"""
crowd_inference.py
Pipeline dedicat pentru crowd counting cu DM-Count.
Fara bounding boxes YOLO, doar density map + estimare numar persoane.
"""

import cv2
import os
import base64
import time
import numpy as np
import ffmpeg
import subprocess
import select
from .dmcount_inference import get_dmcount

STREAM_READ_TIMEOUT = 10

_FFMPEG_PIPE_EXTS = {'.mov', '.hevc', '.mts', '.m2ts'}

def _probe_video(video_path):
    try:
        result = subprocess.run([
            'ffprobe', '-v', 'error', '-select_streams', 'v:0',
            '-show_entries', 'stream=width,height,r_frame_rate',
            '-of', 'default=noprint_wrappers=1', video_path
        ], capture_output=True, text=True, timeout=15)
        info = {}
        for line in result.stdout.strip().split('\n'):
            if '=' in line:
                k, v = line.split('=', 1)
                info[k.strip()] = v.strip()
        w = int(info.get('width', 1280))
        h = int(info.get('height', 720))
        num, den = info.get('r_frame_rate', '30/1').split('/')
        fps = max(1, round(int(num) / int(den)))
        return w, h, fps
    except Exception:
        return 1280, 720, 30

def open_video_source(video_path):
    is_stream = video_path.startswith('http') or video_path.startswith('rtsp')
    ext = os.path.splitext(video_path)[1].lower()
    use_pipe = is_stream or ext in _FFMPEG_PIPE_EXTS

    if use_pipe:
        if is_stream:
            print(f"[CROWD] Deschidere stream: {video_path}")

            w, h, fps = 1280, 720, 11
            command = [
                'ffmpeg',
                '-loglevel', 'error',
                '-i', video_path,
                '-vf', f'scale={w}:{h}',
                '-an',
                '-f', 'rawvideo',
                '-pix_fmt', 'bgr24',
                '-'
            ]
        else:
            print(f"[CROWD] Deschidere {ext} prin ffmpeg pipe (HEVC-safe): {os.path.basename(video_path)}")
            w, h, fps = _probe_video(video_path)
            command = [
                'ffmpeg',
                '-loglevel', 'error',
                '-i', video_path,
                '-an',
                '-f', 'rawvideo',
                '-pix_fmt', 'bgr24',
                '-'
            ]

        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=10**8
        )
        return process, True, w, h, fps

    else:
        cap = cv2.VideoCapture(video_path)
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = int(cap.get(cv2.CAP_PROP_FPS)) or 30
        return cap, False, w, h, fps

def read_frame_from_source(source, is_stream, orig_w, orig_h):
    if is_stream:
        frame_size = orig_w * orig_h * 3
        if source.poll() is not None:
            return False, None
        ready, _, _ = select.select([source.stdout], [], [], STREAM_READ_TIMEOUT)
        if not ready:
            print(f"[CROWD] Nicio data in {STREAM_READ_TIMEOUT}s — stream inchis.")
            return False, None
        raw = source.stdout.read(frame_size)
        if not raw or len(raw) < frame_size:
            return False, None
        frame = np.frombuffer(raw, dtype=np.uint8).reshape((orig_h, orig_w, 3)).copy()
        return True, frame
    else:
        return source.read()

def release_source(source, is_stream):
    if is_stream:
        source.stdout.close()
        source.terminate()
        source.wait()
    else:
        source.release()

def process_crowd_stream(video_path, output_dir, socketio, video_id, processing_state=None):
    """
    Pipeline crowd counting cu DM-Count pur.
    Nu foloseste YOLO deloc — nu are nevoie de model_instance.
    """
    os.makedirs(output_dir, exist_ok=True)

    source, is_stream, orig_w, orig_h, fps = open_video_source(video_path)

    if processing_state is not None:
        processing_state['source_handle'] = source
        processing_state['is_stream_source'] = is_stream

    if orig_w == 0 or orig_h == 0:
        return {"error": "Dimensiuni video invalide (0x0)"}

    is_live = video_path.startswith('http') or video_path.startswith('rtsp')
    if is_live:
        total_frames = 0
    elif is_stream:
        _, _, probe_fps = _probe_video(video_path)
        try:
            r = subprocess.run(
                ['ffprobe', '-v', 'error', '-select_streams', 'v:0',
                 '-show_entries', 'format=duration',
                 '-of', 'default=noprint_wrappers=1', video_path],
                capture_output=True, text=True, timeout=15
            )
            dur = float(next((l.split('=')[1] for l in r.stdout.splitlines() if 'duration' in l), '0'))
            total_frames = int(dur * probe_fps)
        except Exception:
            total_frames = 0
    else:
        total_frames = int(source.get(cv2.CAP_PROP_FRAME_COUNT))

    DISPLAY_WIDTH = 1280
    SCALE_FACTOR = DISPLAY_WIDTH / orig_w
    DISPLAY_HEIGHT = int(orig_h * SCALE_FACTOR)

    base_name = f"live_{video_id}" if is_live else os.path.splitext(os.path.basename(video_path))[0]
    processed_filename = f"processed_{base_name}.mp4"
    processed_heatmap_filename = f"heatmap_{processed_filename}"
    temp_output_path = os.path.join(output_dir, f"temp_{processed_filename}")
    final_output_path = os.path.join(output_dir, processed_filename)
    temp_heatmap_output_path = os.path.join(output_dir, f"temp_{processed_heatmap_filename}")
    final_heatmap_output_path = os.path.join(output_dir, processed_heatmap_filename)

    out = cv2.VideoWriter(temp_output_path, cv2.VideoWriter_fourcc(*'mp4v'), fps, (DISPLAY_WIDTH, DISPLAY_HEIGHT))
    out_heatmap = cv2.VideoWriter(temp_heatmap_output_path, cv2.VideoWriter_fourcc(*'mp4v'), fps, (DISPLAY_WIDTH, DISPLAY_HEIGHT))

    if processing_state is None:
        processing_state = {'mode': 'crowd', 'dm_model': 'qnrf'}

    dm_model_name = processing_state.get('dm_model', 'qnrf')
    dmcount = get_dmcount(device="cuda:0", model_name=dm_model_name)
    if dmcount is None:
        return {"error": f"DM-Count model '{dm_model_name}' indisponibil"}

    print(f"[CROWD] DM-Count activ: model={dm_model_name}")

    frame_count = 0
    processed_count = 0
    FRAME_SKIP = 2
    last_count = 0.0
    last_heatmap = None
    total_count_sum = 0.0
    max_count_seen = 0
    has_heatmap_overlay = False
    start_time_global = time.time()
    was_stopped = False

    def stop_requested():
        return bool(processing_state.get('stop_requested'))

    try:
        while True:
            if stop_requested():
                was_stopped = True
                break

            ret, frame = read_frame_from_source(source, is_stream, orig_w, orig_h)
            if not ret:
                if not is_stream and total_frames > 0:
                    socketio.emit('status_update', {'msg': 'Cadre procesate 100%. Se finalizeaza video-ul crowd...'})
                break

            frame_count += 1
            if frame_count % FRAME_SKIP != 0:
                continue

            if stop_requested():
                was_stopped = True
                break

            t_start = time.time()
            processed_count += 1

            final_frame = cv2.resize(frame, (DISPLAY_WIDTH, DISPLAY_HEIGHT), interpolation=cv2.INTER_CUBIC)
            out.write(final_frame)

            will_emit = not stop_requested() and (processed_count % 2 == 0)

            if will_emit:
                try:
                    dm_count, dm_heatmap = dmcount.predict(frame)
                    last_count = dm_count
                    last_heatmap = dm_heatmap
                    if dm_count > max_count_seen:
                        max_count_seen = int(round(dm_count))
                except Exception as e:
                    print(f"[CROWD] Eroare DM-Count: {e}")

            inference_time = time.time() - t_start
            total_count_sum += last_count

            final_heatmap_frame = final_frame
            if last_heatmap:
                try:
                    heatmap_bytes = base64.b64decode(last_heatmap)
                    heatmap_np = np.frombuffer(heatmap_bytes, dtype=np.uint8)
                    heatmap_img = cv2.imdecode(heatmap_np, cv2.IMREAD_COLOR)
                    if heatmap_img is not None:
                        heatmap_resized = cv2.resize(heatmap_img, (DISPLAY_WIDTH, DISPLAY_HEIGHT), interpolation=cv2.INTER_CUBIC)
                        final_heatmap_frame = cv2.addWeighted(final_frame, 0.6, heatmap_resized, 0.4, 0)
                        has_heatmap_overlay = True
                except Exception:
                    pass
            out_heatmap.write(final_heatmap_frame)

            if will_emit:
                _, buffer = cv2.imencode('.jpg', final_frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                socketio.emit('frame', {
                    'frame': base64.b64encode(buffer).decode('utf-8'),
                    'heatmap': last_heatmap,
                    'density_coeff': 0.0,
                    'people_count': int(round(last_count)),
                    'people_count_yolo': 0,
                    'people_count_dmcount': int(round(last_count)),
                    'is_crowd_mode': True,
                    'progress': round((frame_count / total_frames) * 100, 1) if total_frames > 0 else 0,
                    'metadata': [],
                    'video_id': video_id,
                    'frame_number': frame_count,
                    'total_frames': total_frames,
                    'inference_time': inference_time,
                    'timestamp': time.time()
                })

            if stop_requested():
                was_stopped = True
                break

    except Exception as e:
        print(f"[CROWD ERROR] {e}")
        return {"error": str(e)}

    finally:
        release_source(source, is_stream)
        out.release()
        out_heatmap.release()
        if processing_state is not None:
            processing_state.pop('source_handle', None)
            processing_state.pop('is_stream_source', None)

    if was_stopped:
        for p in [temp_output_path, final_output_path, temp_heatmap_output_path, final_heatmap_output_path]:
            if os.path.exists(p):
                try: os.remove(p)
                except OSError: pass
        return {
            "stopped": True,
            "processed_filename": None,
            "processed_heatmap_filename": None,
            "processing_time": round(time.time() - start_time_global, 2),
            "resolution": f"{orig_w}x{orig_h}"
        }

    if not is_live:
        socketio.emit('status_update', {'msg': 'Finalizare video crowd (recompresie)...'})
        try:
            ffmpeg.input(temp_output_path).output(
                final_output_path, vcodec='libx264', preset='ultrafast', loglevel="quiet"
            ).overwrite_output().run()
            if os.path.exists(temp_output_path):
                os.remove(temp_output_path)
        except:
            if os.path.exists(temp_output_path):
                os.rename(temp_output_path, final_output_path)

        try:
            ffmpeg.input(temp_heatmap_output_path).output(
                final_heatmap_output_path, vcodec='libx264', preset='ultrafast', loglevel="quiet"
            ).overwrite_output().run()
            if os.path.exists(temp_heatmap_output_path):
                os.remove(temp_heatmap_output_path)
        except:
            if os.path.exists(temp_heatmap_output_path):
                os.rename(temp_heatmap_output_path, final_heatmap_output_path)

        if not has_heatmap_overlay and os.path.exists(final_heatmap_output_path):
            os.remove(final_heatmap_output_path)
        socketio.emit('status_update', {'msg': 'Finalizare video crowd completa.'})

    avg_count = round(total_count_sum / processed_count, 1) if processed_count > 0 else 0

    return {
        "max_people_in_frame": max_count_seen,
        "avg_people_per_frame": avg_count,
        "unique_people": max_count_seen,
        "processed_filename": processed_filename if not is_live else None,
        "processed_heatmap_filename": processed_heatmap_filename if has_heatmap_overlay else None,
        "processing_time": round(time.time() - start_time_global, 2),
        "resolution": f"{orig_w}x{orig_h}"
    }