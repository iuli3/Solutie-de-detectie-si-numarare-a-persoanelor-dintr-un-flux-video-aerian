import os
import threading
import uuid
import inspect
from concurrent.futures import ThreadPoolExecutor, as_completed
from extensions import db
from models import GlobalPerson, MultiCamLog
from .minio_client import download_file_from_minio

UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", "/tmp/uploads")
RESULTS_FOLDER = os.getenv("RESULTS_FOLDER", "/tmp/results")
KEEP_REID_CACHE = os.getenv("KEEP_REID_CACHE", "0").lower() in ("1", "true")

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

def make_reid_emit_fn(job_id=None, emit_live_events=True, socketio=None):
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
        if socketio:
            socketio.emit(event, payload)

    return emit_reid_event

def call_process_reid_multicamera(cameras, socketio_obj, emit_fn, results_folder,
                                  stop_event=None, runtime_config=None, process_reid_multicamera_fn=None):
    kwargs = {
        'cameras': cameras,
        'socketio_obj': socketio_obj,
        'emit_fn': emit_fn,
        'results_folder': results_folder,
        'stop_event': stop_event,
    }

    if runtime_config:
        try:
            if process_reid_multicamera_fn:
                sig = inspect.signature(process_reid_multicamera_fn)
                if 'runtime_config' in sig.parameters:
                    kwargs['runtime_config'] = runtime_config
                    print("[REID][CONFIG] Passing runtime_config to tracking_inference.py:", runtime_config)
                else:
                    print(
                        "[REID][CONFIG][WARN] tracking_inference.py nu accepta runtime_config"
                    )
        except (TypeError, ValueError) as sig_err:
            print(f"[REID][CONFIG][WARN] Nu pot inspecta semnatura: {sig_err}.")

    if process_reid_multicamera_fn:
        return process_reid_multicamera_fn(**kwargs)
    return {}

def launch_reid_processing(cameras, save_to_db, reid_event_ref, job_id=None, emit_live_events=True,
                          reid_config=None, app=None, socketio=None, process_reid_multicamera_fn=None):
    def run_reid():
        try:
            result = call_process_reid_multicamera(
                cameras=cameras,
                socketio_obj=socketio,
                emit_fn=make_reid_emit_fn(job_id=job_id, emit_live_events=emit_live_events, socketio=socketio),
                results_folder=RESULTS_FOLDER,
                stop_event=reid_event_ref,
                runtime_config=reid_config,
                process_reid_multicamera_fn=process_reid_multicamera_fn,
            )
            was_stopped = reid_event_ref.is_set()
            global_people = result.get('global_people', {})

            if was_stopped:
                print(f"[REID] Oprit de utilizator dupa {len(global_people)} persoane procesate.")
                if socketio:
                    socketio.emit('reid_stopped', {'message': 'Re-ID oprit de utilizator.'})
                return

            if save_to_db:
                try:
                    if socketio:
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
                    if socketio:
                        socketio.emit('warmup_status', {
                            'job_id': job_id,
                            'status': 'db_save_complete',
                            'message': f'Salvate {len(global_people)} persoane globale in baza de date.'
                        })
                    print(f"[REID][DB] Salvate {len(global_people)} persoane globale.")
                except Exception as db_err:
                    print(f"[REID][DB ERROR] {db_err}")
                    if socketio:
                        socketio.emit('error', {'message': f'Eroare salvare DB Re-ID: {str(db_err)}'})
                    return
            else:
                print("[REID][DB] save_to_db=False, sar peste salvarea in DB.")

            if socketio:
                socketio.emit('reid_complete', {
                    'job_id':        job_id,
                    'n_people':      result.get('n_people', 0),
                    'global_people': global_people,
                    'cameras':       result.get('cameras', [
                        {
                            'video_id': cam['video_id'],
                            'camera_name': cam['camera_name'],
                            'camera_order': cam.get('camera_order'),
                        }
                        for cam in cameras
                    ]),
                    'params':        result.get('params', {}),
                    'saved_to_db':   save_to_db,
                    'message':       f'Re-ID complet: {result.get("n_people", 0)} persoane identificate'
                })
            print(f"[REID] Complet: {result.get('n_people', 0)} persoane")

        except Exception as e:
            print(f"[REID] Eroare: {e}")
            if socketio:
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

    threading.Thread(target=run_reid, daemon=True).start()
