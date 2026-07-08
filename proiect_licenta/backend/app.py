from flask import Flask, request, jsonify, Response
from flask_cors import CORS
from flask_socketio import SocketIO, emit
from flask_jwt_extended import jwt_required, get_jwt_identity
import socketio as sio
import os
from dotenv import load_dotenv
load_dotenv()
import mimetypes
import threading
import time
import ffmpeg
import re
import requests
import json
import uuid
from datetime import datetime
from io import BytesIO
import logging

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger('app')

# Suprima logurile prea verbose din biblioteci externe
logging.getLogger('werkzeug').setLevel(logging.WARNING)
logging.getLogger('engineio').setLevel(logging.WARNING)
logging.getLogger('socketio').setLevel(logging.WARNING)

# Tracking sesiuni active de procesare: {video_id: {mode, dm_model, started_at}}
active_processing_sessions = {}
stopping_processing_sessions = set()
active_reid_sessions = {}
_pending_reid_crops = {}   # global_id (str) -> best_crop base64, acumulat din person_crop events
_sessions_lock = threading.Lock()

from models import Video, TrackingSession, TrackingSessionCamera
from werkzeug.utils import secure_filename
from minio_client import init_minio, upload_file_to_minio, minio_client, BUCKET_NAME
from extensions import db, jwt, bcrypt
from auth import auth_bp

app = Flask(__name__)

app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'postgresql://admin:parola_sigura@localhost:5433/licenta_db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'licenta-secret-key-2024')
app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY', 'jwt-super-secret-key')

db.init_app(app)
jwt.init_app(app)
bcrypt.init_app(app)

app.register_blueprint(auth_bp)

CORS(app, resources={r"/*": {"origins": "*"}})

socketio = SocketIO(app,
                    cors_allowed_origins="*",
                    async_mode='threading',
                    max_http_buffer_size=150*1024*1024,
                    ping_timeout=60,
                    ping_interval=25)

UPLOAD_FOLDER = "uploads"
RESULTS_FOLDER = "results"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(RESULTS_FOLDER, exist_ok=True)

YOUTUBE_MAX_SECONDS = int(os.getenv("YOUTUBE_MAX_SECONDS", "30"))
YOUTUBE_MAX_HEIGHT = int(os.getenv("YOUTUBE_MAX_HEIGHT", "1280"))
DIRECT_CLUSTER_MAX_MB = float(os.getenv("DIRECT_CLUSTER_MAX_MB", "50"))
CLUSTER_COMPRESS_MAX_MB = float(os.getenv("CLUSTER_COMPRESS_MAX_MB", "500"))
CLUSTER_UPLOAD_TIMEOUT = int(os.getenv("CLUSTER_UPLOAD_TIMEOUT", "600"))

with app.app_context():
    db.create_all()
    init_minio()
    logger.info("[INIT] Database si MinIO initializate cu succes")

processing_client = sio.Client(reconnection=True, reconnection_attempts=10, reconnection_delay=2)
_connect_lock = threading.Lock()

def connect_to_processing_server():
    with _connect_lock:
        if processing_client.connected:
            logger.debug("[CLUSTER] Deja conectat la Cluster")
            return True
        try:
            _ps_url = os.getenv('PROCESSING_SERVER_URL', 'http://localhost:5001')
            logger.info(f'[CLUSTER] Conectare la Cluster ({_ps_url})...')
            processing_client.connect(
                _ps_url,
                transports=['websocket'],
                wait_timeout=10
            )
            return True
        except Exception as e:
            logger.warning(f'[CLUSTER] Nu s-a putut conecta la Cluster: {e}')
            return False


image_processing_results = {}
image_processing_events = {}    # threading.Event per in-flight request

def normalize_mode(mode):
    mode = str(mode or "").strip().lower()
    if mode in ("crowd", "dmcount", "qnrf", "nwpu"):
        return "crowd"
    if mode in ("tracking", "reid"):
        return "tracking"
    return "detection"

def normalize_dm_model(dm_model):
    """Acceptă doar qnrf sau nwpu; fallback pe qnrf."""
    return dm_model if dm_model in ('qnrf', 'nwpu') else 'qnrf'

BALANCED_REID_CONFIG = {
    "preset": "balanced",
    "enable_reid_embeddings": True,
    "emit_debug_info": True,
    "max_embeddings": 6,
    "embedding_every_seen": 4,
    "min_embeddings_to_match": 2,
    "recheck_interval": 8,
    "reid_threshold": 0.75,
    "intra_threshold": 0.55,
    "min_crop_h": 50,
    "min_crop_w": 18,
    "min_crop_area": 1200,
}

REID_CONFIG_LIMITS = {
    "max_embeddings": (1, 20, int),
    "embedding_every_seen": (1, 50, int),
    "min_embeddings_to_match": (1, 10, int),
    "recheck_interval": (1.0, 60.0, float),
    "reid_threshold": (0.40, 0.95, float),
    "intra_threshold": (0.30, 0.95, float),
    "min_crop_h": (10, 300, int),
    "min_crop_w": (5, 200, int),
    "min_crop_area": (100, 50000, int),
}

VALID_REID_PRESETS = {"balanced", "strict", "sensitive", "custom"}

def _coerce_bool(value, default):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in ("1", "true", "yes", "on"):
            return True
        if normalized in ("0", "false", "no", "off"):
            return False
    return default

def _clamp_config_value(value, low, high, caster, default):
    try:
        coerced = caster(value)
    except (TypeError, ValueError):
        coerced = default
    coerced = max(low, min(high, coerced))
    return caster(coerced)

def sanitize_reid_config(raw):
    raw = raw if isinstance(raw, dict) else {}
    clean = dict(BALANCED_REID_CONFIG)

    preset = str(raw.get("preset", clean["preset"])).strip().lower()
    clean["preset"] = preset if preset in VALID_REID_PRESETS else "balanced"
    clean["enable_reid_embeddings"] = _coerce_bool(
        raw.get("enable_reid_embeddings", clean["enable_reid_embeddings"]),
        clean["enable_reid_embeddings"],
    )
    clean["emit_debug_info"] = _coerce_bool(
        raw.get("emit_debug_info", clean["emit_debug_info"]),
        clean["emit_debug_info"],
    )

    for key, (low, high, caster) in REID_CONFIG_LIMITS.items():
        clean[key] = _clamp_config_value(
            raw.get(key, clean[key]),
            low,
            high,
            caster,
            clean[key],
        )

    return clean

def upload_file_to_cluster(local_path, filename, metadata=None):
    cluster_url = os.getenv('PROCESSING_SERVER_URL', 'http://localhost:5001').rstrip('/')
    upload_url = f"{cluster_url}/api/input/upload"
    data = {"filename": filename}
    if metadata:
        data.update({k: v for k, v in metadata.items() if v is not None})

    logger.info(f"[CLUSTER-UPLOAD] Trimitere directa catre cluster: {filename} -> {upload_url}")
    with open(local_path, "rb") as file_obj:
        response = requests.post(
            upload_url,
            files={"video": (filename, file_obj, "application/octet-stream")},
            data=data,
            timeout=CLUSTER_UPLOAD_TIMEOUT,
        )
    response.raise_for_status()
    return response.json()

def _image_result_key(video_id):
    return str(video_id) if video_id is not None else None

def _compact_image_event_log(data):
    if not isinstance(data, dict):
        return str(data)
    compact = dict(data)
    if 'annotated_image' in compact:
        compact['annotated_image'] = f"<base64:{len(compact['annotated_image'])} chars>"
    return compact

def _log_active_sessions():
    """Loghează toate sesiunile active de procesare."""
    if not active_processing_sessions:
        logger.debug("[TRACKING] Nu există sesiuni active de procesare")
    else:
        logger.info(f"[TRACKING] Sesiuni active ({len(active_processing_sessions)}): "
                    + ", ".join(f"video_id={vid} mode={s['mode']} dm={s['dm_model']} pornit={s['started_at']}"
                                for vid, s in active_processing_sessions.items()))

# ── Relay events de la Cluster la Frontend ─────────────────────────────────

def _reid_session_key(job_id, cameras):
    if job_id:
        return f"job:{job_id}"
    video_ids = sorted(str(cam.get('video_id')) for cam in cameras if isinstance(cam, dict) and cam.get('video_id') is not None)
    return "videos:" + ",".join(video_ids)

def _upload_json_to_minio(object_name, payload):
    data = json.dumps(payload, ensure_ascii=False, default=str, indent=2).encode("utf-8")
    minio_client.put_object(
        BUCKET_NAME,
        object_name,
        BytesIO(data),
        length=len(data),
        content_type="application/json",
    )
    return object_name

def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default

def _mark_reid_videos_completed(video_ids, n_people):
    ids = [int(vid) for vid in video_ids if vid is not None]
    if not ids:
        return []

    updated = Video.query.filter(Video.id.in_(ids)).all()
    n_people_int = _safe_int(n_people, None)
    for video in updated:
        video.status = 'Completed'
        if n_people_int is not None:
            video.total_unique_people = n_people_int
        video.dm_model_used = 'tracking'
    return [video.id for video in updated]

def _create_tracking_session(job_id, cameras, reid_config):
    video_ids = [int(cam.get('video_id')) for cam in cameras if isinstance(cam, dict) and cam.get('video_id') is not None]
    if not video_ids:
        return None

    videos_by_id = {video.id: video for video in Video.query.filter(Video.id.in_(video_ids)).all()}
    first_video = next((videos_by_id.get(video_id) for video_id in video_ids if videos_by_id.get(video_id)), None)
    if not first_video:
        return None

    session = TrackingSession(
        job_id=job_id,
        user_id=first_video.user_id,
        status="Processing",
        reid_config=reid_config or {},
    )
    db.session.add(session)
    db.session.flush()

    for cam in cameras:
        video_id = int(cam.get('video_id'))
        db.session.add(TrackingSessionCamera(
            session_id=session.id,
            video_id=video_id,
            camera_name=cam.get('camera_name'),
            camera_order=cam.get('camera_order'),
            status="Processing",
        ))

    db.session.commit()
    logger.info(f"[REID][SESSION] Creata sesiune tracking id={session.id} job_id={job_id} cameras={video_ids}")
    return session

def _find_tracking_session_for_complete(job_id, camera_video_ids):
    if job_id:
        session = TrackingSession.query.filter_by(job_id=job_id).order_by(TrackingSession.id.desc()).first()
        if session:
            return session

    if camera_video_ids:
        return (
            TrackingSession.query
            .join(TrackingSessionCamera)
            .filter(
                TrackingSession.status == "Processing",
                TrackingSessionCamera.video_id.in_([int(vid) for vid in camera_video_ids]),
            )
            .order_by(TrackingSession.id.desc())
            .first()
        )

    return TrackingSession.query.filter_by(status="Processing").order_by(TrackingSession.id.desc()).first()

def _should_forward_live_event(video_id):
    if video_id is None:
        return True
    video_key = str(video_id)
    return video_key in active_processing_sessions and video_key not in stopping_processing_sessions

@processing_client.on('frame')
def relay_frame(data):
    video_id = data.get('video_id') if isinstance(data, dict) else None
    if not _should_forward_live_event(video_id):
        logger.debug(f"[RELAY] frame ignorat pentru video_id={video_id} (sesiune oprita sau in curs de oprire)")
        return
    if isinstance(data, dict):
        data.setdefault('relay_timestamp_ms', int(time.time() * 1000))
    socketio.emit('frame', data)

@processing_client.on('processing_complete')
def relay_complete(data):
    video_id = data.get('video_id') if isinstance(data, dict) else '?'
    logger.info(f"[RELAY] processing_complete primit de la cluster pentru video_id={video_id}: {data}")
    socketio.emit('processing_complete', data)
    with _sessions_lock:
        session_info = active_processing_sessions.pop(str(video_id), None)
        stopping_processing_sessions.discard(str(video_id))
    if session_info:
        elapsed = time.time() - session_info.get('started_ts', time.time())
        logger.info(f"[TRACKING] Sesiune finalizată video_id={video_id} după {elapsed:.1f}s")
    _log_active_sessions()
    logger.info(f"[RELAY] processing_complete emis catre frontend pentru video_id={video_id}")

@processing_client.on('error')
def relay_error(data):
    video_id = data.get('video_id') if isinstance(data, dict) else '?'
    logger.error(f"[RELAY] error de la cluster pentru video_id={video_id}: {data}")
    socketio.emit('error', data)

@processing_client.on('reid_update')
def relay_reid_update(data):
    logger.debug(f"[RELAY] reid_update -> frontend: {data}")
    socketio.emit('reid_update', data)

@processing_client.on('reid_complete')
def relay_reid_complete(data):
    n_people = data.get('n_people', '?') if isinstance(data, dict) else '?'
    logger.info(f"[RELAY] reid_complete -> frontend: {n_people} persoane identificate | {data}")
    cameras = data.get('cameras', []) if isinstance(data, dict) else []
    camera_video_ids = [
        str(cam.get('video_id'))
        for cam in cameras
        if isinstance(cam, dict) and cam.get('video_id') is not None
    ]
    with _sessions_lock:
        ids_to_clear = camera_video_ids or [
            vid for vid, session in active_processing_sessions.items()
            if session.get('mode') == 'reid'
        ]
        for vid in ids_to_clear:
            active_processing_sessions.pop(vid, None)
            stopping_processing_sessions.discard(vid)
    with app.app_context():
        if camera_video_ids:
            try:
                updated_ids = _mark_reid_videos_completed(camera_video_ids, n_people)
                db.session.commit()
                logger.info(f"[REID] Status DB actualizat -> Completed pentru video_ids={updated_ids}")
            except Exception as db_err:
                db.session.rollback()
                logger.error(f"[REID] Nu am putut actualiza statusul DB la final Re-ID: {db_err}")
        try:
            job_id = data.get('job_id') if isinstance(data, dict) else None
            session = _find_tracking_session_for_complete(job_id, camera_video_ids)
            if session:
                session_video_ids = [str(camera.video_id) for camera in session.cameras if camera.video_id is not None]
                if not camera_video_ids and session_video_ids:
                    updated_ids = _mark_reid_videos_completed(session_video_ids, n_people)
                    logger.info(f"[REID] Status DB actualizat din sesiune -> Completed pentru video_ids={updated_ids}")
                session.status = "Completed"
                session.completed_at = datetime.now()
                session.n_people = _safe_int(n_people, 0)
                global_people = data.get('global_people', {}) if isinstance(data, dict) else {}
                with _sessions_lock:
                    for gid_str, crops in _pending_reid_crops.items():
                        if gid_str in global_people and crops:
                            global_people[gid_str]['best_crop'] = crops[0]['image']
                            global_people[gid_str]['crop_history'] = crops
                    _pending_reid_crops.clear()
                session.global_people_summary = global_people
                for camera in session.cameras:
                    camera.status = "Completed"
                summary_path = f"user_{session.user_id}/tracking_sessions/{session.id}/summary.json"
                session.summary_json_path = _upload_json_to_minio(summary_path, data)
                db.session.commit()
                active_reid_sessions.pop(_reid_session_key(job_id, cameras), None)
                logger.info(f"[REID][SESSION] Finalizata sesiune tracking id={session.id} summary={summary_path}")
                if isinstance(data, dict):
                    data['db_session_id'] = session.id
        except Exception as session_err:
            db.session.rollback()
            logger.error(f"[REID][SESSION] Nu am putut finaliza sesiunea tracking: {session_err}")
    _log_active_sessions()
    socketio.emit('reid_complete', data)

# ── NOU: relay person_crop — cropuri + metadata persoane identificate ─────────
@processing_client.on('person_crop')
def relay_person_crop(data):
    """
    Relay eveniment person_crop de la cluster la frontend.
    Payload: { global_id, camera_name, track_id, frame_number, timestamp_ms,
               timestamp_s, crops[], best_crop, match_score, is_new_person,
               n_embeddings, bbox, bbox_area, cameras[], color }
    """
    gid = data.get('global_id', '?') if isinstance(data, dict) else '?'
    cam = data.get('camera_name', '?') if isinstance(data, dict) else '?'
    is_new = data.get('is_new_person', False) if isinstance(data, dict) else False
    score = data.get('match_score', 0) if isinstance(data, dict) else 0
    logger.info(
        f"[RELAY] person_crop -> frontend: G{gid} | cam={cam} | "
        f"{'NOU' if is_new else f'match={score:.3f}'}"
    )
    # Acumulam toate cropurile per global_id pentru a le salva in summary la reid_complete
    if isinstance(data, dict) and data.get('best_crop') and gid != '?':
        gid_str = str(gid)
        crop_entry = {
            'image':        data['best_crop'],
            'camera_name':  data.get('camera_name'),
            'track_id':     data.get('track_id'),
            'frame_number': data.get('frame_number'),
            'timestamp_s':  data.get('timestamp_s'),
            'match_score':  data.get('match_score'),
            'is_new_person':data.get('is_new_person'),
        }
        with _sessions_lock:
            if gid_str not in _pending_reid_crops:
                _pending_reid_crops[gid_str] = []
            _pending_reid_crops[gid_str].append(crop_entry)
    socketio.emit('person_crop', data)
# ─────────────────────────────────────────────────────────────────────────────

@processing_client.on('reid_frame_detections')
def relay_reid_frame_detections(data):
    cam = data.get('camera_name', '?') if isinstance(data, dict) else '?'
    logger.debug(f"[RELAY] reid_frame_detections -> frontend: cam={cam}")
    socketio.emit('reid_frame_detections', data)

@processing_client.on('reid_config')
def relay_reid_config(data):
    logger.debug(f"[RELAY] reid_config -> frontend: {data}")
    socketio.emit('reid_config', data)

@processing_client.on('reid_embedding_update')
def relay_reid_embedding_update(data):
    logger.debug(f"[RELAY] reid_embedding_update -> frontend: {data}")
    socketio.emit('reid_embedding_update', data)

@processing_client.on('reid_embedding_skip')
def relay_reid_embedding_skip(data):
    logger.debug(f"[RELAY] reid_embedding_skip -> frontend: {data}")
    socketio.emit('reid_embedding_skip', data)

@processing_client.on('reid_final_summary')
def relay_reid_final_summary(data):
    logger.debug(f"[RELAY] reid_final_summary -> frontend: {data}")
    socketio.emit('reid_final_summary', data)

@processing_client.on('processing_stopped')
def relay_processing_stopped(data):
    video_id = data.get('video_id') if isinstance(data, dict) else '?'
    logger.info(f"[RELAY] processing_stopped <- cluster video_id={video_id}")
    with _sessions_lock:
        session_info = active_processing_sessions.pop(str(video_id), None)
        stopping_processing_sessions.discard(str(video_id))
    if session_info:
        elapsed = time.time() - session_info.get('started_ts', time.time())
        logger.info(f"[TRACKING] Sesiune oprita (cluster confirm) video_id={video_id} dupa {elapsed:.1f}s")
    socketio.emit('processing_stopped', data)

@processing_client.on('warmup_status')
def relay_warmup_status(data):
    logger.info(f"[RELAY] warmup_status -> frontend: {data}")
    socketio.emit('warmup_status', data)

@processing_client.on('reid_prepare_status')
def relay_reid_prepare_status(data):
    logger.info(f"[RELAY] reid_prepare_status -> frontend: {data}")
    socketio.emit('reid_prepare_status', data)

@processing_client.on('reid_ready_to_start')
def relay_reid_ready_to_start(data):
    logger.info(f"[RELAY] reid_ready_to_start -> frontend: {data}")
    socketio.emit('reid_ready_to_start', data)

@processing_client.on('status_update')
def relay_status_update(data):
    video_id = data.get('video_id') if isinstance(data, dict) else '?'
    logger.debug(f"[RELAY] status_update pentru video_id={video_id}: {data}")
    socketio.emit('status_update', data)

@processing_client.on('mode_updated')
def relay_mode_updated(data):
    video_id = data.get('video_id') if isinstance(data, dict) else '?'
    logger.info(f"[RELAY] mode_updated pentru video_id={video_id}: {data}")
    socketio.emit('mode_updated', data)

@processing_client.on('image_processed')
def handle_image_processed(data):
    logger.info(f"[IMAGE] image_processed de la cluster: {_compact_image_event_log(data)}")
    video_id = data.get('video_id') if isinstance(data, dict) else None
    result_key = _image_result_key(video_id)
    if result_key:
        image_processing_results[result_key] = {'data': data, 'error': None}
        if result_key in image_processing_events:
            image_processing_events[result_key].set()
        logger.info(f"[IMAGE] Rezultat stocat pentru video_id={video_id}")
    else:
        logger.warning(f"[IMAGE] image_processed fara video_id: {_compact_image_event_log(data)}")

@processing_client.on('image_error')
def handle_image_error(data):
    logger.error(f"[IMAGE] image_error de la cluster: {data}")
    video_id = data.get('video_id') if isinstance(data, dict) else None
    error_msg = data.get('error', 'Unknown error') if isinstance(data, dict) else str(data)
    result_key = _image_result_key(video_id)
    if result_key:
        image_processing_results[result_key] = {'data': None, 'error': error_msg}
        if result_key in image_processing_events:
            image_processing_events[result_key].set()
        logger.error(f"[IMAGE] Eroare procesare imagine video_id={video_id}: {error_msg}")
    else:
        logger.warning(f"[IMAGE] image_error fara video_id: {data}")

@processing_client.on('connect')
def on_processing_connect():
    logger.info('[CLUSTER] Conectat la Processing Server (Cluster) pe portul 5001')

@processing_client.on('disconnect')
def on_processing_disconnect():
    logger.warning('[CLUSTER] Deconectat de la Processing Server')
    if active_processing_sessions:
        logger.warning(f"[CLUSTER] Atentie: {len(active_processing_sessions)} sesiuni active la deconectare: "
                       + str(list(active_processing_sessions.keys())))

# ── Helpers MinIO / Heatmap ─────────────────────────────────────────────────

def _derive_heatmap_key(processed_video_key):
    folder, filename = os.path.split(processed_video_key)
    return f"{folder}/heatmap_{filename}" if folder else f"heatmap_{filename}"

def _object_exists(object_key):
    try:
        minio_client.stat_object(BUCKET_NAME, object_key)
        return True
    except Exception:
        return False

def _resolve_heatmap_key(video):
    explicit_key = (video.heatmap_video_path or '').strip()
    if explicit_key and _object_exists(explicit_key):
        logger.debug(f"[HEATMAP] Cheie explicita gasita pentru video_id={video.id}: {explicit_key}")
        return explicit_key

    if video.processed_video_path:
        derived_key = _derive_heatmap_key(video.processed_video_path)
        if _object_exists(derived_key):
            logger.debug(f"[HEATMAP] Cheie derivata gasita pentru video_id={video.id}: {derived_key}")
            return derived_key

    logger.debug(f"[HEATMAP] Nicio cheie heatmap pentru video_id={video.id}")
    return None

# ── Routes ──────────────────────────────────────────────────────────────────

@app.route('/api/video/watch/<int:video_id>/variants')
def watch_video_variants(video_id):
    logger.debug(f"[WATCH] Cerere variante video_id={video_id}")
    video = db.session.get(Video, video_id)
    if not video:
        return jsonify({"error": "Video not found"}), 404
    if not video.processed_video_path:
        logger.warning(f"[WATCH] video_id={video_id} nu are processed_video_path")
        return jsonify({"error": "Video is still being processed or failed"}), 404
    heatmap_key = _resolve_heatmap_key(video)
    heatmap_available = bool(heatmap_key)
    logger.info(f"[WATCH] Variante pentru video_id={video_id}: heatmap_available={heatmap_available}")
    return jsonify({
        "normal": f"/api/video/watch/{video_id}?variant=normal",
        "heatmap": f"/api/video/watch/{video_id}?variant=heatmap",
        "heatmap_available": heatmap_available,
        "heatmap_key": heatmap_key if heatmap_available else None
    }), 200

@app.route('/api/video/watch/<int:video_id>')
def watch_video(video_id):
    from models import Video
    from minio_client import minio_client, BUCKET_NAME
    from flask import Response

    requested_variant = (request.args.get('variant') or 'normal').lower()
    logger.info(f"[WATCH] Cerere vizionare video_id={video_id} variant={requested_variant}")

    video = Video.query.get_or_404(video_id)
    if not video.processed_video_path:
        logger.warning(f"[WATCH] video_id={video_id} nu are processed_video_path")
        return {"error": "Video is still being processed or failed"}, 404

    selected_key = video.processed_video_path

    if requested_variant == 'heatmap':
        heatmap_key = _resolve_heatmap_key(video)
        if not heatmap_key:
            logger.warning(f"[WATCH] Heatmap indisponibil pentru video_id={video_id}")
            return {"error": "Heatmap variant is not available for this video"}, 404
        selected_key = heatmap_key

    logger.debug(f"[WATCH] Servire din MinIO: {selected_key}")
    try:
        stat = minio_client.stat_object(BUCKET_NAME, selected_key)
        total_size = stat.size
        guessed_mime, _ = mimetypes.guess_type(selected_key)
        response_mime = guessed_mime or 'application/octet-stream'
        filename = os.path.basename(selected_key)

        range_header = request.headers.get('Range')
        if range_header:
            # Parse "bytes=start-end"
            byte_range = range_header.replace('bytes=', '').split('-')
            start = int(byte_range[0]) if byte_range[0] else 0
            end   = int(byte_range[1]) if len(byte_range) > 1 and byte_range[1] else total_size - 1
            end   = min(end, total_size - 1)
            length = end - start + 1
            minio_data = minio_client.get_object(BUCKET_NAME, selected_key, offset=start, length=length)
            logger.info(f"[WATCH] Range request video_id={video_id} bytes={start}-{end}/{total_size}")
            return Response(
                minio_data.stream(amt=65536),
                status=206,
                mimetype=response_mime,
                headers={
                    "Content-Range": f"bytes {start}-{end}/{total_size}",
                    "Accept-Ranges": "bytes",
                    "Content-Length": str(length),
                    "Content-Disposition": f"inline; filename={filename}",
                }
            )

        minio_data = minio_client.get_object(BUCKET_NAME, selected_key)
        logger.info(f"[WATCH] Servit video_id={video_id} ({response_mime}) din {selected_key}")
        return Response(
            minio_data.stream(amt=65536),
            mimetype=response_mime,
            headers={
                "Accept-Ranges": "bytes",
                "Content-Length": str(total_size),
                "Content-Disposition": f"inline; filename={filename}",
            }
        )
    except Exception as e:
        logger.error(f"[WATCH] Eroare servire video_id={video_id} din MinIO: {e}")
        return {"error": str(e)}, 500


@app.route('/api/videos/<int:video_id>/metadata', methods=['GET'])
@jwt_required()
def get_video_metadata(video_id):
    current_user_id = get_jwt_identity()
    logger.info(f"[METADATA] Cerere metadata video_id={video_id} user_id={current_user_id}")
    video = Video.query.filter_by(id=video_id, user_id=current_user_id).first()

    if not video:
        logger.warning(f"[METADATA] video_id={video_id} nu exista sau acces refuzat pentru user_id={current_user_id}")
        return jsonify({"error": "Video not found or access denied"}), 404

    resolved_heatmap_key = _resolve_heatmap_key(video)
    logger.debug(f"[METADATA] video_id={video_id} status={video.status} people={video.total_unique_people} heatmap={bool(resolved_heatmap_key)}")

    if video.dm_model_used in ('qnrf', 'nwpu'):
        processing_mode = 'crowd'
    elif video.dm_model_used == 'tracking':
        processing_mode = 'tracking'
    else:
        processing_mode = 'detection'

    return jsonify({
        "id": video.id,
        "filename": video.filename,
        "status": video.status,
        "created_at": video.created_at.isoformat(),
        "total_unique_people": video.total_unique_people or 0,
        "avg_dwell_time_sec": video.avg_dwell_time_sec or 0,
        "max_people_in_frame": video.max_people_in_frame or 0,
        "avg_people_per_frame": video.avg_people_per_frame or 0.0,
        "dm_model_used": video.dm_model_used,
        "processing_mode": processing_mode,
        "has_heatmap": bool(resolved_heatmap_key),
        "heatmap_video_path": resolved_heatmap_key,
        "processed_video_url": f"/api/video/watch/{video.id}?variant=normal" if video.processed_video_path else None,
        "heatmap_video_url": f"/api/video/watch/{video.id}?variant=heatmap" if resolved_heatmap_key else None,
    }), 200


@app.route("/upload", methods=["POST"])
@jwt_required()
def upload_video():
    current_user_id = get_jwt_identity()
    logger.info(f"[UPLOAD] Cerere upload de la user_id={current_user_id}")

    file = request.files.get("video")
    if not file:
        logger.warning(f"[UPLOAD] Niciun fisier primit de la user_id={current_user_id}")
        return jsonify({"error": "No file uploaded"}), 400

    camera_name = (request.form.get("camera_name") or "").strip()
    camera_order = (request.form.get("camera_order") or "").strip()
    camera_location = (request.form.get("camera_location") or "").strip()

    filename = secure_filename(file.filename)
    logger.info(f"[UPLOAD] Fisier: {filename} | camera={camera_name} order={camera_order} location={camera_location}")

    existing_video = Video.query.filter_by(filename=filename, user_id=current_user_id).first()
    if existing_video:
        logger.warning(f"[UPLOAD] Fisier duplicat: {filename} deja exista cu video_id={existing_video.id}")
        return jsonify({"error": "Video already exists", "video_id": existing_video.id}), 409

    local_filepath = os.path.join(UPLOAD_FOLDER, filename)
    file.save(local_filepath)
    logger.debug(f"[UPLOAD] Salvat local: {local_filepath}")

    file_size_mb = os.path.getsize(local_filepath) / (1024 * 1024)
    logger.info(f"[UPLOAD] Dimensiune fisier: {file_size_mb:.2f} MB")
    upload_source = local_filepath
    storage_target = "cluster"

    minio_object_name = f"user_{current_user_id}/{filename}"
    storage_metadata = {
        "uploaded_by_user": str(current_user_id),
        "camera_name": camera_name or "",
        "camera_order": camera_order or "",
        "camera_location": camera_location or "",
    }

    if file_size_mb > CLUSTER_COMPRESS_MAX_MB:
        storage_target = "minio"
        logger.info(
            f"[UPLOAD] Fisier foarte mare ({file_size_mb:.2f} MB > "
            f"{CLUSTER_COMPRESS_MAX_MB:.0f} MB), se foloseste MinIO"
        )

    if file_size_mb > DIRECT_CLUSTER_MAX_MB:
        logger.warning(f"[UPLOAD] Fisier peste prag direct ({file_size_mb:.2f} MB > {DIRECT_CLUSTER_MAX_MB:.0f} MB), pornesc compresia...")
        compressed_filename = f"compressed_{filename}"
        compressed_filepath = os.path.join(UPLOAD_FOLDER, compressed_filename)
        try:
            (
                ffmpeg
                .input(local_filepath)
                .output(compressed_filepath,
                        vcodec='libx264',
                        crf=28,
                        preset='ultrafast',
                        vf='scale=-2:1280')
                .overwrite_output()
                .run(quiet=True)
            )
            compressed_mb = os.path.getsize(compressed_filepath) / (1024 * 1024)
            if compressed_mb < file_size_mb:
                upload_source = compressed_filepath
                logger.info(f"[UPLOAD] Comprimat cu succes: {compressed_mb:.2f} MB (de la {file_size_mb:.2f} MB)")
            else:
                os.remove(compressed_filepath)
                logger.warning(f"[UPLOAD] Compresia a marit fisierul ({compressed_mb:.2f} MB > {file_size_mb:.2f} MB), se foloseste originalul")
        except Exception as e:
            logger.error(f"[UPLOAD] Compresia a esuat, se foloseste originalul: {e}")

    if storage_target == "cluster":
        try:
            cluster_response = upload_file_to_cluster(upload_source, filename, metadata=storage_metadata)
            logger.info(f"[UPLOAD] Fisier trimis direct la cluster: {cluster_response}")
        except Exception as e:
            logger.exception(f"[UPLOAD] Trimiterea directa la cluster a esuat pentru {filename}: {e}")
            if os.path.exists(local_filepath):
                os.remove(local_filepath)
            if upload_source != local_filepath and os.path.exists(upload_source):
                os.remove(upload_source)
            return jsonify({"error": "Cluster upload failed", "details": str(e)}), 502

        fallback_minio_path = None
        try:
            if upload_file_to_minio(upload_source, minio_object_name, metadata=storage_metadata):
                fallback_minio_path = minio_object_name
                logger.info(f"[UPLOAD] Fallback MinIO salvat pentru Re-ID: {fallback_minio_path}")
            else:
                logger.warning(f"[UPLOAD] Fallback MinIO indisponibil pentru {filename}")
        except Exception as e:
            logger.warning(f"[UPLOAD] Fallback MinIO a esuat pentru {filename}: {e}")

        new_video = Video(
            filename=filename,
            minio_path=fallback_minio_path,
            status='Pending',
            user_id=current_user_id
        )
        db.session.add(new_video)
        db.session.commit()
        logger.info(f"[UPLOAD] Video inregistrat in DB pentru cluster direct: video_id={new_video.id} filename={filename}")

        if os.path.exists(local_filepath):
            os.remove(local_filepath)
            logger.debug(f"[UPLOAD] Sters fisier local: {local_filepath}")
        if upload_source != local_filepath and os.path.exists(upload_source):
            os.remove(upload_source)
            logger.debug(f"[UPLOAD] Sters fisier comprimat: {upload_source}")

        return jsonify({
            "message": "Upload success",
            "video_id": new_video.id,
            "user_id": current_user_id,
            "storage": "cluster"
        }), 201

    logger.info(f"[UPLOAD] Incarcare in MinIO: {minio_object_name}")
    if upload_file_to_minio(upload_source, minio_object_name, metadata=storage_metadata):
        new_video = Video(
            filename=filename,
            minio_path=minio_object_name,
            status='Pending',
            user_id=current_user_id
        )
        db.session.add(new_video)
        db.session.commit()
        logger.info(f"[UPLOAD] Video inregistrat in DB: video_id={new_video.id} filename={filename}")

        if os.path.exists(local_filepath):
            os.remove(local_filepath)
            logger.debug(f"[UPLOAD] Sters fisier local: {local_filepath}")
        if upload_source != local_filepath and os.path.exists(upload_source):
            os.remove(upload_source)
            logger.debug(f"[UPLOAD] Sters fisier comprimat: {upload_source}")

        return jsonify({
            "message": "Upload success",
            "video_id": new_video.id,
            "user_id": current_user_id,
            "storage": "minio"
        }), 201

    logger.error(f"[UPLOAD] Incarcare MinIO esuata pentru {minio_object_name}")
    return jsonify({"error": "Storage failed"}), 500

@app.route("/process_youtube", methods=["POST"])
@jwt_required()
def process_youtube():
    current_user_id = get_jwt_identity()
    data = request.get_json(silent=True) or {}
    youtube_url = (data.get("youtube_url") or "").strip()
    logger.info(f"[YOUTUBE] Cerere de la user_id={current_user_id} url={youtube_url}")

    if not youtube_url:
        return jsonify({"error": "YouTube URL is required"}), 400

    video_id_match = re.search(r"(?:youtube\.com/watch\?v=|youtu\.be/|v=)([A-Za-z0-9_-]{11})", youtube_url)
    if video_id_match:
        yt_video_id = video_id_match.group(1)
    elif re.match(r"^[A-Za-z0-9_-]{11}$", youtube_url):
        yt_video_id = youtube_url
        youtube_url = f"https://www.youtube.com/watch?v={yt_video_id}"
    else:
        logger.warning(f"[YOUTUBE] URL invalid: {youtube_url}")
        return jsonify({"error": "Invalid YouTube URL or video ID"}), 400

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    local_filename = f"youtube_{yt_video_id}_{timestamp}.mp4"
    local_filepath = os.path.join(UPLOAD_FOLDER, local_filename)

    try:
        try:
            import yt_dlp
        except ImportError:
            logger.error("[YOUTUBE] yt-dlp nu este instalat")
            return jsonify({"error": "yt-dlp is not installed on backend", "hint": "Run: pip install yt-dlp"}), 500

        logger.info(f"[YOUTUBE] Descarcare video: {yt_video_id} (max {YOUTUBE_MAX_SECONDS}s, {YOUTUBE_MAX_HEIGHT}p)")
        ydl_opts = {
            "format": "best[ext=mp4][height<=1280]/best[height<=1280]/best",
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "retries": 2,
            "socket_timeout": 10,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(youtube_url, download=False)
        logger.debug(f"[YOUTUBE] Titlu video: {info.get('title', 'N/A')} durata: {info.get('duration', 'N/A')}s")

        direct_media_url = info.get("url")
        if not direct_media_url:
            logger.error(f"[YOUTUBE] Nu s-a putut rezolva URL-ul direct pentru {yt_video_id}")
            return jsonify({"error": "Could not resolve direct media URL from YouTube"}), 400

        logger.info(f"[YOUTUBE] Incepe conversie ffmpeg -> {local_filename}")
        (
            ffmpeg
            .input(direct_media_url, t=YOUTUBE_MAX_SECONDS)
            .output(
                local_filepath,
                vcodec="libx264",
                acodec="aac",
                preset="ultrafast",
                crf=32,
                vf=f"scale=-2:{YOUTUBE_MAX_HEIGHT}",
                movflags="+faststart",
            )
            .overwrite_output()
            .run(quiet=True)
        )

        if not os.path.exists(local_filepath):
            logger.error(f"[YOUTUBE] Fisierul nu a fost creat: {local_filepath}")
            return jsonify({"error": "Video file was not created"}), 500

        file_size_mb = os.path.getsize(local_filepath) / (1024 * 1024)
        logger.info(f"[YOUTUBE] Conversie completa: {local_filename} ({file_size_mb:.2f} MB)")

        minio_object_name = f"user_{current_user_id}/{local_filename}"
        logger.info(f"[YOUTUBE] Incarcare in MinIO: {minio_object_name}")
        if not upload_file_to_minio(local_filepath, minio_object_name):
            logger.error(f"[YOUTUBE] Incarcare MinIO esuata pentru {minio_object_name}")
            return jsonify({"error": "MinIO upload failed"}), 500

        new_video = Video(
            filename=local_filename,
            minio_path=minio_object_name,
            status='Pending',
            user_id=current_user_id
        )
        db.session.add(new_video)
        db.session.commit()
        logger.info(f"[YOUTUBE] Video inregistrat in DB: video_id={new_video.id} filename={local_filename}")

        return jsonify({
            "message": "YouTube video processed",
            "video_id": new_video.id,
            "filename": local_filename,
            "user_id": current_user_id
        }), 201
    except Exception as e:
        logger.exception(f"[YOUTUBE] Procesare esuata pentru {youtube_url}: {e}")
        return jsonify({
            "error": f"Processing failed: {str(e)}",
            "hint": "Try another video URL or reduce YOUTUBE_MAX_SECONDS/YOUTUBE_MAX_HEIGHT"
        }), 500
    finally:
        for path in [local_filepath]:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                    logger.debug(f"[YOUTUBE] Sters fisier temp: {path}")
                except OSError:
                    pass

# ── Socket.IO handlers ───────────────────────────────────────────────────────

@socketio.on('start_processing')
def handle_start_processing(data):
    video_id = data.get('video_id')
    filename = data.get('filename')
    stream_url = data.get('stream_url')
    requested_mode = normalize_mode(data.get('mode'))
    requested_dm_model = normalize_dm_model(data.get('dm_model'))
    requested_camera = data.get('camera') if isinstance(data, dict) else None

    logger.info(f"[PROCESSING] start_processing primit: video_id={video_id} mode={requested_mode} dm_model={requested_dm_model} stream={bool(stream_url)}")

    if not video_id:
        logger.error("[PROCESSING] Cerere primita fara video_id")
        emit('error', {'message': 'Missing video_id'})
        return

    if active_processing_sessions:
        logger.info(f"[TRACKING] Sesiuni deja active: {list(active_processing_sessions.keys())}")

    is_live = str(video_id).startswith('live_')
    video = None
    if not is_live:
        video = db.session.get(Video, int(video_id))
        if not video:
            logger.error(f"[PROCESSING] Video ID {video_id} nu exista in DB")
            emit('error', {'message': 'Video not found in DB'})
            return
        logger.debug(f"[PROCESSING] Video gasit in DB: video_id={video_id} filename={video.filename} status={video.status}")

    if not processing_client.connected:
        logger.warning("[PROCESSING] Cluster deconectat. Incerc reconectarea...")
        if not connect_to_processing_server():
            logger.error("[PROCESSING] Reconectare esuata - cluster offline")
            emit('error', {'message': 'Cluster is offline. Cannot start processing.'})
            return

    cluster_payload = {
        'video_id': video_id,
        'mode': requested_mode,
        'dm_model': requested_dm_model,
    }

    if isinstance(requested_camera, dict):
        cluster_payload['camera'] = {
            'name': (requested_camera.get('name') or '').strip(),
            'order': requested_camera.get('order'),
            'location': (requested_camera.get('location') or '').strip(),
        }
        logger.debug(f"[PROCESSING] Camera info: {cluster_payload['camera']}")

    if stream_url:
        cluster_payload['stream_url'] = stream_url
        logger.info(f"[PROCESSING] LIVE stream delegat la Cluster: {stream_url} | mode={requested_mode} | dm_model={requested_dm_model}")
    else:
        actual_filename = filename if filename else video.filename
        cluster_payload['filename'] = actual_filename
        logger.info(f"[PROCESSING] Fisier delegat la Cluster: {actual_filename} | mode={requested_mode} | dm_model={requested_dm_model}")

    try:
        processing_client.emit('start_processing', cluster_payload)
        logger.debug(f"[PROCESSING] Payload trimis la cluster: {cluster_payload}")

        with _sessions_lock:
            stopping_processing_sessions.discard(str(video_id))
            active_processing_sessions[str(video_id)] = {
                'mode': requested_mode,
                'dm_model': requested_dm_model,
                'started_at': datetime.now().strftime('%H:%M:%S'),
                'started_ts': time.time(),
                'is_live': bool(stream_url),
            }
        _log_active_sessions()

        if video:
            video.status = 'Processing'
            db.session.commit()
            logger.debug(f"[PROCESSING] Status DB actualizat -> Processing pentru video_id={video_id}")

        emit('processing_started', {
            'video_id': video_id,
            'mode': requested_mode,
            'dm_model': requested_dm_model,
            'camera': cluster_payload.get('camera'),
            'is_live': bool(stream_url)
        })
        logger.info(f"[PROCESSING] Procesare pornita cu succes pentru video_id={video_id}")

    except Exception as e:
        logger.exception(f"[PROCESSING] Eroare critica la emitere catre cluster pentru video_id={video_id}: {e}")
        emit('error', {'message': f'Internal relay error: {str(e)}'})

@app.route("/api/live/start", methods=["POST"])
@jwt_required()
def start_live_feed():
    current_user_id = get_jwt_identity()
    data = request.get_json()
    stream_url = data.get("stream_url")
    logger.info(f"[LIVE] Initializare feed live de la user_id={current_user_id} stream_url={stream_url}")

    if not stream_url:
        logger.warning(f"[LIVE] stream_url lipsa de la user_id={current_user_id}")
        return jsonify({"error": "Stream URL is required"}), 400

    new_live_entry = Video(
        filename=f"Live_{datetime.now().strftime('%H%M%S')}",
        minio_path=None,
        status='Live',
        user_id=current_user_id
    )
    db.session.add(new_live_entry)
    db.session.commit()
    logger.info(f"[LIVE] Feed live inregistrat in DB: video_id={new_live_entry.id} stream={stream_url}")

    return jsonify({
        "message": "Live feed initialized",
        "video_id": new_live_entry.id,
        "stream_url": stream_url
    }), 201

@socketio.on('update_mode')
def handle_update_mode(data):
    video_id = data.get('video_id') if isinstance(data, dict) else None
    if not video_id:
        logger.warning("[MODE] Cerere update_mode fara video_id")
        emit('error', {'message': 'Missing video_id for mode update'})
        return

    if not processing_client.connected:
        logger.warning(f"[MODE] Cluster deconectat la update_mode pentru video_id={video_id}")
        if not connect_to_processing_server():
            emit('error', {'message': 'Cluster is offline. Cannot update mode.'})
            return

    new_mode = normalize_mode(data.get('mode') if isinstance(data, dict) else None)
    new_dm_model = normalize_dm_model(data.get('dm_model') if isinstance(data, dict) else None)
    logger.info(f"[MODE] Schimbare mod pentru video_id={video_id}: mode={new_mode} dm_model={new_dm_model}")

    if str(video_id) in active_processing_sessions:
        active_processing_sessions[str(video_id)]['mode'] = new_mode
        active_processing_sessions[str(video_id)]['dm_model'] = new_dm_model
        logger.debug(f"[TRACKING] Sesiune actualizata pentru video_id={video_id}")

    processing_client.emit('update_mode', {
        'video_id': video_id,
        'mode': new_mode,
        'dm_model': new_dm_model,
    })
    emit('mode_updated', {'video_id': video_id, 'mode': new_mode, 'dm_model': new_dm_model})

@socketio.on('stop_processing')
def handle_stop_processing(data):
    video_id = data.get('video_id') if isinstance(data, dict) else None

    if not video_id:
        logger.warning("[STOP] Cerere stop_processing fara video_id")
        emit('error', {'message': 'Missing video_id for stop request'})
        return

    logger.info(f"[STOP] Cerere oprire pentru video_id={video_id}")

    with _sessions_lock:
        stopping_processing_sessions.add(str(video_id))

    is_live = str(video_id).startswith('live_')
    if not is_live:
        video = db.session.get(Video, video_id)
        if video:
            video.status = 'Stopped'
            db.session.commit()
            logger.info(f"[STOP] Status DB -> Stopped pentru video_id={video_id}")
        else:
            logger.warning(f"[STOP] video_id={video_id} nu exista in DB")

    if processing_client.connected:
        processing_client.emit('stop_processing', {'video_id': video_id})
        logger.info(f"[STOP] Comanda trimisa la Cluster pentru video_id={video_id}")
    else:
        logger.warning(f"[STOP] Cluster deconectat - nu s-a putut trimite comanda stop pentru video_id={video_id}")

    with _sessions_lock:
        session_info = active_processing_sessions.pop(str(video_id), None)
    if session_info:
        elapsed = time.time() - session_info.get('started_ts', time.time())
        logger.info(f"[TRACKING] Sesiune oprita video_id={video_id} dupa {elapsed:.1f}s")
    _log_active_sessions()

    emit('processing_stopped', {
        'video_id': video_id,
        'message': 'Processing stopped successfully'
    })

@socketio.on('prepare_reid')
def handle_prepare_reid(data):
    cameras = data.get('cameras', []) if isinstance(data, dict) else []
    logger.info(f"[REID] Cerere prepare_reid pentru {len(cameras)} camere: {cameras}")

    if not cameras:
        emit('error', {'message': 'No cameras provided for Re-ID prepare'})
        return

    if not processing_client.connected:
        logger.warning("[REID] Cluster deconectat la prepare_reid")
        if not connect_to_processing_server():
            emit('error', {'message': 'Cluster is offline. Cannot prepare Re-ID.'})
            return

    payload = {'cameras': cameras}
    processing_client.emit('prepare_reid', payload)
    logger.info("[REID] Cerere prepare_reid trimisa la cluster")

@socketio.on('start_reid')
def handle_start_reid(data):
    cameras = data.get('cameras', []) if isinstance(data, dict) else []
    job_id = data.get('job_id') if isinstance(data, dict) else None
    save_to_db = bool(data.get('save_to_db', True)) if isinstance(data, dict) else True
    emit_live_events = bool(data.get('emit_live_events', True)) if isinstance(data, dict) else True
    raw_reid_config = data.get("reid_config", {}) if isinstance(data, dict) else {}
    sanitized_reid_config = sanitize_reid_config(raw_reid_config)
    logger.info(f"[REID] Cerere start_reid pentru {len(cameras)} camere: {cameras} | job_id={job_id}")

    if not cameras and not job_id:
        logger.warning("[REID] Nicio camera furnizata pentru Re-ID")
        emit('error', {'message': 'No cameras provided for Re-ID'})
        return

    if not processing_client.connected:
        logger.warning("[REID] Cluster deconectat la start_reid")
        if not connect_to_processing_server():
            emit('error', {'message': 'Cluster is offline. Cannot start Re-ID.'})
            return

    logger.info(f"[REID] Pornire Re-ID pe cluster pentru {len(cameras)} camere")
    socketio.emit('warmup_status', {
        'status': 'warmup',
        'message': f'Pregătire Re-ID pentru {len(cameras)} camere.'
    })

    with _sessions_lock:
        video_ids_for_db = []
        for cam in cameras:
            vid = str(cam.get('video_id', ''))
            if vid:
                stopping_processing_sessions.discard(vid)
                active_processing_sessions[vid] = {
                    'mode': 'reid',
                    'dm_model': None,
                    'job_id': job_id,
                    'started_at': datetime.now().strftime('%H:%M:%S'),
                    'started_ts': time.time(),
                    'is_live': False,
                }
                video_ids_for_db.append(int(vid))
        logger.info(f"[REID] Sesiuni active adaugate pentru Re-ID: {[str(c.get('video_id')) for c in cameras]}")

    if video_ids_for_db:
        try:
            for video in Video.query.filter(Video.id.in_(video_ids_for_db)).all():
                video.status = 'Processing'
                video.dm_model_used = 'tracking'
            db.session.commit()
            logger.info(f"[REID] Status DB actualizat -> Processing pentru video_ids={video_ids_for_db}")
        except Exception as db_err:
            db.session.rollback()
            logger.error(f"[REID] Nu am putut actualiza statusul DB la start Re-ID: {db_err}")

    try:
        session = _create_tracking_session(job_id, cameras, sanitized_reid_config)
        if session:
            active_reid_sessions[_reid_session_key(job_id, cameras)] = session.id
    except Exception as session_err:
        db.session.rollback()
        logger.error(f"[REID][SESSION] Nu am putut crea sesiunea tracking: {session_err}")

    with _sessions_lock:
        _pending_reid_crops.clear()

    print("[REID][CONFIG] Forwarding Re-ID config to cluster:", sanitized_reid_config)
    processing_client.emit('start_reid', {
        'job_id': job_id,
        'cameras': cameras,
        'save_to_db': save_to_db,
        'emit_live_events': emit_live_events,
        'reid_config': sanitized_reid_config,
    })
    emit('reid_started', {'cameras': cameras, 'message': 'Re-ID warmup started'})
    logger.info(f"[REID] Cerere Re-ID trimisa la cluster")

@socketio.on('stop_reid')
def handle_stop_reid(data):
    logger.info("[STOP] Cerere stop_reid primita de la frontend")
    if processing_client.connected:
        processing_client.emit('stop_reid', data or {})
        logger.info("[STOP] Comanda stop_reid trimisa la cluster")
    else:
        logger.warning("[STOP] Cluster deconectat — nu s-a putut trimite stop_reid")
        emit('reid_stopped', {'message': 'Cluster offline', 'already_finished': True})

@processing_client.on('reid_stopped')
def relay_reid_stopped(data):
    logger.info(f"[RELAY] reid_stopped <- cluster: {data}")
    with _sessions_lock:
        ids_to_clear = [
            vid for vid, session in active_processing_sessions.items()
            if session.get('mode') == 'reid'
        ]
        for vid in ids_to_clear:
            active_processing_sessions.pop(vid, None)
            stopping_processing_sessions.discard(vid)
    _log_active_sessions()
    socketio.emit('reid_stopped', data)

@app.route('/process_image', methods=['POST'])
@jwt_required()
def process_image():
    data = request.get_json()
    filename = data.get('filename')
    video_id = data.get('video_id')
    request_key = _image_result_key(video_id)
    logger.info(f"[IMAGE] Cerere procesare imagine: filename={filename} video_id={video_id}")

    if not filename or not video_id:
        logger.warning(f"[IMAGE] Lipsesc filename sau video_id din cerere")
        return jsonify({"error": "Missing filename or video_id"}), 400

    video = db.session.get(Video, int(video_id))
    if not video:
        logger.error(f"[IMAGE] video_id={video_id} nu exista in DB")
        return jsonify({"error": "Video not found in DB"}), 404

    if not processing_client.connected:
        logger.warning(f"[IMAGE] Cluster deconectat la process_image pentru video_id={video_id}")
        if not connect_to_processing_server():
            return jsonify({"error": "Cluster is offline"}), 503

    logger.info(f"[IMAGE] Trimit la Cluster pentru procesare: {filename} video_id={video_id}")

    image_processing_results.pop(request_key, None)

    event = threading.Event()
    image_processing_events[request_key] = event

    processing_client.emit('process_image', {
        'filename': filename,
        'video_id': video_id
    })

    logger.debug(f"[IMAGE] Astept raspuns de la cluster (timeout=30s) pentru video_id={video_id}")
    got_result = event.wait(timeout=30)
    image_processing_events.pop(request_key, None)

    if not got_result:
        image_processing_results.pop(request_key, None)
        logger.error(f"[IMAGE] TIMEOUT dupa 30s pentru video_id={video_id} (key={request_key})")
        return jsonify({"error": "Processing timeout"}), 504

    logger.info(f"[IMAGE] Raspuns primit pentru video_id={video_id}")
    result = image_processing_results.pop(request_key)

    if result['error']:
        logger.error(f"[IMAGE] Eroare de la cluster pentru video_id={video_id}: {result['error']}")
        return jsonify({"error": result['error']}), 500

    response_data = result['data']

    if response_data.get('processed_path_minio'):
        video.processed_video_path = response_data['processed_path_minio']
        video.status = 'Completed'
        video.total_unique_people = response_data.get('people_count', 0)
        db.session.commit()
        response_data['image_url'] = f'/api/image/view/{video_id}'
        logger.info(f"[IMAGE] Imagine salvata in DB pentru video_id={video_id}: path={video.processed_video_path} persoane={video.total_unique_people}")
    else:
        video.status = 'Completed'
        video.total_unique_people = response_data.get('people_count', 0)
        db.session.commit()
        logger.info(f"[IMAGE] Imagine procesata (fara MinIO path) video_id={video_id} persoane={video.total_unique_people}")

    if 'annotated_image' in response_data:
        del response_data['annotated_image']

    return jsonify(response_data), 200

@app.route('/api/image/view/<int:video_id>')
@jwt_required()
def view_processed_image(video_id):
    current_user_id = get_jwt_identity()
    logger.debug(f"[IMAGE-VIEW] Cerere vizualizare imagine video_id={video_id} user_id={current_user_id}")

    video = Video.query.filter_by(id=video_id, user_id=current_user_id).first()
    if not video:
        logger.warning(f"[IMAGE-VIEW] video_id={video_id} nu exista sau acces refuzat pentru user_id={current_user_id}")
        return jsonify({"error": "Image not found or access denied"}), 404

    if not video.processed_video_path:
        logger.warning(f"[IMAGE-VIEW] video_id={video_id} nu are processed_video_path")
        return jsonify({"error": "Image is still being processed or failed"}), 404

    try:
        logger.debug(f"[IMAGE-VIEW] Servire imagine din MinIO: {video.processed_video_path}")
        minio_data = minio_client.get_object(BUCKET_NAME, video.processed_video_path)
        return Response(
            minio_data.read(),
            mimetype='image/jpeg',
            headers={
                "Content-Disposition": f"inline; filename={os.path.basename(video.processed_video_path)}",
                "Cache-Control": "public, max-age=3600"
            }
        )
    except Exception as e:
        logger.error(f"[IMAGE-VIEW] Eroare servire imagine din MinIO pentru video_id={video_id}: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/dashboard-stats', methods=['GET'])
@jwt_required()
def get_dashboard_stats():
    current_user_id = get_jwt_identity()
    logger.debug(f"[DASHBOARD] Cerere statistici pentru user_id={current_user_id}")
    try:
        user_videos = Video.query.filter_by(user_id=current_user_id).all()
        detection_videos = [
            video for video in user_videos
            if (video.dm_model_used or "").lower() != "tracking"
        ]
        total_people = sum(v.total_unique_people for v in detection_videos)

        # Calculăm storage total din MinIO (original + procesat + heatmap)
        storage_bytes = 0
        all_keys = []
        for v in detection_videos:
            for key in (v.minio_path, v.processed_video_path, v.heatmap_video_path):
                if key:
                    all_keys.append(key)
        for key in all_keys:
            try:
                stat = minio_client.stat_object(BUCKET_NAME, key)
                storage_bytes += stat.size
            except Exception:
                pass
        storage_mb = round(storage_bytes / (1024 * 1024), 1)

        logger.info(
            f"[DASHBOARD] user_id={current_user_id}: "
            f"{len(detection_videos)} detection videos, {total_people} persoane, {storage_mb} MB"
        )
        activity = [{
            "id": v.id, "filename": v.filename, "status": v.status,
            "people_count": v.total_unique_people, "created_at": v.created_at.isoformat()
        } for v in detection_videos[-10:]]
        return jsonify({
            "total_videos": len(detection_videos),
            "total_people": total_people,
            "storage_used": storage_mb,
            "recent_activity": activity
        }), 200
    except Exception as e:
        logger.exception(f"[DASHBOARD] Eroare la obtinerea statisticilor pentru user_id={current_user_id}: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/tracking-sessions', methods=['GET'])
@jwt_required()
def list_tracking_sessions():
    current_user_id = get_jwt_identity()
    try:
        sessions = (
            TrackingSession.query
            .filter_by(user_id=current_user_id)
            .order_by(TrackingSession.started_at.desc())
            .limit(50)
            .all()
        )
        return jsonify({
            "sessions": [session.to_dict(include_cameras=True) for session in sessions]
        }), 200
    except Exception as e:
        logger.exception(f"[REID][SESSION] Eroare listare sesiuni user_id={current_user_id}: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/tracking-sessions/<int:session_id>', methods=['GET'])
@jwt_required()
def get_tracking_session(session_id):
    current_user_id = get_jwt_identity()
    session = TrackingSession.query.filter_by(id=session_id, user_id=current_user_id).first()
    if not session:
        return jsonify({"error": "Tracking session not found"}), 404
    return jsonify(session.to_dict(include_cameras=True)), 200

@app.route('/api/tracking-sessions/<int:session_id>', methods=['DELETE'])
@jwt_required()
def delete_tracking_session(session_id):
    current_user_id = get_jwt_identity()
    tracking_session = TrackingSession.query.filter_by(id=session_id, user_id=current_user_id).first()
    if not tracking_session:
        return jsonify({"error": "Tracking session not found"}), 404
    try:
        if tracking_session.summary_json_path:
            try:
                minio_client.remove_object(BUCKET_NAME, tracking_session.summary_json_path)
            except Exception:
                pass
        db.session.delete(tracking_session)
        db.session.commit()
        logger.info(f"[REID][SESSION] Deleted session_id={session_id} user_id={current_user_id}")
        return jsonify({"message": "Deleted"}), 200
    except Exception as e:
        db.session.rollback()
        logger.exception(f"[REID][SESSION] Eroare stergere session_id={session_id}: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/videos/<int:video_id>', methods=['DELETE'])
@jwt_required()
def delete_video(video_id):
    current_user_id = get_jwt_identity()
    logger.info(f"[DELETE] Cerere stergere video_id={video_id} de la user_id={current_user_id}")
    video = Video.query.filter_by(id=video_id, user_id=current_user_id).first()
    if not video:
        logger.warning(f"[DELETE] video_id={video_id} nu exista pentru user_id={current_user_id}")
        return jsonify({"error": "Not found"}), 404
    try:
        minio_keys = [
            video.minio_path,
            video.processed_video_path,
            video.heatmap_video_path,
        ]
        for key in minio_keys:
            if key:
                try:
                    minio_client.remove_object(BUCKET_NAME, key)
                    logger.info(f"[DELETE] Sters din MinIO: {key}")
                except Exception as minio_err:
                    logger.warning(f"[DELETE] Nu s-a putut sterge din MinIO {key}: {minio_err}")
        db.session.delete(video)
        db.session.commit()
        logger.info(f"[DELETE] Video sters din DB: video_id={video_id} filename={video.filename}")
        return jsonify({"message": "Deleted"}), 200
    except Exception as e:
        db.session.rollback()
        logger.exception(f"[DELETE] Eroare la stergerea video_id={video_id}: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    _port = int(os.getenv('FLASK_PORT', 5000))
    _debug = os.getenv('FLASK_DEBUG', 'false').lower() == 'true'
    logger.info(f"[STARTUP] API Gateway pornit pe portul {_port}. Gata de delegare catre Cluster.")
    threading.Thread(target=connect_to_processing_server, daemon=True).start()
    socketio.run(app, host='0.0.0.0', use_reloader=_debug, debug=_debug, port=_port, allow_unsafe_werkzeug=True)
