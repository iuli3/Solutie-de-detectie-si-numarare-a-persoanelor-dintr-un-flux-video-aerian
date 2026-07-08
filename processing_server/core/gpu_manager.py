import os
import threading
import subprocess
import csv
import time
from io import StringIO
from ultralytics import YOLO
import torch
import numpy as np
from rich.console import Console

console = Console()

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
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
console.print(f"[INIT] GPU 0 este preferinta primara pentru YOLO", style="yellow")

GPU_POLICY = {
    "detection": {"min_free_mb": 8000, "max_util": 98},
    "crowd":     {"min_free_mb": 16000, "max_util": 95},
    "reid":      {"min_free_mb": 20000, "max_util": 90},
}

def _query_gpu_snapshot():
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

def wait_for_available_gpu(mode="detection", video_id=None, poll_sec=10, is_stop_fn=None, socketio=None):
    video_key = str(video_id) if video_id is not None else None

    while True:
        if video_key and is_stop_fn and is_stop_fn(video_key):
            return None

        gid = get_best_gpu_for_mode(mode)
        if gid is not None:
            return gid

        if video_id is not None and socketio:
            socketio.emit("status_update", {
                "video_id": video_id,
                "msg": "Toate GPU-urile sunt ocupate. Jobul asteapta in coada..."
            })

        time.sleep(poll_sec)

def load_yolo_for_gpu(gpu_id):
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
    return 0
