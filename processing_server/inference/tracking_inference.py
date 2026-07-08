"""
tracking_inference.py — Re-ID multi-camera INCREMENTAL (Solutia 3)
====================================================================
Flux per camera:
  1. YOLO track + bytetrack continuu, frame cu frame
  2. La fiecare EMBEDDING_EVERY_SEEN aparitii ale aceluiasi track → extrage embedding TransReID
  3. Cand un track acumuleaza MIN_EMBEDDINGS_TO_MATCH embeddings
     → prima comparare cu galeria globala → asigneaza global ID
  4. La fiecare RE_CHECK_INTERVAL secunde → re-verifica toate
     trackurile active (embedding mediu mai precis acum)
  5. Emite detections + frame JPEG base64 prin 'reid_frame_detections'
     ca frontend-ul sa poata afisa video-ul procesat live

Galeria globala este partajata intre toate camerele (thread-safe).
"""

import cv2
import numpy as np
import torch
import timm
import os
import time
import base64
import threading
import traceback
import subprocess
from PIL import Image
from torchvision import transforms
from ultralytics import YOLO
from scipy.spatial.distance import cosine
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

def validate_video_file(video_path):
    """
    Verifica integritatea unui fisier video in doua etape:
      1. ffprobe — verifica header-ul containerului (moov atom, dimensiuni)
      2. ffmpeg decode test — incearca sa decodeze primele 10 frame-uri
         pentru a prinde coruptii la nivel de bitstream (HEVC NAL unit etc.)
    Returneaza (True, None) daca e valid, (False, motiv) daca e corupt/incomplet,
    (None, motiv) daca ffprobe/ffmpeg nu sunt disponibile.
    """
    try:

        probe = subprocess.run(
            ['ffprobe', '-v', 'error',
             '-select_streams', 'v:0',
             '-show_entries', 'stream=width,height,codec_name',
             '-of', 'default=noprint_wrappers=1',
             video_path],
            capture_output=True, text=True, timeout=4
        )
        if probe.returncode != 0 or not probe.stdout.strip():
            stderr = probe.stderr.strip()
            return False, f"ffprobe container: {stderr[:300] if stderr else 'iesire goala'}"
        info = {}
        for line in probe.stdout.strip().split('\n'):
            if '=' in line:
                k, v = line.split('=', 1)
                info[k.strip()] = v.strip()
        w = int(info.get('width', 0))
        h = int(info.get('height', 0))
        if w == 0 or h == 0:
            return False, f"Dimensiuni invalide raportate de ffprobe: {w}x{h}"

        return True, None

    except subprocess.TimeoutExpired:
        return None, "Timeout ffprobe — continuam cu inferenta"
    except FileNotFoundError:
        return None, "ffprobe nu este instalat — validare omisa"
    except Exception as e:
        return None, f"validate_video_file exceptie: {e}"

_PIPE_EXTS = {'.mov', '.hevc', '.mts', '.m2ts'}

def _probe_dimensions(video_path):
    """Return (width, height, fps) via ffprobe."""
    try:
        result = subprocess.run([
            'ffprobe', '-v', 'error', '-select_streams', 'v:0',
            '-show_entries', 'stream=width,height,r_frame_rate',
            '-of', 'default=noprint_wrappers=1', video_path
        ], capture_output=True, text=True, timeout=10)
        info = {}
        for line in result.stdout.strip().split('\n'):
            if '=' in line:
                k, v = line.split('=', 1)
                info[k.strip()] = v.strip()
        w = int(info.get('width', 1280))
        h = int(info.get('height', 720))
        num, den = info.get('r_frame_rate', '20/1').split('/')
        fps = max(1, round(int(num) / int(den)))
        return w, h, fps
    except Exception:
        return 1280, 720, 20

def _probe_frame_count(video_path, fps):
    """Return estimated frame count from duration * fps via ffprobe."""
    try:
        r = subprocess.run([
            'ffprobe', '-v', 'error', '-select_streams', 'v:0',
            '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1', video_path
        ], capture_output=True, text=True, timeout=10)
        dur = float(next((l.split('=')[1] for l in r.stdout.splitlines() if 'duration' in l), '0'))
        return int(dur * fps)
    except Exception:
        return 0

def _open_cap(video_path):
    """
    Deschide un fisier video. Pentru extensii HEVC/ProRes (.mov etc.)
    foloseste ffmpeg pipe pentru a evita erorile NAL unit din OpenCV.
    Returneaza (source, is_pipe, width, height, fps) sau (None, ...) la esec.
    """
    ext = os.path.splitext(video_path)[1].lower()
    if ext in _PIPE_EXTS:
        w, h, fps = _probe_dimensions(video_path)
        cmd = ['ffmpeg', '-i', video_path, '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-']
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=10**8)
        return proc, True, w, h, fps
    else:
        cap = cv2.VideoCapture(video_path)

        try:
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except Exception:
            pass
        if not cap.isOpened():
            return None, False, 0, 0, 20
        w   = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h   = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS) or 20
        return cap, False, w, h, fps

BASE_DIR       = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_DEFAULT_YOLO_MODEL = os.path.join(BASE_DIR, "models/best.pt")
YOLO_MODEL = os.getenv("REID_DETECTOR_MODEL", _DEFAULT_YOLO_MODEL)
if not os.path.isabs(YOLO_MODEL):
    candidate = os.path.join(BASE_DIR, "models", os.path.basename(YOLO_MODEL))
    if os.path.exists(candidate):
        YOLO_MODEL = candidate
    else:
        candidate = os.path.join(BASE_DIR, YOLO_MODEL)
        if os.path.exists(candidate):
            YOLO_MODEL = candidate

TRANSREID_PATH = os.path.join(BASE_DIR, "models/vit_transreid_msmt.pth")
SEG_MODEL_PATH = os.path.join(BASE_DIR, "models/yolo11n-seg.pt")

GPU_IDS = list(range(torch.cuda.device_count()))

CONF_THRESHOLD          = float(os.getenv("REID_CONF_THRESHOLD", "0.25"))
IMG_SIZE                = int(os.getenv("REID_YOLO_IMG_SIZE", "640"))

PROCESS_FRAME_EVERY     = max(1, int(os.getenv("REID_PROCESS_FRAME_EVERY", "1")))
TRACKER_CONFIG          = os.getenv(
    "REID_TRACKER_CONFIG",
    os.path.join(BASE_DIR, "bytetrack_reid.yaml"),
)

ENABLE_REID_EMBEDDINGS  = os.getenv("ENABLE_REID_EMBEDDINGS", "1") == "1"

EMIT_DEBUG_INFO         = os.getenv("REID_EMIT_DEBUG_INFO", "0") == "1"

FRAME_SKIP              = max(1, int(os.getenv("REID_FRAME_SKIP", "45")))

EMBEDDING_EVERY_SEEN    = max(1, int(os.getenv("REID_EMBEDDING_EVERY_SEEN", "4")))
MAX_EMBEDDINGS          = max(1, int(os.getenv("REID_MAX_EMBEDDINGS", "6")))
MIN_EMBEDDINGS_TO_MATCH = max(1, int(os.getenv("REID_MIN_EMBEDDINGS_TO_MATCH", "2")))
RE_CHECK_INTERVAL       = float(os.getenv("REID_RECHECK_INTERVAL", "8.0"))
REID_THRESHOLD          = float(os.getenv("REID_THRESHOLD", "0.75"))

INTRA_THRESHOLD         = float(os.getenv("REID_INTRA_THRESHOLD", "0.55"))
OVERLAP_THRESHOLD       = int(os.getenv("REID_OVERLAP_THRESHOLD", "3"))
MIN_CAMERAS_FOR_VALID   = 1

USE_SEGMENTATION_FOR_REID = os.getenv("USE_SEGMENTATION_FOR_REID", "0") == "1"

MIN_CROP_H              = int(os.getenv("REID_MIN_CROP_H", "50"))
MIN_CROP_W              = int(os.getenv("REID_MIN_CROP_W", "18"))
MIN_CROP_AREA           = int(os.getenv("REID_MIN_CROP_AREA", "1200"))
MIN_ASPECT              = float(os.getenv("REID_MIN_ASPECT", "1.20"))
MAX_ASPECT              = float(os.getenv("REID_MAX_ASPECT", "4.50"))

EMIT_REID_FRAMES        = os.getenv("EMIT_REID_FRAMES", "1") == "1"
REID_JPEG_QUALITY       = int(os.getenv("REID_JPEG_QUALITY", "35"))
REID_EMIT_FRAME_EVERY   = max(1, int(os.getenv("REID_EMIT_FRAME_EVERY", "2")))
SEND_FRAME_MAX_WIDTH    = int(os.getenv("REID_SEND_FRAME_MAX_WIDTH", "700"))

SYNC_CAMERAS            = os.getenv("REID_SYNC_CAMERAS", "0") == "1"
SYNC_TIMEOUT_SEC        = float(os.getenv("REID_SYNC_TIMEOUT_SEC", "60"))

_REID_RUNTIME_DEFAULTS = {
    "preset": "balanced",
    "enable_reid_embeddings": ENABLE_REID_EMBEDDINGS,
    "emit_debug_info": EMIT_DEBUG_INFO,

    "max_embeddings": MAX_EMBEDDINGS,
    "embedding_every_seen": EMBEDDING_EVERY_SEEN,
    "min_embeddings_to_match": MIN_EMBEDDINGS_TO_MATCH,
    "recheck_interval": RE_CHECK_INTERVAL,

    "reid_threshold": REID_THRESHOLD,
    "intra_threshold": INTRA_THRESHOLD,

    "min_crop_h": MIN_CROP_H,
    "min_crop_w": MIN_CROP_W,
    "min_crop_area": MIN_CROP_AREA,
}

_REID_NUMERIC_LIMITS = {
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

_ALLOWED_REID_CONFIG_KEYS = set(_REID_RUNTIME_DEFAULTS.keys())

def _coerce_bool(value, default):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        v = value.strip().lower()
        if v in {"1", "true", "yes", "y", "on"}:
            return True
        if v in {"0", "false", "no", "n", "off"}:
            return False
    return bool(default)

def _coerce_number(value, default, minimum, maximum, cast_type):
    try:
        if value is None or value == "":
            number = default
        else:
            number = cast_type(value)
    except (TypeError, ValueError):
        number = default

    try:
        number = max(minimum, min(maximum, number))
    except TypeError:
        number = default

    if cast_type is int:
        return int(number)
    return float(number)

def build_runtime_config(runtime_config=None):
    """
    Construieste configul efectiv pentru Re-ID pe job.

    Accepta doar parametri strict Re-ID:
    enable_reid_embeddings, emit_debug_info, max_embeddings,
    embedding_every_seen, min_embeddings_to_match, recheck_interval,
    reid_threshold, intra_threshold, min_crop_h, min_crop_w, min_crop_area.

    Parametrii YOLO/streaming raman hardcodati si sunt ignorati daca apar accidental.
    """
    raw = runtime_config if isinstance(runtime_config, dict) else {}
    cfg = dict(_REID_RUNTIME_DEFAULTS)

    preset = str(raw.get("preset", cfg["preset"])).strip().lower()
    if preset not in {"balanced", "strict", "sensitive", "custom"}:
        preset = "balanced"
    cfg["preset"] = preset

    cfg["enable_reid_embeddings"] = _coerce_bool(
        raw.get("enable_reid_embeddings"),
        cfg["enable_reid_embeddings"],
    )
    cfg["emit_debug_info"] = _coerce_bool(
        raw.get("emit_debug_info"),
        cfg["emit_debug_info"],
    )

    for key, (minimum, maximum, cast_type) in _REID_NUMERIC_LIMITS.items():
        cfg[key] = _coerce_number(
            raw.get(key),
            cfg[key],
            minimum,
            maximum,
            cast_type,
        )

    ignored = sorted(k for k in raw.keys() if k not in _ALLOWED_REID_CONFIG_KEYS)
    if ignored:
        print(f"[REID][CONFIG] Ignor parametri non-Re-ID din runtime_config: {ignored}")

    return cfg

GLOBAL_ID_COLORS = {
    1: (34, 197, 94),
    2: (239, 68, 68),
    3: (249, 115, 22),
    4: (168, 85, 247),
    5: (6, 182, 212),
    6: (234, 179, 8),
    7: (236, 72, 153),
    8: (20, 184, 166),
}

def _hex_to_bgr(hex_color):
    """Hex la BGR tuple."""
    try:
        h = str(hex_color or "#888888").lstrip("#")
        if len(h) != 6:
            h = "888888"
        r = int(h[0:2], 16)
        g = int(h[2:4], 16)
        b = int(h[4:6], 16)
        return (b, g, r)
    except Exception:
        return (136, 136, 136)

def _encode_reid_frame(frame_bgr, detections):
    """
    Deseneaza bbox-urile + label-urile Re-ID pe frame, redimensioneaza frame-ul
    pentru web si il encodeaza JPEG base64.

    Returneaza (frame_b64, width, height) sau None daca encoding-ul esueaza.
    """
    if frame_bgr is None or frame_bgr.size == 0:
        return None

    display_frame = frame_bgr.copy()

    for det in detections or []:
        try:
            if not det.get("bbox"):
                continue

            x1, y1, x2, y2 = map(int, det["bbox"])
            color = _hex_to_bgr(det.get("color", "#888888"))
            label = str(det.get("label") or "?")

            cv2.rectangle(display_frame, (x1, y1), (x2, y2), color, 2)

            # Fundal label
            font = cv2.FONT_HERSHEY_SIMPLEX
            font_scale = 0.55
            thickness = 2
            (tw, th), baseline = cv2.getTextSize(label, font, font_scale, thickness)
            label_y1 = max(0, y1 - th - baseline - 8)
            label_y2 = max(th + baseline + 8, y1)
            cv2.rectangle(
                display_frame,
                (x1, label_y1),
                (x1 + tw + 10, label_y2),
                color,
                -1
            )

            # Text alb/negru in functie de ID
            text_color = (0, 0, 0) if det.get("global_id") and int(det.get("global_id")) <= 2 else (255, 255, 255)
            cv2.putText(
                display_frame,
                label,
                (x1 + 5, label_y2 - 6),
                font,
                font_scale,
                text_color,
                thickness,
                cv2.LINE_AA
            )
        except Exception:
            continue

    # Redimensionare inainte de JPEG/base64. Asta reduce masiv traficul Socket.IO.
    h, w = display_frame.shape[:2]
    if SEND_FRAME_MAX_WIDTH > 0 and w > SEND_FRAME_MAX_WIDTH:
        scale = SEND_FRAME_MAX_WIDTH / float(w)
        new_w = int(SEND_FRAME_MAX_WIDTH)
        new_h = max(1, int(h * scale))
        display_frame = cv2.resize(display_frame, (new_w, new_h), interpolation=cv2.INTER_AREA)

    ok, buffer = cv2.imencode(
        ".jpg",
        display_frame,
        [cv2.IMWRITE_JPEG_QUALITY, max(20, min(95, REID_JPEG_QUALITY))]
    )
    if not ok:
        return None

    out_h, out_w = display_frame.shape[:2]
    return base64.b64encode(buffer).decode("utf-8"), out_w, out_h

REID_TRANSFORM = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
])

# ══════════════════════════════════════════════════════════════════════════════
# PRE-INCARCARE MODELE LA STARTUP
# ══════════════════════════════════════════════════════════════════════════════

_yolo_models    = {}
_reid_models    = {}
_seg_models     = {}
_models_loaded  = False
_models_lock    = threading.Lock()
_loaded_gpu_ids = []

def _gpu_memory_info_mb(gpu_id):
    with torch.cuda.device(gpu_id):
        free_b, total_b = torch.cuda.mem_get_info()
    return free_b // (1024 * 1024), total_b // (1024 * 1024)

def get_tracking_gpu_ids():
    return list(_loaded_gpu_ids)

def preload_all_models():
    global _models_loaded, _loaded_gpu_ids
    with _models_lock:
        if _models_loaded:
            print("[TRACKING] Modelele sunt deja incarcate.")
            return True

        if not GPU_IDS:
            raise RuntimeError("Nu exista GPU-uri CUDA vizibile.")

        min_free_gb = float(os.getenv("TRACKING_MIN_FREE_GB", "12"))
        max_preload = int(os.getenv("TRACKING_PRELOAD_MAX_GPUS", "1"))
        max_preload = max(1, max_preload)

        gpu_stats = []
        for gid in GPU_IDS:
            try:
                free_mb, total_mb = _gpu_memory_info_mb(gid)
                gpu_stats.append((gid, free_mb, total_mb))
            except Exception as e:
                print(f"[TRACKING] GPU {gid}: nu pot citi memoria libera ({e})")

        gpu_stats.sort(key=lambda x: x[1], reverse=True)
        min_free_mb = int(min_free_gb * 1024)
        preferred = [s for s in gpu_stats if s[1] >= min_free_mb]
        if not preferred:
            preferred = gpu_stats

        target_gpus = [gid for gid, _, _ in preferred[:max_preload]]
        print(f"[TRACKING] GPU-uri detectate: {GPU_IDS}")
        for gid, free_mb, total_mb in gpu_stats:
            print(f"[TRACKING] GPU {gid}: free={free_mb}MB / total={total_mb}MB")
        print(
            f"[TRACKING] Pre-incarcare pe GPU-uri candidate: {target_gpus} "
            f"(TRACKING_MIN_FREE_GB={min_free_gb}, TRACKING_PRELOAD_MAX_GPUS={max_preload})"
        )
        load_errors = []

        def load_gpu(gpu_id):
            parts = ["YOLO"]
            if USE_SEGMENTATION_FOR_REID:
                parts.append("YOLO-seg")
            if ENABLE_REID_EMBEDDINGS:
                parts.append("TransReID")
            print(f"[TRACKING] GPU {gpu_id}: incarcare {' + '.join(parts)}...")

            _yolo_models[gpu_id] = YOLO(YOLO_MODEL).to(f'cuda:{gpu_id}')

            # YOLO-seg este optional si scump; nu il incarcam daca segmentarea e oprita.
            if USE_SEGMENTATION_FOR_REID:
                _seg_models[gpu_id] = YOLO(SEG_MODEL_PATH).to(f'cuda:{gpu_id}')
            else:
                _seg_models[gpu_id] = None

            # TransReID este optional pentru demo live fluid. Daca e dezactivat,
            # sistemul ramane pe YOLO + ByteTrack si trimite frame-uri/detectii rapid.
            if ENABLE_REID_EMBEDDINGS:
                model = timm.create_model('vit_base_patch16_224', pretrained=False, num_classes=0)
                ckpt = torch.load(TRANSREID_PATH, map_location='cpu')
                sd = {k[5:]: v for k, v in ckpt.items()
                      if k.startswith('base.') and k[5:] != 'pos_embed'}
                model.load_state_dict(sd, strict=False)
                _reid_models[gpu_id] = model.to(f'cuda:{gpu_id}').eval()
            else:
                _reid_models[gpu_id] = None

            print(f"[TRACKING] GPU {gpu_id}: modele incarcate ")

        for gid in target_gpus:
            try:
                load_gpu(gid)
            except Exception as e:
                load_errors.append(f"GPU {gid}: {e}")
                print(f"[TRACKING] Eroare GPU {gid}: {e}")
                torch.cuda.empty_cache()

        dummy = np.zeros((320, 320, 3), dtype=np.uint8)
        # Pentru live detection-only este suficient YOLO incarcat. Daca ENABLE_REID_EMBEDDINGS=1,
        # verificam si prezenta modelului TransReID. Segmentarea este optionala.
        if ENABLE_REID_EMBEDDINGS:
            loaded_now = sorted(set(_yolo_models.keys()) & set(_reid_models.keys()))
        else:
            loaded_now = sorted(set(_yolo_models.keys()))
        for gpu_id in loaded_now:
            if gpu_id in _yolo_models:
                try:
                    _yolo_models[gpu_id].predict(dummy, device=gpu_id, verbose=False)
                    print(f"[TRACKING] GPU {gpu_id}: warmup YOLO done ")
                except Exception as e:
                    load_errors.append(f"GPU {gpu_id} warmup: {e}")

        _loaded_gpu_ids = loaded_now
        _models_loaded = len(_loaded_gpu_ids) > 0
        if _models_loaded:
            print(f"[TRACKING]  Modele tracking incarcate pe GPU-urile: {_loaded_gpu_ids}")
            if load_errors:
                print("[TRACKING] [WARN] Unele GPU-uri au esuat la preload:")
                for err in load_errors:
                    print(f"  - {err}")
        else:
            print("[TRACKING] [WARN] Nu s-a putut incarca niciun set complet de modele tracking.")
            if load_errors:
                print("[TRACKING] Detalii erori:")
                for err in load_errors:
                    print(f"  - {err}")
                print(traceback.format_exc())
        return _models_loaded

def models_loaded_ok():
    return _models_loaded

# ══════════════════════════════════════════════════════════════════════════════
# SEGMENTARE + EMBEDDING
# ══════════════════════════════════════════════════════════════════════════════

def segment_crop(gpu_id, crop_bgr):
    if crop_bgr is None or crop_bgr.size == 0 or crop_bgr.shape[0] < 40:
        return crop_bgr
    seg_model = _seg_models.get(gpu_id)
    if seg_model is None:
        return crop_bgr
    try:
        results = seg_model.predict(crop_bgr, classes=[0], conf=0.25,
                                    device=gpu_id, verbose=False)
        masks = results[0].masks
        if masks is None or len(masks) == 0:
            return crop_bgr
        boxes = results[0].boxes.xyxy.cpu().numpy()
        areas = (boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1])
        best  = int(np.argmax(areas))
        mask  = masks.data[best].cpu().numpy().astype(bool)
        if mask.shape != crop_bgr.shape[:2]:
            mask = cv2.resize(mask.astype(np.uint8),
                              (crop_bgr.shape[1], crop_bgr.shape[0]),
                              interpolation=cv2.INTER_NEAREST).astype(bool)
        seg        = crop_bgr.copy()
        seg[~mask] = 0
        return seg
    except Exception:
        return crop_bgr

def extract_embedding(gpu_id, crop_bgr):
    if crop_bgr is None or crop_bgr.size == 0 or crop_bgr.shape[0] < 40:
        return None
    reid_model = _reid_models.get(gpu_id)
    if reid_model is None:
        return None
    try:
        seg = segment_crop(gpu_id, crop_bgr) if USE_SEGMENTATION_FOR_REID else crop_bgr
        img = Image.fromarray(cv2.cvtColor(seg, cv2.COLOR_BGR2RGB))
        t   = REID_TRANSFORM(img).unsqueeze(0).to(f'cuda:{gpu_id}')
        with torch.no_grad():
            emb = reid_model(t)
            emb = emb / emb.norm(dim=-1, keepdim=True)
        return emb.cpu().float().numpy().flatten()
    except Exception:
        return None

# ══════════════════════════════════════════════════════════════════════════════
# UTILITATI RE-ID
# ══════════════════════════════════════════════════════════════════════════════

def _normalize_embedding(emb):
    if emb is None:
        return None
    norm = np.linalg.norm(emb)
    if norm > 0:
        return emb / norm
    return emb

def _is_good_crop(x1, y1, x2, y2, frame_w, frame_h, cfg=None):
    """Filtreaza crop-uri prea mici sau cu aspect ratio ciudat."""
    cfg = cfg or _REID_RUNTIME_DEFAULTS
    min_crop_w = cfg.get("min_crop_w", MIN_CROP_W)
    min_crop_h = cfg.get("min_crop_h", MIN_CROP_H)
    min_crop_area = cfg.get("min_crop_area", MIN_CROP_AREA)

    x1 = max(0, int(x1))
    y1 = max(0, int(y1))
    x2 = min(frame_w, int(x2))
    y2 = min(frame_h, int(y2))

    w = max(0, x2 - x1)
    h = max(0, y2 - y1)
    area = w * h
    aspect = h / max(w, 1)

    if w < min_crop_w or h < min_crop_h:
        return False
    if area < min_crop_area:
        return False
    if aspect < MIN_ASPECT or aspect > MAX_ASPECT:
        return False
    return True

def _should_accept_embedding(existing_embeddings, new_emb, intra_threshold=None):
    """
    Foloseste intra_threshold ca sa nu strice media unui track cu embedding-uri
    foarte diferite, de obicei aparute din ID switch sau crop prost.
    """
    threshold = INTRA_THRESHOLD if intra_threshold is None else float(intra_threshold)

    if new_emb is None:
        return False, 0.0
    if not existing_embeddings:
        return True, 1.0

    mean_existing = np.mean(existing_embeddings, axis=0)
    mean_existing = _normalize_embedding(mean_existing)
    if mean_existing is None:
        return True, 1.0

    sim = float(1 - cosine(new_emb, mean_existing))
    return sim >= threshold, sim

class FrameSync:
    """
    Sincronizare stricta intre camere.

    Fiecare camera proceseaza frame-ul curent si apoi asteapta la bariera.
    Astfel, camera rapida nu ajunge la frame 200 in timp ce camera lenta e la 50.

    Daca o camera termina, se rupe bariera si se seteaza stop_event, deci toate
    camerele se opresc consistent.
    """
    def __init__(self, n_cameras, enabled=True, timeout=60.0):
        self.enabled = bool(enabled and n_cameras > 1)
        self.timeout = timeout
        self._barrier = threading.Barrier(n_cameras) if self.enabled else None
        self._lock = threading.Lock()
        self._last_frames = {}

    def wait(self, camera_name, frame_number, stop_event):
        if not self.enabled:
            return True
        if stop_event.is_set():
            return False

        with self._lock:
            self._last_frames[camera_name] = frame_number

        try:
            self._barrier.wait(timeout=self.timeout)
            return not stop_event.is_set()
        except threading.BrokenBarrierError:
            stop_event.set()
            return False

    def abort(self, stop_event):
        if self.enabled and self._barrier is not None:
            try:
                self._barrier.abort()
            except Exception:
                pass
        stop_event.set()

class GlobalGallery:
    def __init__(self, reid_threshold=REID_THRESHOLD):
        self._gallery      = {}
        self._track_to_gid = {}
        self._lock         = threading.Lock()
        self._next_id      = 1
        self.reid_threshold = float(reid_threshold)

    def assign(self, camera_name, track_id, mean_emb, track_frames,
               n_track_embeddings=None, reid_threshold=None):
        """Returneaza (global_id, match_score, candidate_score). match_score=0.0 daca e ID nou."""
        threshold = self.reid_threshold if reid_threshold is None else float(reid_threshold)

        with self._lock:
            best_sim = 0.0
            best_gid = None

            for gid, gdata in self._gallery.items():
                conflict = False
                for (cam, tid), frames in gdata['track_frames'].items():
                    if cam == camera_name:
                        if len(track_frames & frames) > OVERLAP_THRESHOLD:
                            conflict = True
                            break
                if conflict:
                    continue
                sim = float(1 - cosine(mean_emb, gdata['mean_emb']))
                if sim > best_sim:
                    best_sim = sim
                    best_gid = gid

            if best_sim >= threshold and best_gid is not None:
                gid = best_gid
                n = self._gallery[gid]['n_emb']
                self._gallery[gid]['mean_emb'] = (
                    self._gallery[gid]['mean_emb'] * n + mean_emb
                ) / (n + 1)
                norm = np.linalg.norm(self._gallery[gid]['mean_emb'])
                if norm > 0:
                    self._gallery[gid]['mean_emb'] /= norm
                self._gallery[gid]['n_emb'] += 1
                self._gallery[gid]['n_gallery_updates'] += 1
                self._gallery[gid]['n_track_embeddings'] += int(n_track_embeddings or 0)
                self._gallery[gid]['cameras'].add(camera_name)
                self._gallery[gid]['track_frames'][(camera_name, track_id)] = track_frames
                match_score = best_sim
            else:
                gid = self._next_id
                self._next_id += 1
                self._gallery[gid] = {
                    'mean_emb':            mean_emb.copy(),
                    'n_emb':               1,  # backward compatibility: gallery mean updates
                    'n_gallery_updates':   1,
                    'n_track_embeddings':  int(n_track_embeddings or 0),
                    'cameras':             {camera_name},
                    'track_frames':        {(camera_name, track_id): track_frames},
                }
                match_score = 0.0

            self._track_to_gid[(camera_name, track_id)] = gid
            return gid, match_score, best_sim

    def get_gid(self, camera_name, track_id):
        with self._lock:
            return self._track_to_gid.get((camera_name, track_id))

    def recheck(self, camera_name, track_id, mean_emb, track_frames,
                n_track_embeddings=None, reid_threshold=None):
        """Returneaza (new_gid, match_score)."""
        threshold = self.reid_threshold if reid_threshold is None else float(reid_threshold)

        with self._lock:
            current_gid = self._track_to_gid.get((camera_name, track_id))
            best_sim = 0.0
            best_gid = None

            for gid, gdata in self._gallery.items():
                if gid == current_gid:
                    continue
                conflict = False
                for (cam, tid), frames in gdata['track_frames'].items():
                    if cam == camera_name and (cam, tid) != (camera_name, track_id):
                        if len(track_frames & frames) > OVERLAP_THRESHOLD:
                            conflict = True
                            break
                if conflict:
                    continue
                sim = float(1 - cosine(mean_emb, gdata['mean_emb']))
                if sim > best_sim:
                    best_sim = sim
                    best_gid = gid

            if best_sim >= threshold and best_gid is not None:
                old_gid = current_gid
                new_gid = best_gid
                if old_gid and old_gid in self._gallery:
                    self._gallery[old_gid]['track_frames'].pop((camera_name, track_id), None)
                    self._gallery[old_gid]['cameras'].discard(camera_name)
                self._gallery[new_gid]['cameras'].add(camera_name)
                self._gallery[new_gid]['track_frames'][(camera_name, track_id)] = track_frames
                n = self._gallery[new_gid]['n_emb']
                self._gallery[new_gid]['mean_emb'] = (
                    self._gallery[new_gid]['mean_emb'] * n + mean_emb
                ) / (n + 1)
                norm = np.linalg.norm(self._gallery[new_gid]['mean_emb'])
                if norm > 0:
                    self._gallery[new_gid]['mean_emb'] /= norm
                self._gallery[new_gid]['n_emb'] += 1
                self._gallery[new_gid]['n_gallery_updates'] += 1
                self._gallery[new_gid]['n_track_embeddings'] += int(n_track_embeddings or 0)
                self._track_to_gid[(camera_name, track_id)] = new_gid
                print(f"  [RECHECK] {camera_name}/track{track_id}: "
                      f"G{old_gid} → G{new_gid} (sim={best_sim:.3f})")
                return new_gid, best_sim

            return current_gid, 0.0

    def get_summary(self):
        with self._lock:
            result = {}
            for gid, gdata in self._gallery.items():
                n_gallery_updates = gdata.get('n_gallery_updates', gdata.get('n_emb', 0))
                result[str(gid)] = {
                    'cameras':             sorted(gdata['cameras']),

                    'n_embeddings':        gdata.get('n_emb', n_gallery_updates),
                    'n_gallery_updates':   n_gallery_updates,
                    'n_track_embeddings':  gdata.get('n_track_embeddings', 0),
                    'color':               '#{:02x}{:02x}{:02x}'.format(
                                            *GLOBAL_ID_COLORS.get(gid, (136, 136, 136))),
                }
            return result

def process_camera_incremental(camera_name, video_id, video_path,
                                gpu_id, gallery, emit_fn, stop_event,
                                sync_ctx=None, cfg=None):
    """
    Proceseaza o singura camera incremental.
    Emite:
      - 'reid_frame_detections' → frame JPEG base64 + bbox-uri + Global IDs per frame
      - 'person_crop'  → la primul match al unui track cu Global ID
      - 'reid_update'  → la assign + recheck
    """
    cfg = build_runtime_config(cfg)

    yolo = _yolo_models.get(gpu_id)
    if yolo is None:
        print(f"[{camera_name}] EROARE: YOLO nu e incarcat pe GPU {gpu_id}")
        return

    valid, reason = validate_video_file(video_path)
    if valid is False and reason and 'moov atom not found' in reason:
        print(f"[{camera_name}] moov atom la sfarsit — re-mux cu ffmpeg faststart...")
        fixed_path = video_path + '_fixed.mp4'
        try:
            remux = subprocess.run(
                ['ffmpeg', '-y', '-i', video_path, '-c', 'copy', '-movflags', 'faststart', fixed_path],
                capture_output=True, text=True, timeout=120
            )
            if stop_event.is_set():
                if os.path.exists(fixed_path):
                    os.remove(fixed_path)
                return
            if remux.returncode == 0 and os.path.exists(fixed_path):
                os.replace(fixed_path, video_path)
                print(f"[{camera_name}] Re-mux reusit. Re-validare...")
                valid, reason = validate_video_file(video_path)
            else:
                print(f"[{camera_name}] Re-mux esuat: {remux.stderr[:200]}")
                if os.path.exists(fixed_path):
                    os.remove(fixed_path)
        except Exception as e:
            print(f"[{camera_name}] Re-mux exceptie: {e}")
            if os.path.exists(fixed_path):
                os.remove(fixed_path)
    if valid is False:
        print(f"[{camera_name}] EROARE: Fisier video invalid, sar peste camera — {reason}")
        return
    if valid is None:
        print(f"[{camera_name}] AVERTISMENT: {reason}")

    source, is_pipe, orig_w, orig_h, fps = _open_cap(video_path)
    if source is None:
        print(f"[{camera_name}] EROARE: Nu s-a putut deschide {video_path}")
        return

    if is_pipe:
        total = _probe_frame_count(video_path, fps)
    else:
        total = int(source.get(cv2.CAP_PROP_FRAME_COUNT))
    print(f"[{camera_name}] Start incremental pe GPU {gpu_id} | {total} frame-uri @ {fps:.0f}fps")

    local_tracks = defaultdict(lambda: {
        'embeddings':         [],
        'embedding_crops':     [],
        'frames':             set(),
        'seen_count':         0,
        'matched':            False,
        'last_recheck_count': 0,
        'best_crop':          None,
        'best_area':          0,
    })

    def _encode_track_crop_payload(track_data):
        crop_b64 = None
        best_crop = track_data.get('best_crop')
        if best_crop is not None:
            _, buf = cv2.imencode('.jpg', best_crop, [cv2.IMWRITE_JPEG_QUALITY, 80])
            crop_b64 = base64.b64encode(buf).decode('utf-8')

        embedding_crops = []
        for crop_info in track_data.get('embedding_crops', []):
            crop_img = crop_info.get('image')
            if crop_img is None:
                continue
            _, crop_buf = cv2.imencode('.jpg', crop_img, [cv2.IMWRITE_JPEG_QUALITY, 80])
            embedding_crops.append({
                'image': base64.b64encode(crop_buf).decode('utf-8'),
                'camera_name': crop_info.get('camera_name'),
                'track_id': crop_info.get('track_id'),
                'frame_number': crop_info.get('frame_number'),
                'timestamp_s': crop_info.get('timestamp_s'),
                'timestamp_ms': crop_info.get('timestamp_ms'),
                'bbox': crop_info.get('bbox'),
                'bbox_area': crop_info.get('bbox_area'),
            })

        return crop_b64, embedding_crops

    frame_count     = 0
    processed_count = 0
    last_recheck_t  = time.time()

    while not stop_event.is_set():
        if is_pipe:
            frame_size = orig_w * orig_h * 3
            if source.poll() is not None:
                break
            raw = source.stdout.read(frame_size)
            if not raw or len(raw) < frame_size:
                break
            frame = np.frombuffer(raw, dtype=np.uint8).reshape((orig_h, orig_w, 3)).copy()
        else:
            ret, frame = source.read()
            if not ret:
                break
        frame_count += 1
        timestamp_ms = int(time.time() * 1000)

        if PROCESS_FRAME_EVERY > 1 and frame_count % PROCESS_FRAME_EVERY != 0:
            if sync_ctx is not None:
                if not sync_ctx.wait(camera_name, frame_count, stop_event):
                    break
            continue

        processed_count += 1

        results = yolo.track(
            frame, persist=True, tracker=TRACKER_CONFIG,
            conf=CONF_THRESHOLD, imgsz=IMG_SIZE,
            device=gpu_id, classes=[0], verbose=False
        )

        people_in_frame = []
        detections      = []

        boxes_obj = results[0].boxes if results and len(results) > 0 else None

        if boxes_obj is not None and len(boxes_obj) > 0:
            boxes = boxes_obj.xyxy.cpu().numpy()
            confs = boxes_obj.conf.cpu().numpy() if boxes_obj.conf is not None else np.zeros(len(boxes))

            if boxes_obj.id is not None:
                ids = boxes_obj.id.int().cpu().numpy().tolist()
            else:
                ids = [None] * len(boxes)

            for detection_index, (box, raw_tid, conf) in enumerate(zip(boxes, ids, confs)):
                x1, y1, x2, y2 = map(int, box)
                box_area = max(0, x2 - x1) * max(0, y2 - y1)
                tid = int(raw_tid) if raw_tid is not None else None

                if tid is None:
                    good_crop = _is_good_crop(x1, y1, x2, y2, orig_w, orig_h, cfg)
                    detections.append({
                        'detection_index': detection_index,
                        'global_id': None,
                        'track_id':  None,
                        'bbox':      [float(x1), float(y1), float(x2), float(y2)],
                        'bbox_xywh': [float(x1), float(y1), float(x2 - x1), float(y2 - y1)],
                        'bbox_area': float(box_area),
                        'conf':      round(float(conf), 4),
                        'label':     f"D{detection_index + 1}",
                        'color':     '#888888',
                        'seen_count': 0,
                        'n_embeddings': 0,
                        'max_embeddings': cfg["max_embeddings"],
                        'matched': False,
                        'good_crop': bool(good_crop),
                        'detector_only': True,
                        'reason': 'no_track_id',
                    })
                    continue

                local_tracks[tid]['seen_count'] += 1
                local_tracks[tid]['frames'].add(frame_count)

                good_crop = _is_good_crop(x1, y1, x2, y2, orig_w, orig_h, cfg)

                should_extract_embedding = (
                    cfg["enable_reid_embeddings"]
                    and good_crop
                    and local_tracks[tid]['seen_count'] % cfg["embedding_every_seen"] == 0
                    and len(local_tracks[tid]['embeddings']) < cfg["max_embeddings"]
                )

                if should_extract_embedding:
                    crop = frame[max(0, y1):min(orig_h, y2), max(0, x1):min(orig_w, x2)]
                    if crop.size > 0:
                        emb = extract_embedding(gpu_id, crop)
                        emb = _normalize_embedding(emb)

                        accept_emb, intra_sim = _should_accept_embedding(
                            local_tracks[tid]['embeddings'],
                            emb,
                            cfg["intra_threshold"],
                        )

                        if accept_emb:
                            local_tracks[tid]['embeddings'].append(emb)
                            emb_count = len(local_tracks[tid]['embeddings'])
                            resized_crop = cv2.resize(crop, (96, 192))
                            local_tracks[tid]['embedding_crops'].append({
                                'image': resized_crop,
                                'camera_name': camera_name,
                                'track_id': tid,
                                'frame_number': frame_count,
                                'timestamp_s': round(frame_count / fps, 2),
                                'timestamp_ms': timestamp_ms,
                                'bbox': [float(x1), float(y1), float(x2), float(y2)],
                                'bbox_area': float(box_area),
                            })
                            print(
                                f"  [{camera_name}] emb track{tid}: "
                                f"{emb_count}/{cfg['max_embeddings']} "
                                f"(seen={local_tracks[tid]['seen_count']}, frame={frame_count}, "
                                f"area={box_area})"
                            )

                            if cfg["emit_debug_info"]:
                                emit_fn("reid_embedding_update", {
                                    "video_id": video_id,
                                    "camera_id": str(video_id),
                                    "camera_name": camera_name,
                                    "track_id": tid,
                                    "frame_number": frame_count,
                                    "timestamp_ms": timestamp_ms,
                                    "seen_count": local_tracks[tid]["seen_count"],
                                    "n_embeddings": emb_count,
                                    "max_embeddings": cfg["max_embeddings"],
                                    "bbox": [float(x1), float(y1), float(x2), float(y2)],
                                    "bbox_xywh": [float(x1), float(y1), float(x2 - x1), float(y2 - y1)],
                                    "bbox_area": float(box_area),
                                })

                            if box_area > local_tracks[tid]['best_area']:
                                local_tracks[tid]['best_area'] = box_area
                                local_tracks[tid]['best_crop'] = resized_crop
                        else:
                            print(f"  [{camera_name}] skip emb track{tid}: intra_sim={intra_sim:.3f}")
                            if cfg["emit_debug_info"]:
                                emit_fn("reid_embedding_skip", {
                                    "video_id": video_id,
                                    "camera_id": str(video_id),
                                    "camera_name": camera_name,
                                    "track_id": tid,
                                    "frame_number": frame_count,
                                    "timestamp_ms": timestamp_ms,
                                    "seen_count": local_tracks[tid]["seen_count"],
                                    "reason": "intra_threshold_or_empty_embedding",
                                    "intra_sim": round(float(intra_sim), 4),
                                    "threshold": cfg["intra_threshold"],
                                    "bbox": [float(x1), float(y1), float(x2), float(y2)],
                                    "bbox_area": float(box_area),
                                })

                n_emb = len(local_tracks[tid]['embeddings'])

                if n_emb >= cfg["min_embeddings_to_match"] and not local_tracks[tid]['matched']:
                    mean_emb = np.mean(local_tracks[tid]['embeddings'], axis=0)
                    mean_emb = _normalize_embedding(mean_emb)

                    if mean_emb is not None:
                        gid, match_score, candidate_score = gallery.assign(
                            camera_name, tid, mean_emb,
                            set(local_tracks[tid]['frames']),
                            n_track_embeddings=n_emb,
                            reid_threshold=cfg["reid_threshold"],
                        )
                        local_tracks[tid]['matched']            = True
                        local_tracks[tid]['last_recheck_count'] = n_emb
                        is_new_person = (match_score == 0.0)

                        print(f"  [{camera_name}] track{tid} → G{gid} "
                              f"({'NOU' if is_new_person else f'match={match_score:.3f}'}) "
                              f"({n_emb} emb, frame {frame_count})")

                        crop_b64, embedding_crops = _encode_track_crop_payload(local_tracks[tid])

                        summary = gallery.get_summary()
                        emit_fn('person_crop', {
                            'video_id':       video_id,
                            'camera_id':      str(video_id),
                            'global_id':     gid,
                            'camera_name':   camera_name,
                            'track_id':      tid,
                            'frame_number':  frame_count,
                            'timestamp_ms':  timestamp_ms,
                            'timestamp_s':   round(frame_count / fps, 2),
                            'best_crop':     crop_b64,
                            'crops':         embedding_crops,
                            'match_score':   round(match_score, 4),
                            'candidate_score': round(candidate_score, 4),
                            'reid_threshold': round(float(cfg["reid_threshold"]), 4),
                            'is_new_person': is_new_person,
                            'n_embeddings':  n_emb,
                            'bbox':          [float(x1), float(y1), float(x2), float(y2)],
                            'bbox_area':     float((x2 - x1) * (y2 - y1)),
                            'cameras':       summary.get(str(gid), {}).get('cameras', []),
                            'color':         summary.get(str(gid), {}).get('color', '#888888'),
                        })
                        emit_fn('reid_update', {
                            'global_people': summary,
                            'video_id':       video_id,
                            'camera_id':      str(video_id),
                            'camera_name':   camera_name,
                            'track_id':      tid,
                            'global_id':     gid,
                            'match_score':   round(match_score, 4),
                            'candidate_score': round(candidate_score, 4),
                            'reid_threshold': round(float(cfg["reid_threshold"]), 4),
                            'is_new_person': is_new_person,
                            'timestamp_ms':  timestamp_ms,
                        })

                gid = gallery.get_gid(camera_name, tid)
                if gid:
                    color     = GLOBAL_ID_COLORS.get(gid, (136, 136, 136))
                    hex_color = '#{:02x}{:02x}{:02x}'.format(*color)
                    label     = f"G{gid}"
                    people_in_frame.append(gid)
                else:
                    hex_color = '#888888'
                    label     = f"T{tid}"

                detections.append({
                    'detection_index': detection_index,
                    'global_id': gid,
                    'track_id':  tid,
                    'bbox':      [float(x1), float(y1), float(x2), float(y2)],
                    'bbox_xywh': [float(x1), float(y1), float(x2 - x1), float(y2 - y1)],
                    'bbox_area': float(box_area),
                    'conf':      round(float(conf), 4),
                    'label':     label,
                    'color':     hex_color,
                    'seen_count': local_tracks[tid]['seen_count'],
                    'n_embeddings': n_emb,
                    'max_embeddings': cfg["max_embeddings"],
                    'matched': local_tracks[tid]['matched'],
                    'good_crop': bool(good_crop),
                    'detector_only': False,
                })

        now = time.time()
        if now - last_recheck_t >= cfg["recheck_interval"]:
            last_recheck_t = now
            for tid, tdata in local_tracks.items():
                if not tdata['matched']:
                    continue
                n_emb = len(tdata['embeddings'])
                if n_emb <= tdata['last_recheck_count']:
                    continue
                mean_emb = np.mean(tdata['embeddings'], axis=0)
                mean_emb = _normalize_embedding(mean_emb)
                if mean_emb is None:
                    continue

                old_gid = gallery.get_gid(camera_name, tid)
                new_gid, recheck_score = gallery.recheck(
                    camera_name,
                    tid,
                    mean_emb,
                    set(tdata['frames']),
                    n_track_embeddings=n_emb,
                    reid_threshold=cfg["reid_threshold"],
                )
                tdata['last_recheck_count'] = n_emb
                if new_gid and recheck_score > 0:
                    summary = gallery.get_summary()
                    crop_b64, embedding_crops = _encode_track_crop_payload(tdata)
                    emit_fn('reid_update', {
                        'global_people': summary,
                        'video_id':       video_id,
                        'camera_id':      str(video_id),
                        'camera_name':   camera_name,
                        'track_id':      tid,
                        'global_id':     new_gid,
                        'match_score':   round(recheck_score, 4),
                        'is_new_person': False,
                        'timestamp_ms':  int(time.time() * 1000),
                        'recheck':       True,
                    })
                    if new_gid != old_gid:
                        last_crop_info = (
                            tdata.get('embedding_crops')[-1]
                            if tdata.get('embedding_crops')
                            else {}
                        )
                        emit_fn('person_crop', {
                            'video_id':       video_id,
                            'camera_id':      str(video_id),
                            'global_id':      new_gid,
                            'camera_name':    camera_name,
                            'track_id':       tid,
                            'frame_number':   frame_count,
                            'timestamp_ms':   int(time.time() * 1000),
                            'timestamp_s':    round(frame_count / fps, 2),
                            'best_crop':      crop_b64,
                            'crops':          embedding_crops,
                            'match_score':    round(recheck_score, 4),
                            'candidate_score': round(recheck_score, 4),
                            'reid_threshold': round(float(cfg["reid_threshold"]), 4),
                            'is_new_person':  False,
                            'n_embeddings':   n_emb,
                            'bbox':           last_crop_info.get('bbox'),
                            'bbox_area':      last_crop_info.get('bbox_area'),
                            'cameras':        summary.get(str(new_gid), {}).get('cameras', []),
                            'color':          summary.get(str(new_gid), {}).get('color', '#888888'),
                            'recheck':        True,
                            'previous_global_id': old_gid,
                        })

        unique_gids = sorted(set(gid for gid in people_in_frame if gid is not None))

        should_emit = (
            EMIT_REID_FRAMES
            and REID_EMIT_FRAME_EVERY > 0
            and processed_count % REID_EMIT_FRAME_EVERY == 0
        )

        if should_emit:
            frame_b64 = None
            send_w = orig_w
            send_h = orig_h
            encoded = _encode_reid_frame(frame, detections)
            if encoded is not None:
                frame_b64, send_w, send_h = encoded

            payload = {
                'video_id':      video_id,
                'camera_id':     str(video_id),
                'camera_name':   camera_name,
                'frame_number':  frame_count,
                'processed_frame_number': processed_count,
                'timestamp_ms':  timestamp_ms,
                'total_frames':  total,

                'people_count':  len(detections),
                'detected_people_count': len(detections),
                'identified_people_count': len(unique_gids),
                'global_ids':    unique_gids,
                'detections':    detections,

                'progress':      round(frame_count / total * 100) if total else 0,
                'synced':        bool(sync_ctx and sync_ctx.enabled),
                'frame_width':   send_w,
                'frame_height':  send_h,
                'original_frame_width': orig_w,
                'original_frame_height': orig_h,
            }

            if cfg["emit_debug_info"]:
                payload["track_debug"] = {
                    str(tid): {
                        "seen_count": tdata["seen_count"],
                        "n_embeddings": len(tdata["embeddings"]),
                        "max_embeddings": cfg["max_embeddings"],
                        "matched": tdata["matched"],
                        "last_recheck_count": tdata["last_recheck_count"],
                        "best_area": tdata["best_area"],
                    }
                    for tid, tdata in local_tracks.items()
                }

            if frame_b64 is not None:
                payload['frame'] = frame_b64

            print(f"  [EMIT][{camera_name}] frame={frame_count} "
                  f"detections={len(detections)} "
                  f"bboxes={[d['bbox'] for d in detections]}")

            emit_fn('reid_frame_detections', payload)

        if sync_ctx is not None:
            if not sync_ctx.wait(camera_name, frame_count, stop_event):
                break

    if sync_ctx is not None and sync_ctx.enabled:

        sync_ctx.abort(stop_event)

    if sync_ctx is not None and stop_event.is_set():
        print(f"[{camera_name}] Oprit prin sincronizare/stop_event la frame {frame_count}.")

    if is_pipe:
        source.stdout.close()
        source.terminate()
        source.wait()
    else:
        source.release()
    if frame_count == 0:
        print(f"[{camera_name}] EROARE: 0 frame-uri procesate — fisier corupt "
              f"(codec invalid, HEVC/NAL unit corupt, sau stream gol): {video_path}")
    else:
        print(f"[{camera_name}] Terminat ({frame_count} frame-uri procesate).")

def process_reid_multicamera(cameras, socketio_obj, emit_fn, results_folder,
                             stop_event=None, runtime_config=None):
    if not _models_loaded:
        emit_fn('error', {'message': 'Modelele nu sunt incarcate. Reporneste serverul.'})
        return {'n_people': 0, 'global_people': {}, 'params': {}}

    cfg = build_runtime_config(runtime_config)

    if cfg["enable_reid_embeddings"] and not any(m is not None for m in _reid_models.values()):
        msg = (
            "Re-ID embeddings au fost cerute din UI, dar modelul TransReID nu este "
            "incarcat pe niciun GPU. Continui cu YOLO + ByteTrack, fara Global ID nou."
        )
        print(f"[REID][CONFIG][WARN] {msg}")
        emit_fn('warmup_status', {
            'status': 'reid_warning',
            'message': msg,
        })
        cfg["enable_reid_embeddings"] = False

    print(f"\n{'='*60}")
    print(f"[REID] Incremental Re-ID: {len(cameras)} camere (cu emit frame JPEG)")
    print("[REID][CONFIG] Runtime Re-ID config:", cfg)
    print(f"[REID] Hardcoded pipeline: "
          f"SYNC_CAMERAS={SYNC_CAMERAS}, PROCESS_FRAME_EVERY={PROCESS_FRAME_EVERY}, "
          f"REID_EMIT_FRAME_EVERY={REID_EMIT_FRAME_EVERY}, IMG_SIZE={IMG_SIZE}, "
          f"CONF_THRESHOLD={CONF_THRESHOLD}")
    print(f"{'='*60}")

    emit_fn('warmup_status', {
        'status':  'reid_ready',
        'message': f'Incremental Re-ID pornit pe {len(cameras)} camere...'
    })

    if cfg["emit_debug_info"]:
        emit_fn("reid_config", {
            "runtime_config": cfg,
            "hardcoded_pipeline": {
                "CONF_THRESHOLD": CONF_THRESHOLD,
                "IMG_SIZE": IMG_SIZE,
                "PROCESS_FRAME_EVERY": PROCESS_FRAME_EVERY,
                "REID_EMIT_FRAME_EVERY": REID_EMIT_FRAME_EVERY,
                "REID_JPEG_QUALITY": REID_JPEG_QUALITY,
                "SEND_FRAME_MAX_WIDTH": SEND_FRAME_MAX_WIDTH,
                "SYNC_CAMERAS": SYNC_CAMERAS,
                "EMIT_REID_FRAMES": EMIT_REID_FRAMES,
            },
        })

    gallery = GlobalGallery(reid_threshold=cfg["reid_threshold"])
    if stop_event is None:
        stop_event = threading.Event()

    sync_ctx = FrameSync(
        n_cameras=len(cameras),
        enabled=SYNC_CAMERAS,
        timeout=SYNC_TIMEOUT_SEC,
    )

    if sync_ctx.enabled:
        print(f"[REID] Sincronizare camere ACTIVA: barrier per frame, timeout={SYNC_TIMEOUT_SEC}s")
    else:
        print("[REID] Sincronizare camere dezactivata sau o singura camera.")

    with ThreadPoolExecutor(max_workers=min(len(cameras), 4)) as ex:
        futures = {
            ex.submit(
                process_camera_incremental,
                cam['camera_name'],
                cam['video_id'],
                cam['video_path'],
                cam['gpu_id'],
                gallery,
                emit_fn,
                stop_event,
                sync_ctx,
                cfg,
            ): cam['camera_name']
            for cam in cameras
        }
        for f in as_completed(futures):
            cam_name = futures[f]
            try:
                f.result()
                print(f"[REID] Camera {cam_name} terminata.")
            except Exception as e:
                print(f"[REID] Eroare camera {cam_name}: {e}")
                sync_ctx.abort(stop_event)

    summary  = gallery.get_summary()
    n_people = len(summary)

    print(f"\n[REID] Pipeline complet: {n_people} persoane unice identificate")
    for gid, info in summary.items():
        print(
            f"  G{gid}: camere={info['cameras']}, "
            f"gallery_updates={info.get('n_gallery_updates')}, "
            f"track_embeddings={info.get('n_track_embeddings')}"
        )

    if cfg["emit_debug_info"]:
        emit_fn("reid_final_summary", {
            "n_people": n_people,
            "global_people": summary,
            "runtime_config": cfg,
        })

    return {
        'n_people':      n_people,
        'global_people': summary,
        'params': {
            'runtime_config': cfg,

            'REID_THRESHOLD':          cfg["reid_threshold"],
            'MIN_EMBEDDINGS_TO_MATCH': cfg["min_embeddings_to_match"],
            'ENABLE_REID_EMBEDDINGS':  cfg["enable_reid_embeddings"],
            'EMBEDDING_EVERY_SEEN':    cfg["embedding_every_seen"],
            'MAX_EMBEDDINGS':          cfg["max_embeddings"],
            'INTRA_THRESHOLD':         cfg["intra_threshold"],
            'PROCESS_FRAME_EVERY':     PROCESS_FRAME_EVERY,
            'REID_EMIT_FRAME_EVERY':   REID_EMIT_FRAME_EVERY,
            'REID_JPEG_QUALITY':       REID_JPEG_QUALITY,
            'SEND_FRAME_MAX_WIDTH':    SEND_FRAME_MAX_WIDTH,
            'SYNC_CAMERAS':            SYNC_CAMERAS,
        },
    }
