import os, sys, json, time, signal, atexit, threading, subprocess, csv, uuid, inspect

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

console = Console()

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from utils.minio_client import minio_client, BUCKET_NAME, upload_file_to_minio, download_file_from_minio
from flask import Flask, request, jsonify
from flask_socketio import SocketIO, emit
from werkzeug.utils import secure_filename
from extensions import db
from models import Video, PersonLog, GlobalPerson, MultiCamLog
from io import StringIO
from queue import Queue
from concurrent.futures import ThreadPoolExecutor, as_completed

os.environ.setdefault('CUDA_VISIBLE_DEVICES', '0,1,2')

os.environ.setdefault('REID_SYNC_CAMERAS', '0')
os.environ.setdefault('REID_PROCESS_FRAME_EVERY', '3')
os.environ.setdefault('REID_YOLO_IMG_SIZE', '640')
os.environ.setdefault('REID_CONF_THRESHOLD', '0.25')
os.environ.setdefault('REID_EMIT_FRAME_EVERY', '2')
os.environ.setdefault('REID_JPEG_QUALITY', '35')
os.environ.setdefault('REID_SEND_FRAME_MAX_WIDTH', '700')
os.environ.setdefault("ENABLE_REID_EMBEDDINGS", "1")
os.environ.setdefault('REID_FRAME_SKIP', '45')
os.environ.setdefault('REID_MAX_EMBEDDINGS', '3')
os.environ.setdefault('REID_MIN_EMBEDDINGS_TO_MATCH', '2')
os.environ.setdefault('REID_RECHECK_INTERVAL', '15.0')
os.environ.setdefault('USE_SEGMENTATION_FOR_REID', '0')
os.environ.setdefault('TRACKING_PRELOAD_MAX_GPUS', '1')

YOLO_GPU_ID = 0
active_processing = {}
active_processing_lock = threading.Lock()
_reid_stop_event = None
_reid_prepare_stop_event = None
prepared_reid_jobs = {}
prepared_reid_jobs_lock = threading.Lock()

processing_queue = Queue()
queued_processing = set()

def is_stop_requested(video_key):
    state = active_processing.get(video_key)
    return bool(state and state.get('stop_requested'))

from ultralytics import YOLO
import torch
import numpy as np

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MODEL_DEFAULT = os.path.join(_BASE_DIR, "models/yolo11m_smallperson_aerial_1280.engine")
_MODEL_ENV = os.getenv("MODEL_PATH", "models/yolo11m_smallperson_aerial_1280.engine")
MODEL_PATH = _MODEL_ENV if os.path.isabs(_MODEL_ENV) else os.path.join(_BASE_DIR, _MODEL_ENV)
_gpu_count = torch.cuda.device_count()
AVAILABLE_GPUS = list(range(_gpu_count))
gpu_locks = {gid: threading.Lock() for gid in AVAILABLE_GPUS}

console.print(f"[INIT] CUDA_VISIBLE_DEVICES={os.environ.get('CUDA_VISIBLE_DEVICES', '(unset)')}", style="cyan")
console.print(f"[INIT] torch.cuda.device_count()={_gpu_count}", style="cyan")
console.print(f"[INIT] AVAILABLE_GPUS={AVAILABLE_GPUS}", style="cyan")

detection_models = {}
dummy_img = np.zeros((1280, 1280, 3), dtype=np.uint8)

console.print("[INIT] Strategie: Lazy loading YOLO models (on-demand per GPU)", style="yellow")
console.print(f"[INIT] GPU {YOLO_GPU_ID} este preferinta primara pentru YOLO", style="yellow")

GPU_POLICY = {

    "detection": {"min_free_mb": 8000, "max_util": 98},
    "crowd":     {"min_free_mb": 16000, "max_util": 95},
    "reid":      {"min_free_mb": 20000, "max_util": 90},
}

def _query_gpu_snapshot():
    """Ia lista de GPU-uri cu RAM si utilizare."""
    snapshot = []

    try:
        cmd = [
            "nvidia-smi",
            "--query-gpu=index,memory.free,utilization.gpu",
            "--format=csv,noheader,nounits",
        ]
        out = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL)
        rows = csv.reader(StringIO(out))

        visible_set = set(AVAILABLE_GPUS)
        for row in rows:
            if len(row) < 3:
                continue
            gid = int(row[0].strip())
            free_mb = int(row[1].strip())
            util = int(row[2].strip())

            if gid in visible_set:
                snapshot.append({"id": gid, "free_mb": free_mb, "util": util})

        if snapshot:
            return snapshot
    except Exception as e:
        print(f"[GPU][WARN] nvidia-smi snapshot indisponibil: {e}")

    for gid in AVAILABLE_GPUS:
        try:
            free_b, _total_b = torch.cuda.mem_get_info(gid)
            snapshot.append({
                "id": gid,
                "free_mb": int(free_b // (1024 * 1024)),
                "util": 0,
            })
        except Exception as e:
            print(f"[GPU][WARN] torch mem_get_info esuat pentru cuda:{gid}: {e}")

    return snapshot

def get_best_gpu_for_mode(mode="detection"):
    """Alege cel mai bun GPU pentru job-ul asta."""
    if not AVAILABLE_GPUS:
        return None

    policy = GPU_POLICY.get(mode, GPU_POLICY["detection"])
    snapshot = _query_gpu_snapshot()

    candidates = []
    for info in snapshot:
        gid = info["id"]
        free_mb = info["free_mb"]
        util = info["util"]

        if gid not in gpu_locks:
            continue

        if gpu_locks[gid].locked():
            continue

        if free_mb >= policy["min_free_mb"] and util <= policy["max_util"]:
            candidates.append(info)

    if not candidates:
        print(f"[GPU] Niciun GPU potrivit pentru mode={mode}. Snapshot={snapshot}")
        return None

    candidates.sort(key=lambda x: (x["free_mb"], -x["util"]), reverse=True)
    chosen = candidates[0]
    print(
        f"[GPU] Ales cuda:{chosen['id']} pentru mode={mode} "
        f"({chosen['free_mb']} MB liberi, util={chosen['util']}%)"
    )
    return chosen["id"]

def wait_for_available_gpu(mode="detection", video_id=None, poll_sec=10):
    """Asteapta pana e GPU liber pentru job."""
    video_key = str(video_id) if video_id is not None else None

    while True:
        if video_key and is_stop_requested(video_key):
            return None

        gid = get_best_gpu_for_mode(mode)
        if gid is not None:
            return gid

        if video_id is not None:
            socketio.emit("status_update", {
                "video_id": video_id,
                "msg": "⏳ Toate GPU-urile sunt ocupate. Jobul asteapta in coada..."
            })

        time.sleep(poll_sec)

def load_yolo_for_gpu(gpu_id):
    """Incarc YOLO pe GPU. Returns (model, gpu_id) sau (None, None)."""
    if gpu_id in detection_models:
        return detection_models[gpu_id], gpu_id

    try:
        print(f"[INIT] Loading model YOLO (TensorRT engine)...")
        _m = YOLO(MODEL_PATH, task='detect')
        _m.predict(dummy_img, device=gpu_id, verbose=False)
        detection_models[gpu_id] = _m
        print(f"[INIT] Model YOLO incarcat pe cuda:{gpu_id} ")
        return _m, gpu_id
    except RuntimeError as e:
        if "out of memory" in str(e):
            print(f"[INIT] WARN  GPU {gpu_id} insufficient memory")
            print(f"[INIT] Fallback to: try alt GPU...")

            fallback_order = sorted(AVAILABLE_GPUS, reverse=True)
            for fallback_gpu in fallback_order:
                if fallback_gpu == gpu_id:
                    continue
                if fallback_gpu in detection_models:
                    print(f"[INIT] Using GPU {fallback_gpu} (deja incarcat)")
                    return detection_models[fallback_gpu], fallback_gpu
                try:
                    print(f"[INIT] Incerc fallback pe GPU {fallback_gpu}...")
                    _m = YOLO(MODEL_PATH, task='detect')
                    _m.predict(dummy_img, device=fallback_gpu, verbose=False)
                    detection_models[fallback_gpu] = _m
                    print(f"[INIT] Model YOLO incarcat pe cuda:{fallback_gpu} ")
                    return _m, fallback_gpu
                except Exception:
                    continue
            print(f"[INIT] ERROR No GPU available for YOLO")
            return None, None
        else:
            raise

def _get_freest_gpu():
    """Ia GPU-ul cu cea mai multa RAM libera."""
    best_gpu, best_free = 0, -1
    for gid in AVAILABLE_GPUS:
        try:
            free_b, _ = torch.cuda.mem_get_info(gid)
            if free_b > best_free:
                best_free = free_b
                best_gpu = gid
        except Exception:
            continue
    free_mb = best_free // (1024 * 1024)
    print(f"[GPU] Cel mai liber GPU: cuda:{best_gpu} ({free_mb} MB liberi)")
    return best_gpu

def get_next_gpu():
    """Ia GPU-ul pe care e YOLO."""
    return YOLO_GPU_ID

def get_model_for_gpu(gpu_id):
    """
    Returneaza modelul YOLO pentru GPU-ul cerut.
    Daca nu este inca incarcat pe acel GPU, incearca lazy loading.
    """
    if gpu_id in detection_models:
        return detection_models[gpu_id]

    _m, effective_gpu = load_yolo_for_gpu(gpu_id)
    if _m is None:
        return None

    if effective_gpu != gpu_id:
        print(f"[WARN] Modelul YOLO nu a putut fi incarcat pe cuda:{gpu_id}; folosesc cuda:{effective_gpu}")

    return _m

_freest_at_start = _get_freest_gpu()
try:
    _m, _effective_gpu = load_yolo_for_gpu(_freest_at_start)
    if _m is None:
        print(f"[INIT] ERROR ERROR: Cannot load YOLO pe niciun GPU!")
        sys.exit(1)
    YOLO_GPU_ID = _effective_gpu
    print(f"[INIT]  YOLO preloaded pe GPU {_effective_gpu} (cel mai liber la startup)")
except Exception as e:
    print(f"[INIT] ERROR ERROR: {e}")
    sys.exit(1)

model = detection_models.get(YOLO_GPU_ID)

try:
    from inference.dmcount_inference import get_dmcount
    print("[INIT] dmcount_inference pre-incarcat cu succes.")
    print("[INIT] Preload model DM-Count QNRF...")
    get_dmcount(device="cuda:0", model_name="qnrf")
    print("[INIT] Preload model DM-Count NWPU...")
    get_dmcount(device="cuda:0", model_name="nwpu")
    print("[INIT]  Ambele modele DM-Count incarcate si cached.")
except Exception as e:
    print(f"[INIT] [WARN] dmcount_inference indisponibil: {e}")

try:
    from inference.yolo_inference import process_video_stream, validate_video_file
    print("[INIT] yolo_inference importat cu succes.")
except ImportError as e:
    print(f"[CRITICAL] Nu s-a putut importa yolo_inference: {e}")
    sys.exit(1)

try:
    from inference.crowd_inference import process_crowd_stream
    print("[INIT] crowd_inference importat cu succes.")
except ImportError as e:
    print(f"[INIT] [WARN] crowd_inference indisponibil: {e}")
    process_crowd_stream = None

try:
    from inference.tracking_inference import process_reid_multicamera, preload_all_models, get_tracking_gpu_ids
    console.print("[INIT]  tracking_inference importat cu succes.", style="green")
except ImportError as e:
    console.print(f"[INIT] WARN  tracking_inference indisponibil: {e}", style="red")
    process_reid_multicamera = None
    preload_all_models = None
    get_tracking_gpu_ids = None

if preload_all_models is not None:
    console.print("[INIT] Pre-incarcare modele tracking pe toate GPU-urile...", style="cyan")
    try:
        preload_ok = preload_all_models()
        if preload_ok:
            loaded_gpus = get_tracking_gpu_ids() if get_tracking_gpu_ids else []
            console.print(f"[INIT]  Modele tracking preloadede pe GPU: {loaded_gpus}", style="green")
        else:
            console.print("[INIT] WARN  Modelele tracking au fost incarcate partial; verifica logurile [TRACKING].", style="yellow")
    except Exception as e:
        console.print(f"[INIT] WARN  Pre-incarcare tracking esuata: {e}", style="red")

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv(
    'DATABASE_URL', 'postgresql://admin:parola_sigura@127.0.0.1:5433/licenta_db'
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode='threading',
    max_http_buffer_size=150*1024*1024,
    ping_timeout=120,
    ping_interval=25
)

import logging
logging.getLogger('werkzeug').setLevel(logging.ERROR)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
RESULTS_FOLDER = os.path.join(BASE_DIR, "results")
KEEP_REID_CACHE = os.getenv("KEEP_REID_CACHE", "1") == "1"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(RESULTS_FOLDER, exist_ok=True)

@app.route("/api/input/upload", methods=["POST"])
def upload_input_file():
    file = request.files.get("video")
    filename = request.form.get("filename")

    if not file or not filename:
        return jsonify({"error": "Missing video or filename"}), 400

    safe_filename = secure_filename(filename)
    if not safe_filename:
        return jsonify({"error": "Invalid filename"}), 400

    target_path = os.path.join(UPLOAD_FOLDER, safe_filename)
    temp_path = f"{target_path}.part"

    try:
        file.save(temp_path)
        if not os.path.exists(temp_path) or os.path.getsize(temp_path) <= 1024:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            return jsonify({"error": "Uploaded file is empty or too small"}), 400
        os.replace(temp_path, target_path)
        print(f"[INPUT-UPLOAD] Primit direct de la backend: {safe_filename} -> {target_path}")
        return jsonify({
            "message": "Uploaded to cluster",
            "filename": safe_filename,
            "size": os.path.getsize(target_path),
        }), 201
    except Exception as exc:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass
        print(f"[INPUT-UPLOAD][ERROR] {safe_filename}: {exc}")
        return jsonify({"error": str(exc)}), 500

def normalize_mode(mode):
    mode_norm = str(mode).strip().lower() if mode is not None else ''
    if mode_norm in ('crowd', 'dmcount', 'qnrf', 'nwpu'):
        return 'crowd'
    if mode_norm in ('tracking', 'reid'):
        return 'tracking'
    return 'detection'

def normalize_dm_model(dm_model):
    dm_norm = str(dm_model).strip().lower() if dm_model is not None else ''
    return dm_norm if dm_norm in ('qnrf', 'nwpu') else 'qnrf'

def update_video_status(video_id, status):
    if str(video_id).startswith('live_'):
        return
    try:
        with app.app_context():
            video = db.session.get(Video, int(video_id))
            if video:
                video.status = status
                db.session.commit()
                print(f"[DB] Status actualizat: Video {video_id} -> {status}")
    except Exception as e:
        print(f"[DB ERROR] {e}")

def save_results_to_db(video_id, stats, processed_video_path=None, heatmap_video_path=None):
    if str(video_id).startswith('live_'):
        return
    print(f"[DB] Saving final results for video_id={video_id}...")
    try:
        with app.app_context():
            video = db.session.get(Video, int(video_id))
            if video:
                video.status = 'Completed'

                video.total_unique_people = (
                    stats.get('unique_people') or stats.get('max_people_in_frame', 0)
                )
                if processed_video_path:
                    video.processed_video_path = processed_video_path
                if heatmap_video_path:
                    video.heatmap_video_path = heatmap_video_path
                if 'max_people_in_frame' in stats:
                    video.max_people_in_frame = stats['max_people_in_frame']
                if 'avg_people_per_frame' in stats:
                    video.avg_people_per_frame = stats['avg_people_per_frame']

                if stats.get('dm_model_used'):
                    video.dm_model_used = stats['dm_model_used']
            analytics_data = stats.get('analytics_data', {})
            fps = stats.get('fps', 30)
            dwell_times = []
            for track_id, info in analytics_data.items():
                start = info.get('start_frame')
                end = info.get('end_frame')
                if start is not None and end is not None and end > start:
                    dwell_times.append((end - start) / fps)
                log = PersonLog(
                    video_id=int(video_id),
                    track_id=int(track_id),
                    start_frame=start,
                    end_frame=end,
                    path_data=json.dumps(info.get('path', []))
                )
                db.session.add(log)
            if dwell_times and video:
                video.avg_dwell_time_sec = round(sum(dwell_times) / len(dwell_times), 2)
            db.session.commit()
            print(f"[DB] Final results saved successfully for video_id={video_id}.")
    except Exception as e:
        print(f"[DB ERROR] {e}")

@socketio.on('connect')
def handle_connect():
    print(f"[SOCKET] API Gateway conectat la Cluster.")

@socketio.on('stop_processing')
def handle_stop_processing(data):
    video_id = data.get('video_id') if isinstance(data, dict) else None
    if not video_id:
        emit('status_update', {'msg': 'ERROR Eroare: lipseste video_id pentru oprire.'})
        return

    video_key = str(video_id)
    state = active_processing.get(video_key)

    if state:
        state['stop_requested'] = True
        print(f"[STOP] Semnal stop marcat pentru video_id={video_id}")
        source_handle = state.get('source_handle')
        is_stream = state.get('is_stream_source', False)
        is_live = state.get('is_live', False)
        if is_stream and source_handle is not None:
            try:
                source_handle.terminate()
                try:
                    source_handle.wait(timeout=2)
                except Exception:
                    source_handle.kill()
                print(f"[STOP] Subprocess ffmpeg oprit fortat pentru video_id={video_id}")
            except Exception as e:
                print(f"[STOP] Eroare la terminarea subprocess: {e}")
        emit('status_update', {
            'msg': f' Oprire solicitata pentru video_id={video_id}.'
        })
        if is_live:
            update_video_status(video_id, 'Stopped')
            emit('processing_stopped', {
                'video_id': video_id,
                'status': 'Stopped',
                'is_live': True
            })
            print(f"[STOP] processing_stopped emis imediat pentru live video_id={video_id}")
    else:
        emit('processing_stopped', {'video_id': video_id, 'status': 'Stopped', 'already_finished': True})
        print(f"[STOP] video_id={video_id} nu este activ; probabil deja finalizat")

@socketio.on('stop_reid')
def handle_stop_reid(data):
    global _reid_stop_event, _reid_prepare_stop_event
    stopped_any = False
    if _reid_stop_event is not None:
        _reid_stop_event.set()
        print("[STOP] Semnal stop trimis catre thread-ul Re-ID.")
        stopped_any = True
    if _reid_prepare_stop_event is not None:
        _reid_prepare_stop_event.set()
        print("[STOP] Semnal stop trimis catre pregatirea Re-ID.")
        stopped_any = True
    with prepared_reid_jobs_lock:
        prepared_reid_jobs.clear()
    if stopped_any:
        emit('status_update', {'msg': 'Oprire Re-ID solicitata...'})
    else:
        emit('reid_stopped', {'message': 'Re-ID nu era activ.', 'already_finished': True})
        print("[STOP] stop_reid primit dar Re-ID nu era activ.")

def _queue_position(video_key):
    try:
        with processing_queue.mutex:
            items = list(processing_queue.queue)
        keys = [str(item.get("video_id")) for item in items]
        return keys.index(str(video_key)) + 1 if str(video_key) in keys else None
    except Exception:
        return None

def processing_worker():
    """Consuma joburi din coada si le ruleaza cand exista GPU liber."""
    print("[QUEUE] Worker procesare pornit.")

    while True:
        data = processing_queue.get()
        video_id = data.get("video_id")
        video_key = str(video_id)

        try:
            with active_processing_lock:
                queued_processing.discard(video_key)

            if is_stop_requested(video_key):
                print(f"[QUEUE] Job video_id={video_id} a fost oprit inainte de pornire.")
                update_video_status(video_id, "Stopped")
                socketio.emit("processing_stopped", {
                    "video_id": video_id,
                    "status": "Stopped",
                    "already_finished": False,
                    "stopped_while_queued": True,
                })
                with active_processing_lock:
                    active_processing.pop(video_key, None)
                continue

            # Folosim modul curent din active_processing daca userul l-a schimbat cat timp jobul era queued.
            queued_state = active_processing.get(video_key, {})
            mode = queued_state.get("mode") or normalize_mode(data.get("mode"))

            assigned_gpu = wait_for_available_gpu(mode=mode, video_id=video_id)
            if assigned_gpu is None:
                update_video_status(video_id, "Stopped")
                socketio.emit("processing_stopped", {
                    "video_id": video_id,
                    "status": "Stopped",
                    "stopped_while_waiting_gpu": True,
                })
                with active_processing_lock:
                    active_processing.pop(video_key, None)
                continue

            with gpu_locks[assigned_gpu]:
                run_processing_job(data, assigned_gpu=assigned_gpu)

        except Exception as e:
            print(f"[QUEUE][ERROR] Job video_id={video_id} a esuat in worker: {e}")
            socketio.emit("status_update", {
                "video_id": video_id,
                "msg": f"ERROR Eroare worker procesare: {str(e)}"
            })
            update_video_status(video_id, "Error")
            with active_processing_lock:
                active_processing.pop(video_key, None)
        finally:
            processing_queue.task_done()

@socketio.on('start_processing')
def handle_start_processing(data):
    """
    Nu procesam direct in handler. Punem jobul in coada, iar worker-ul il ruleaza cand are GPU.
    """
    if not isinstance(data, dict):
        emit('status_update', {'msg': 'ERROR Eroare: payload invalid pentru procesare.'})
        return

    video_id = data.get('video_id')
    if not video_id:
        emit('status_update', {'msg': 'ERROR Eroare: lipseste video_id.'})
        return

    video_key = str(video_id)
    stream_url = data.get('stream_url')
    filename = data.get('filename')
    initial_mode = normalize_mode(data.get('mode'))
    initial_dm_model = normalize_dm_model(data.get('dm_model'))
    if initial_mode != 'crowd':
        initial_dm_model = None

    if not stream_url and not filename:
        emit('status_update', {'msg': 'ERROR Eroare: Trebuie furnizat fie un URL de stream fie un nume de fisier.'})
        return

    with active_processing_lock:
        if video_key in active_processing or video_key in queued_processing:
            pos = _queue_position(video_key)
            emit('status_update', {
                'video_id': video_id,
                'msg': f'ℹ Jobul este deja activ sau in coada.' + (f' Pozitie coada: {pos}.' if pos else '')
            })
            return

        active_processing[video_key] = {
            'mode': initial_mode,
            'dm_model': initial_dm_model,
            'stop_requested': False,
            'is_live': bool(stream_url),
            'gpu_id': None,
            'queued': True,
        }
        queued_processing.add(video_key)

    # Nu actualizam DB cu status 'Queued' ca sa nu rupem schema daca statusurile sunt validate strict.
    # Statusul real devine 'Processing' cand worker-ul porneste jobul.
    processing_queue.put(dict(data))
    pos = _queue_position(video_key)

    emit('status_update', {
        'video_id': video_id,
        'msg': f' Job adaugat in coada de procesare.' + (f' Pozitie: {pos}.' if pos else '')
    })

def run_processing_job(data, assigned_gpu=None):
    video_id = data.get('video_id')
    video_key = str(video_id)
    stream_url = data.get('stream_url')
    filename = data.get('filename')
    initial_mode = normalize_mode(data.get('mode'))
    initial_dm_model = normalize_dm_model(data.get('dm_model'))

    # Daca modul a fost actualizat cat timp jobul era in coada, folosim starea curenta.
    existing_state = active_processing.get(video_key, {})
    if existing_state.get('mode'):
        initial_mode = existing_state.get('mode')
    if existing_state.get('dm_model'):
        initial_dm_model = existing_state.get('dm_model')

    if initial_mode != 'crowd':
        initial_dm_model = None

    print("\n" + "="*50)

    if not stream_url and not filename:
        socketio.emit('status_update', {'msg': 'ERROR Eroare: Trebuie furnizat fie un URL de stream fie un nume de fisier.'})
        return

    if stream_url:
        video_path = stream_url
        print(f"[START] LIVE: {stream_url} | mode={initial_mode}" + (f" | dm_model={initial_dm_model}" if initial_mode == 'crowd' else " | model=YOLO"))
        socketio.emit('status_update', {'msg': '📡 Conectare la fluxul video live...'})
    else:
        video_path = os.path.join(UPLOAD_FOLDER, filename)
        print(f"[START] FILE: {filename} | mode={initial_mode}")
        socketio.emit('status_update', {'msg': f'Cerere primita pentru: {filename}'})

    # GPU-ul este ales de worker. Daca functia e apelata direct, alegem unul aici.
    if assigned_gpu is None:
        assigned_gpu = wait_for_available_gpu(mode=initial_mode, video_id=video_id)
        if assigned_gpu is None:
            socketio.emit('status_update', {'video_id': video_id, 'msg': ' Procesare oprita inainte de alocarea GPU.'})
            update_video_status(video_id, 'Stopped')
            return

    previous_state = active_processing.get(video_key, {})
    if previous_state.get('stop_requested'):
        update_video_status(video_id, 'Stopped')
        socketio.emit('processing_stopped', {'video_id': video_id, 'status': 'Stopped', 'stopped_while_queued': True})
        return

    with active_processing_lock:
        active_processing[video_key] = {
            'mode': initial_mode,
            'dm_model': initial_dm_model,
            'stop_requested': False,
            'is_live': bool(stream_url),
            'gpu_id': assigned_gpu,
            'queued': False,
        }
    print(f"[GPU] Video {video_id} asignat la cuda:{assigned_gpu}")

    socketio.sleep(0.01)

    if not stream_url:
        cached_ok = os.path.exists(video_path) and os.path.getsize(video_path) > 1024
        from_cache = cached_ok

        def progress_callback(bytes_dl, total_bytes):
            if is_stop_requested(video_key):
                raise RuntimeError("Stop requested during download")
            percent = (bytes_dl / total_bytes) * 100 if total_bytes else 0
            if int(percent) % 20 == 0:
                socketio.emit('status_update', {'msg': f'Descarcare: {percent:.0f}%'})
                socketio.sleep(0.01)

        def do_minio_download(label=""):
            if os.path.exists(video_path):
                os.remove(video_path)
            tag = f" ({label})" if label else ""
            print(f"[MINIO] Descarcare din MinIO{tag}: {filename}")
            socketio.emit('status_update', {'msg': f'Se descarca clipul din stocarea MinIO{tag}...'})
            with app.app_context():
                video_obj = db.session.get(Video, int(video_id))
                if not video_obj:
                    raise Exception(f"Video ID {video_id} negasit in DB")
                if not video_obj.minio_path:
                    raise Exception("Fisierul nu exista local pe cluster si video-ul nu are minio_path pentru fallback")
                success = download_file_from_minio(video_obj.minio_path, video_path,
                                                   progress_callback=progress_callback)
                if not success:
                    raise Exception("Download MinIO esuat")
            print(f"[MINIO] Download complet pentru {filename}")

        if not cached_ok:
            try:
                do_minio_download()
            except Exception as e:
                print(f"[MINIO ERROR] {e}")
                if is_stop_requested(video_key):
                    update_video_status(video_id, 'Stopped')
                    socketio.emit('processing_stopped', {'video_id': video_id, 'status': 'Stopped', 'is_live': False})
                else:
                    socketio.emit('status_update', {'msg': 'Eroare la descarcarea din MinIO!'})
                    update_video_status(video_id, 'Error')
                return
        else:
            print(f"[INFO] Fisierul {filename} gasit in cache local ({os.path.getsize(video_path)/(1024*1024):.1f} MB).")
            socketio.emit('status_update', {'msg': 'Fisier gasit in cache local.'})

        # Validare integritate — detecteaza moov atom lipsa, HEVC corupt etc.
        valid, reason = validate_video_file(video_path)
        if valid is False:
            if from_cache:
                print(f"[CACHE] Fisier corupt in cache — {reason}. Sterg si re-descarc din MinIO...")
                socketio.emit('status_update', {'msg': 'Cache corupt. Re-descarcare din MinIO...'})
                try:
                    do_minio_download(label="re-download")
                except Exception as e:
                    print(f"[MINIO ERROR] Re-download: {e}")
                    socketio.emit('status_update', {'msg': 'Eroare la re-descarcarea din MinIO!'})
                    update_video_status(video_id, 'Error')
                    return
                valid2, reason2 = validate_video_file(video_path)
                if valid2 is False:
                    print(f"[EROARE] Fisier corupt si dupa re-download: {reason2}")
                    socketio.emit('status_update', {'msg': f'Fisier corupt si dupa re-descarcare: {reason2}'})
                    update_video_status(video_id, 'Error')
                    if os.path.exists(video_path):
                        os.remove(video_path)
                    return
            else:
                print(f"[EROARE] Fisier corupt dupa download: {reason}")
                socketio.emit('status_update', {'msg': f'Fisier corupt: {reason}'})
                update_video_status(video_id, 'Error')
                if os.path.exists(video_path):
                    os.remove(video_path)
                return

    if is_stop_requested(video_key):
        update_video_status(video_id, 'Stopped')
        socketio.emit('processing_stopped', {'video_id': video_id, 'status': 'Stopped', 'is_live': bool(stream_url)})
        return

    if not stream_url:
        update_video_status(video_id, 'Processing')

    try:
        socketio.emit('status_update', {'msg': 'Analiza AI in curs...'})
        if initial_mode == 'crowd':
            socketio.emit('status_update', {'msg': f'Mod activ: DM-Count ({initial_dm_model.upper()})'})
        else:
            socketio.emit('status_update', {'msg': 'Mod activ: YOLO detection'})

        if initial_mode == 'crowd' and process_crowd_stream is not None:
            print(f"[START] Pipeline: CROWD (DM-Count {initial_dm_model.upper()})")
            stats = process_crowd_stream(
                video_path,
                RESULTS_FOLDER,
                socketio,
                video_id,
                processing_state=active_processing[video_key]
            )
        else:
            gpu_id = active_processing[video_key].get('gpu_id', YOLO_GPU_ID)

            # ── FIX: foloseste get_model_for_gpu in loc de detection_models.get() ──
            det_model = get_model_for_gpu(gpu_id)

            if det_model is None:
                raise RuntimeError(
                    f"Modelul YOLO nu este disponibil pe niciun GPU. "
                    f"GPU-uri cu modele: {list(detection_models.keys())}"
                )

            print(f"[START] Pipeline: DETECTION (YOLO) pe cuda:{gpu_id}")
            stats = process_video_stream(
                video_path,
                RESULTS_FOLDER,
                socketio,
                video_id,
                det_model,
                processing_state=active_processing[video_key]
            )

        if "error" in stats:
            raise Exception(stats["error"])

        if stats.get('stopped') or is_stop_requested(video_key):
            update_video_status(video_id, 'Stopped')
            socketio.emit('processing_stopped', {'video_id': video_id, 'status': 'Stopped', 'is_live': bool(stream_url)})
            print(f"[STOP] Procesare oprita pentru ID: {video_id}")
            return

        processed_filename = stats.get('processed_filename')
        processed_heatmap_filename = stats.get('processed_heatmap_filename')
        minio_video_path = None
        minio_heatmap_path = None

        if processed_filename and not stream_url:
            local_res_path = os.path.join(RESULTS_FOLDER, processed_filename)
            socketio.emit('status_update', {'msg': 'Se salveaza rezultatele in stocare...'})

            with app.app_context():
                video = db.session.get(Video, int(video_id))
                if not video:
                    raise Exception(f"Video ID {video_id} nu mai exista in DB")
                if video.user_id is None:
                    raise Exception(f"Video ID {video_id} are user_id NULL")

                minio_key = f"processed/user_{video.user_id}/video_{video_id}/{processed_filename}"
                print(f"[MINIO] Uploading processed video for video_id={video_id} -> {minio_key}")
                if upload_file_to_minio(local_res_path, minio_key):
                    minio_video_path = minio_key
                    print(f"[MINIO] Processed video upload succeeded for video_id={video_id}")
                    if os.path.exists(local_res_path):
                        os.remove(local_res_path)
                else:
                    print(f"[MINIO ERROR] Processed video upload failed for video_id={video_id}")
                    raise Exception("Processed video upload failed")

                if processed_heatmap_filename:
                    local_h_path = os.path.join(RESULTS_FOLDER, processed_heatmap_filename)
                    h_minio_key = f"processed/user_{video.user_id}/video_{video_id}/{processed_heatmap_filename}"
                    if not os.path.exists(local_h_path):
                        print(f"[MINIO WARN] Heatmap file not found for video_id={video_id}: {local_h_path}")
                        socketio.emit('status_update', {
                            'msg': 'Heatmap output was requested but file is missing on server.'
                        })
                    else:
                        print(f"[MINIO] Uploading heatmap video for video_id={video_id} -> {h_minio_key}")
                        if upload_file_to_minio(local_h_path, h_minio_key):
                            minio_heatmap_path = h_minio_key
                            print(f"[MINIO] Heatmap video upload succeeded for video_id={video_id}")
                            if os.path.exists(local_h_path):
                                os.remove(local_h_path)
                        else:
                            print(f"[MINIO WARN] Heatmap upload failed for video_id={video_id}")
                            socketio.emit('status_update', {
                                'msg': 'Heatmap upload failed. Processed video is available without heatmap.'
                            })
                else:
                    print(f"[PIPELINE] No heatmap file generated for video_id={video_id}")

        if initial_mode == 'crowd':
            stats['dm_model_used'] = initial_dm_model

        save_results_to_db(video_id, stats, minio_video_path, minio_heatmap_path)
        socketio.emit('status_update', {'msg': 'Procesare finalizata (100%).'})
        socketio.emit('processing_complete', {
            'video_id': video_id,
            'status': 'Completed',
            'processed_filename': processed_filename,
            'processed_heatmap_filename': processed_heatmap_filename,
            'processed_video_path': minio_video_path,
            'heatmap_video_path': minio_heatmap_path,
            'mode': initial_mode,
            'dm_model': initial_dm_model,
            'is_live': bool(stream_url),
            # Statistici pentru frontend (afisare imediata fara re-fetch DB)
            'unique_people': stats.get('unique_people') or stats.get('max_people_in_frame', 0),
            'max_people_in_frame': stats.get('max_people_in_frame', 0),
            'avg_people_per_frame': stats.get('avg_people_per_frame', 0),
            'processing_time': stats.get('processing_time', 0),
            'resolution': stats.get('resolution', ''),
        })
        print(f"[FINISH] Procesare incheiata pentru ID: {video_id}")

    except Exception as e:
        print(f"[CRITICAL ERROR] {e}")
        if is_stop_requested(video_key):
            update_video_status(video_id, 'Stopped')
            socketio.emit('processing_stopped', {'video_id': video_id, 'status': 'Stopped', 'is_live': bool(stream_url)})
        else:
            socketio.emit('status_update', {'msg': f'ERROR Eroare: {str(e)}'})
            update_video_status(video_id, 'Error')

    finally:
        active_processing.pop(video_key, None)
        if not stream_url and video_path and os.path.exists(video_path):
            os.remove(video_path)
            print(f"[CLEANUP] Fisier sursa sters.")
        print("="*50 + "\n")

@socketio.on('update_mode')
def handle_update_mode(data):
    video_id = data.get('video_id')
    video_key = str(video_id)
    new_mode = normalize_mode(data.get('mode'))
    new_dm_model = normalize_dm_model(data.get('dm_model'))

    if video_key in active_processing:
        active_processing[video_key]['mode'] = new_mode
        active_processing[video_key]['dm_model'] = new_dm_model
        print(f"[SOCKET] Mod actualizat pentru Video {video_id}: mode={new_mode} | dm_model={new_dm_model}")

def prepare_reid_camera_file(info, emit_fn=None, progress_event="warmup_status", stop_event=None):
    local_path = os.path.join(UPLOAD_FOLDER, info['filename'])
    camera_name = info['camera_name']

    def emit_progress(status, percent, message, bytes_downloaded=0, total_bytes=0):
        if not emit_fn:
            return
        if progress_event == "reid_prepare_status":
            emit_fn("reid_prepare_status", {
                "video_id": info.get("video_id"),
                "camera_name": camera_name,
                "status": status,
                "percent": percent,
                "message": message,
            })
        else:
            emit_fn("warmup_status", {
                "status": "download_bytes",
                "camera_name": camera_name,
                "percent": percent,
                "bytes_downloaded": bytes_downloaded,
                "total_bytes": total_bytes,
                "message": message,
            })

    if stop_event is not None and stop_event.is_set():
        return {
            **info,
            'video_path': local_path,
            'ok': False,
            'from_cache': False,
            'stopped': True,
            'error': f"Pregatire oprita pentru {camera_name}",
        }

    if os.path.exists(local_path) and os.path.getsize(local_path) > 1024:
        cached_size = os.path.getsize(local_path)
        emit_progress(
            "ready",
            100,
            f"{camera_name}: fisier gasit in cache local",
            cached_size,
            cached_size,
        )
        return {
            **info,
            'video_path': local_path,
            'ok': True,
            'from_cache': True,
            'error': None,
        }

    def progress_callback(bytes_dl, total_bytes):
        if stop_event is not None and stop_event.is_set():
            raise RuntimeError("Stop requested during Re-ID prepare")
        percent = round((bytes_dl / total_bytes) * 100) if total_bytes else 0
        emit_progress(
            "downloading",
            percent,
            f"{camera_name}: download {percent}%",
            bytes_dl,
            total_bytes,
        )

    print(f"[REID][DOWNLOAD] Start: {camera_name} -> {info['filename']}")
    if not info.get('minio_path'):
        emit_progress("error", 0, f"{camera_name}: fisierul nu exista local si nu are fallback MinIO")
        return {
            **info,
            'video_path': local_path,
            'ok': False,
            'from_cache': False,
            'error': f"{camera_name}: fisierul nu exista local si nu are fallback MinIO",
        }

    success = download_file_from_minio(
        info['minio_path'],
        local_path,
        progress_callback=progress_callback
    )

    if not success:
        emit_progress("error", 0, f"Download esuat pentru {camera_name}")
        return {
            **info,
            'video_path': local_path,
            'ok': False,
            'from_cache': False,
            'error': f"Download esuat pentru {camera_name}",
        }

    emit_progress(
        "ready",
        100,
        f"{camera_name}: ready on cluster",
        os.path.getsize(local_path) if os.path.exists(local_path) else 0,
        os.path.getsize(local_path) if os.path.exists(local_path) else 0,
    )

    return {
        **info,
        'video_path': local_path,
        'ok': True,
        'from_cache': False,
        'error': None,
    }

@socketio.on('prepare_reid')
def handle_prepare_reid(data):
    global _reid_prepare_stop_event
    cameras_data = data.get('cameras', []) if isinstance(data, dict) else []
    if not cameras_data:
        emit('error', {'message': 'No cameras provided for Re-ID prepare'})
        return

    if get_tracking_gpu_ids is not None:
        gpu_assignment = get_tracking_gpu_ids()
    else:
        gpu_assignment = list(range(torch.cuda.device_count()))

    if not gpu_assignment:
        socketio.emit('error', {'message': 'Nu exista GPU-uri cu modele tracking incarcate pentru Re-ID'})
        return

    print(f"[REID][PREPARE] Pregatesc {len(cameras_data)} camere pentru Re-ID/live tracking")
    _reid_prepare_stop_event = threading.Event()
    prepare_stop_event = _reid_prepare_stop_event

    cam_infos = []
    with app.app_context():
        for i, cam_info in enumerate(cameras_data):
            video_id = cam_info.get('video_id')
            camera_name = cam_info.get('camera_name', f'Camera {i+1}')
            if not video_id:
                continue
            video = db.session.get(Video, int(video_id))
            if not video:
                socketio.emit("reid_prepare_status", {
                    "video_id": video_id,
                    "camera_name": camera_name,
                    "status": "error",
                    "percent": 0,
                    "message": f"Video ID {video_id} nu exista in DB",
                })
                continue
            cam_infos.append({
                'video_id':     str(video_id),
                'camera_name':  camera_name,
                'camera_order': cam_info.get('camera_order', i + 1),
                'filename':     video.filename,
                'minio_path':   video.minio_path,
                'gpu_id':       gpu_assignment[i % len(gpu_assignment)],
            })

    prepared = []
    max_download_workers = min(len(cam_infos), 4)
    with ThreadPoolExecutor(max_workers=max_download_workers) as executor:
        futures = {
            executor.submit(prepare_reid_camera_file, info, socketio.emit, "reid_prepare_status", prepare_stop_event): info
            for info in cam_infos
        }
        for future in as_completed(futures):
            if prepare_stop_event.is_set():
                socketio.emit('reid_stopped', {'message': 'Pregatire Re-ID oprita de utilizator.'})
                _reid_prepare_stop_event = None
                return
            result = future.result()
            if result.get('stopped'):
                socketio.emit('reid_stopped', {'message': result.get('error', 'Pregatire Re-ID oprita.')})
                _reid_prepare_stop_event = None
                return
            if result['ok']:
                prepared.append(result)
            else:
                socketio.emit("reid_prepare_status", {
                    "video_id": result.get("video_id"),
                    "camera_name": result.get("camera_name"),
                    "status": "error",
                    "percent": 0,
                    "message": result.get("error", "Eroare pregatire camera"),
                })

    if len(prepared) != len(cam_infos):
        socketio.emit('error', {
            'message': f'Pregatire Re-ID incompleta: {len(prepared)}/{len(cam_infos)} camere.'
        })
        _reid_prepare_stop_event = None
        return

    prepared_cameras = [
        {
            'video_id':     info['video_id'],
            'camera_name':  info['camera_name'],
            'camera_order': info['camera_order'],
            'video_path':   info['video_path'],
            'gpu_id':       info['gpu_id'],
        }
        for info in sorted(prepared, key=lambda x: x.get('camera_order', 1))
    ]
    prepared_cameras_light = [
        {
            'video_id':     cam['video_id'],
            'camera_name':  cam['camera_name'],
            'camera_order': cam.get('camera_order'),
        }
        for cam in prepared_cameras
    ]
    job_id = uuid.uuid4().hex
    with prepared_reid_jobs_lock:
        prepared_reid_jobs[job_id] = prepared_cameras
    _reid_prepare_stop_event = None

    socketio.emit("reid_ready_to_start", {
        "job_id": job_id,
        "cameras": prepared_cameras_light,
        "message": "Toate camerele sunt gata pe cluster.",
    })
    print(f"[REID][PREPARE] Job pregatit: {job_id} ({len(prepared_cameras)} camere)")

def make_reid_emit_fn(job_id=None, emit_live_events=True):
    # Evenimente live/interactive. Daca API Gateway a cerut emit_live_events=False,
    # le suprimam ca sa pastram compatibilitatea cu comportamentul anterior.
    live_events = {
        'reid_frame_detections',
        'person_crop',
        'reid_update',
        'reid_config',
        'reid_embedding_update',
        'reid_embedding_skip',
        'reid_final_summary',
    }

    def emit_reid_event(event, data):
        if event in live_events and not emit_live_events:
            return
        payload = dict(data or {})
        if job_id:
            payload['job_id'] = job_id
        socketio.emit(event, payload)

    return emit_reid_event

def call_process_reid_multicamera(cameras, socketio_obj, emit_fn, results_folder,
                                  stop_event=None, runtime_config=None):
    """
    Apeleaza pipeline-ul Re-ID si paseaza runtime_config doar daca versiunea curenta
    de tracking_inference.py accepta parametrul. Astfel, processing_server.py ramane
    functional pana cand tracking_inference.py este actualizat in pasul urmator.
    """
    kwargs = {
        'cameras': cameras,
        'socketio_obj': socketio_obj,
        'emit_fn': emit_fn,
        'results_folder': results_folder,
        'stop_event': stop_event,
    }

    if runtime_config:
        try:
            sig = inspect.signature(process_reid_multicamera)
            if 'runtime_config' in sig.parameters:
                kwargs['runtime_config'] = runtime_config
                print("[REID][CONFIG] Passing runtime_config to tracking_inference.py:", runtime_config)
            else:
                print(
                    "[REID][CONFIG][WARN] tracking_inference.py nu accepta inca runtime_config; "
                    "configul a fost primit de cluster, dar nu va avea efect pana actualizezi tracking_inference.py."
                )
        except (TypeError, ValueError) as sig_err:
            print(f"[REID][CONFIG][WARN] Nu pot inspecta semnatura process_reid_multicamera: {sig_err}.")
            print("[REID][CONFIG][WARN] Rulez fara runtime_config pentru compatibilitate.")

    return process_reid_multicamera(**kwargs)

def launch_reid_processing(cameras, save_to_db, reid_event_ref, job_id=None, emit_live_events=True, reid_config=None):
    def run_reid():
        global _reid_stop_event
        try:
            result = call_process_reid_multicamera(
                cameras=cameras,
                socketio_obj=socketio,
                emit_fn=make_reid_emit_fn(job_id=job_id, emit_live_events=emit_live_events),
                results_folder=RESULTS_FOLDER,
                stop_event=reid_event_ref,
                runtime_config=reid_config,
            )
            was_stopped = reid_event_ref.is_set()
            global_people = result.get('global_people', {})

            if was_stopped:
                print(f"[REID] Oprit de utilizator dupa {len(global_people)} persoane procesate.")
                socketio.emit('reid_stopped', {'message': 'Re-ID oprit de utilizator.'})
                return

            if save_to_db:
                try:
                    socketio.emit('warmup_status', {
                        'job_id': job_id,
                        'status': 'db_save_start',
                        'message': 'Se salveaza rezultatele Re-ID in baza de date...'
                    })
                    with app.app_context():
                        for gid_str, info in global_people.items():
                            gid = int(gid_str)
                            existing = GlobalPerson.query.filter_by(global_id=gid).first()
                            if not existing:
                                existing = GlobalPerson(global_id=gid)
                                db.session.add(existing)
                                db.session.flush()
                            for cam_name in info.get('cameras', []):
                                vid_id = next(
                                    (int(c['video_id']) for c in cameras if c['camera_name'] == cam_name),
                                    None
                                )
                                if vid_id:
                                    db.session.add(MultiCamLog(
                                        global_person_id=existing.id,
                                        video_id=vid_id,
                                        camera_name=cam_name,
                                    ))
                        db.session.commit()
                    socketio.emit('warmup_status', {
                        'job_id': job_id,
                        'status': 'db_save_complete',
                        'message': f'Salvate {len(global_people)} persoane globale in baza de date.'
                    })
                    print(f"[REID][DB] Salvate {len(global_people)} persoane globale.")
                except Exception as db_err:
                    print(f"[REID][DB ERROR] {db_err}")
                    socketio.emit('error', {'message': f'Eroare salvare DB Re-ID: {str(db_err)}'})
                    return
            else:
                print("[REID][DB] save_to_db=False, sar peste salvarea in DB.")

            socketio.emit('reid_complete', {
                'job_id':        job_id,
                'n_people':      result['n_people'],
                'global_people': global_people,
                'cameras':       result.get('cameras', [
                    {
                        'video_id': cam['video_id'],
                        'camera_name': cam['camera_name'],
                        'camera_order': cam.get('camera_order'),
                    }
                    for cam in cameras
                ]),
                'params':        result['params'],
                'saved_to_db':   save_to_db,
                'message':       f'Re-ID complet: {result["n_people"]} persoane identificate'
            })
            print(f"[REID] Complet: {result['n_people']} persoane")

        except Exception as e:
            print(f"[REID] Eroare: {e}")
            socketio.emit('error', {'message': f'Re-ID failed: {str(e)}'})
        finally:
            if KEEP_REID_CACHE:
                print("[REID][CACHE] Pastrez fisierele locale pentru rulari viitoare.")
            else:
                for cam_info in cameras:
                    local_path = cam_info.get('video_path')
                    if local_path and os.path.exists(local_path):
                        try:
                            os.remove(local_path)
                            print(f"[REID][CLEANUP] Sters fisier camera: {local_path}")
                        except OSError as cleanup_err:
                            print(f"[REID][CLEANUP] Nu s-a putut sterge {local_path}: {cleanup_err}")
            if _reid_stop_event is reid_event_ref:
                _reid_stop_event = None

    threading.Thread(target=run_reid, daemon=True).start()

@socketio.on('start_reid')
def handle_start_reid(data):
    global _reid_stop_event
    if process_reid_multicamera is None:
        emit('error', {'message': 'tracking_inference nu este disponibil pe cluster'})
        return

    cameras_data = data.get('cameras', []) if isinstance(data, dict) else []
    job_id = data.get('job_id') if isinstance(data, dict) else None
    save_to_db = bool(data.get('save_to_db', True))
    emit_live_events = bool(data.get('emit_live_events', True))
    reid_config = data.get('reid_config', {}) if isinstance(data, dict) else {}
    if not isinstance(reid_config, dict):
        reid_config = {}
    print("[REID][CONFIG] Received Re-ID config from API Gateway:", reid_config)
    if not cameras_data and not job_id:
        emit('error', {'message': 'No cameras provided for Re-ID'})
        return

    print(f"\n{'='*60}")
    print(f"[REID] Start Re-ID pentru {len(cameras_data)} camere")
    print(f"{'='*60}")

    if get_tracking_gpu_ids is not None:
        gpu_assignment = get_tracking_gpu_ids()
    else:
        gpu_assignment = list(range(torch.cuda.device_count()))

    if not gpu_assignment:
        socketio.emit('error', {'message': 'Nu exista GPU-uri cu modele tracking incarcate pentru Re-ID'})
        return

    print(f"[REID] GPU-uri disponibile pentru Re-ID: {gpu_assignment}")

    if job_id:
        with prepared_reid_jobs_lock:
            cameras = prepared_reid_jobs.pop(job_id, None)
        if not cameras:
            socketio.emit('error', {'message': f'Job Re-ID pregatit inexistent sau expirat: {job_id}'})
            return

        socketio.emit('warmup_status', {
            'job_id': job_id,
            'status': 'processing_start',
            'message': f'Pornesc Re-ID pe {len(cameras)} camere deja pregatite.'
        })

        _reid_stop_event = threading.Event()
        reid_event_ref = _reid_stop_event
        launch_reid_processing(
            cameras,
            save_to_db,
            reid_event_ref,
            job_id=job_id,
            emit_live_events=emit_live_events,
            reid_config=reid_config,
        )

        emit('reid_started', {
            'job_id': job_id,
            'cameras': [c['camera_name'] for c in cameras],
            'reid_config': reid_config,
            'message': f'Re-ID pornit pentru {len(cameras)} camere'
        })
        return

    # ── FAZA 1: doar citire DB — rapid, fara download ─────────────────────────
    cam_infos = []
    with app.app_context():
        for i, cam_info in enumerate(cameras_data):
            video_id    = cam_info.get('video_id')
            camera_name = cam_info.get('camera_name', f'Camera {i+1}')
            if not video_id:
                continue
            video = db.session.get(Video, int(video_id))
            if not video:
                print(f"[REID] Video ID {video_id} nu exista in DB")
                continue
            cam_infos.append({
                'video_id':     str(video_id),
                'camera_name':  camera_name,
                'camera_order': cam_info.get('camera_order', i + 1),
                'filename':     video.filename,
                'minio_path':   video.minio_path,
                'gpu_id':       gpu_assignment[i % len(gpu_assignment)],
            })
    # app_context inchis aici — elibereaza conexiunea DB

    # ── FAZA 2: download paralel + bariera de pregatire ─────────────────────────
    _reid_stop_event = threading.Event()
    reid_event_ref = _reid_stop_event
    socketio.emit('warmup_status', {
        'status': 'download_start',
        'message': f'Se descarca {len(cam_infos)} camere din MinIO...'
    })

    downloaded = []
    max_download_workers = min(len(cam_infos), 4)

    with ThreadPoolExecutor(max_workers=max_download_workers) as executor:
        futures = {
            executor.submit(prepare_reid_camera_file, info, socketio.emit, "warmup_status", reid_event_ref): info
            for info in cam_infos
        }

        done_count = 0

        for future in as_completed(futures):
            if reid_event_ref.is_set():
                socketio.emit('reid_stopped', {'message': 'Re-ID oprit in timpul pregatirii camerelor.'})
                return
            done_count += 1
            result = future.result()
            if result.get('stopped'):
                socketio.emit('reid_stopped', {'message': result.get('error', 'Re-ID oprit in timpul pregatirii.')})
                return

            if not result['ok']:
                socketio.emit('error', {'message': result['error']})
            else:
                downloaded.append(result)

            socketio.emit('warmup_status', {
                'status': 'download_progress',
                'done': done_count,
                'total': len(cam_infos),
                'camera_name': result.get('camera_name'),
                'message': f'Download camere: {done_count}/{len(cam_infos)}'
            })

    if len(downloaded) != len(cam_infos):
        socketio.emit('error', {
            'message': f'Download incomplet: {len(downloaded)}/{len(cam_infos)} camere.'
        })
        return

    cameras = [
        {
            'video_id':     info['video_id'],
            'camera_name':  info['camera_name'],
            'camera_order': info['camera_order'],
            'video_path':   info['video_path'],
            'gpu_id':       info['gpu_id'],
        }
        for info in sorted(downloaded, key=lambda x: x.get('camera_order', 1))
    ]

    socketio.emit('warmup_status', {
        'status': 'processing_start',
        'message': f'Toate camerele au fost descarcate. Pornesc Re-ID pe {len(cameras)} camere.'
    })

    _reid_stop_event = threading.Event()
    reid_event_ref = _reid_stop_event

    def run_reid():
        global _reid_stop_event
        try:
            result = call_process_reid_multicamera(
                cameras=cameras,
                socketio_obj=socketio,
                emit_fn=make_reid_emit_fn(job_id=None, emit_live_events=emit_live_events),
                results_folder=RESULTS_FOLDER,
                stop_event=reid_event_ref,
                runtime_config=reid_config,
            )
            was_stopped = reid_event_ref.is_set()
            global_people = result.get('global_people', {})

            if was_stopped:
                print(f"[REID] Oprit de utilizator dupa {len(global_people)} persoane procesate.")
                socketio.emit('reid_stopped', {'message': 'Re-ID oprit de utilizator.'})
                return

            if save_to_db:
                try:
                    socketio.emit('warmup_status', {
                        'status': 'db_save_start',
                        'message': 'Se salveaza rezultatele Re-ID in baza de date...'
                    })
                    with app.app_context():
                        for gid_str, info in global_people.items():
                            gid = int(gid_str)
                            existing = GlobalPerson.query.filter_by(global_id=gid).first()
                            if not existing:
                                existing = GlobalPerson(global_id=gid)
                                db.session.add(existing)
                                db.session.flush()
                            for cam_name in info.get('cameras', []):
                                vid_id = next(
                                    (int(c['video_id']) for c in cameras if c['camera_name'] == cam_name),
                                    None
                                )
                                if vid_id:
                                    db.session.add(MultiCamLog(
                                        global_person_id=existing.id,
                                        video_id=vid_id,
                                        camera_name=cam_name,
                                    ))
                        db.session.commit()
                    socketio.emit('warmup_status', {
                        'status': 'db_save_complete',
                        'message': f'Salvate {len(global_people)} persoane globale in baza de date.'
                    })
                    print(f"[REID][DB] Salvate {len(global_people)} persoane globale.")
                except Exception as db_err:
                    print(f"[REID][DB ERROR] {db_err}")
                    socketio.emit('error', {'message': f'Eroare salvare DB Re-ID: {str(db_err)}'})
                    return
            else:
                print("[REID][DB] save_to_db=False, sar peste salvarea in DB.")

            socketio.emit('reid_complete', {
                'job_id':        None,
                'n_people':      result['n_people'],
                'global_people': global_people,
                'cameras':       result.get('cameras', [
                    {
                        'video_id': cam['video_id'],
                        'camera_name': cam['camera_name'],
                        'camera_order': cam.get('camera_order'),
                    }
                    for cam in cameras
                ]),
                'params':        result['params'],
                'saved_to_db':   save_to_db,
                'message':       f'Re-ID complet: {result["n_people"]} persoane identificate'
            })
            print(f"[REID] Complet: {result['n_people']} persoane")

        except Exception as e:
            print(f"[REID] Eroare: {e}")
            socketio.emit('error', {'message': f'Re-ID failed: {str(e)}'})
        finally:
            if KEEP_REID_CACHE:
                print("[REID][CACHE] Pastrez fisierele locale pentru rulari viitoare.")
            else:
                # Clean up camera video files downloaded from MinIO
                for cam_info in cameras:
                    local_path = cam_info.get('video_path')
                    if local_path and os.path.exists(local_path):
                        try:
                            os.remove(local_path)
                            print(f"[REID][CLEANUP] Sters fisier camera: {local_path}")
                        except OSError as cleanup_err:
                            print(f"[REID][CLEANUP] Nu s-a putut sterge {local_path}: {cleanup_err}")
            if _reid_stop_event is reid_event_ref:
                _reid_stop_event = None

    threading.Thread(target=run_reid, daemon=True).start()

    emit('reid_started', {
        'cameras': [c['camera_name'] for c in cameras],
        'reid_config': reid_config,
        'message': f'Re-ID pornit pentru {len(cameras)} camere'
    })

_cleanup_done = False

def cleanup_on_exit():
    global _cleanup_done
    if _cleanup_done:
        return
    _cleanup_done = True
    print("[CLEANUP] Shutting down...")
    try:
        with app.app_context():
            db.session.remove()
            db.engine.dispose()
        print("[CLEANUP] DB closed.")
    except Exception as e:
        print(f"[CLEANUP] Error: {e}")

def signal_handler(sig, frame):
    print("\n[SIGNAL] Stop signal received.")
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)
atexit.register(cleanup_on_exit)

if __name__ == "__main__":
    SERVER_PORT = int(os.getenv("PROCESSING_SERVER_PORT", "5001"))
    console.print(Panel(
        f"[bold cyan]Processing Server[/bold cyan]\n"
        f"Port: {SERVER_PORT}\n"
        f"GPU YOLO: {list(detection_models.keys())}",
        title="[bold green]START[/bold green]",
        border_style="green"
    ))

    # Pornim worker-ul de procesare o singura data.
    threading.Thread(target=processing_worker, daemon=True).start()

    socketio.run(app, debug=False, use_reloader=False, host='0.0.0.0', port=SERVER_PORT, allow_unsafe_werkzeug=True)
