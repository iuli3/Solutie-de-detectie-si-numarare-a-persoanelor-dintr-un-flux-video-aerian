import os
import base64
import time
import threading
import queue
import subprocess
import select

import cv2
import ffmpeg
import numpy as np

STREAM_READ_TIMEOUT = 10
DISPLAY_WIDTH       = 1280
EMIT_FPS            = 10
QUEUE_MAXSIZE       = 32
JPEG_QUALITY        = 65

_FFMPEG_PIPE_EXTS = {'.mov', '.hevc', '.mts', '.m2ts'}

_SENTINEL = object()

def validate_video_file(video_path: str):
    """Verifica daca fisierul e bun. Returneaza (True, None) daca ok."""
    try:
        probe = subprocess.run(
            [
                'ffprobe', '-v', 'error',
                '-select_streams', 'v:0',
                '-show_entries', 'stream=width,height,codec_name',
                '-of', 'default=noprint_wrappers=1',
                video_path,
            ],
            capture_output=True, text=True, timeout=15,
        )
        if probe.returncode != 0 or not probe.stdout.strip():
            reason = probe.stderr.strip()[:300] or 'iesire goala'
            return False, f"ffprobe container: {reason}"

        info = dict(
            line.split('=', 1)
            for line in probe.stdout.strip().splitlines()
            if '=' in line
        )
        w, h = int(info.get('width', 0)), int(info.get('height', 0))
        if w == 0 or h == 0:
            return False, f"Dimensiuni invalide raportate de ffprobe: {w}x{h}"

        decode = subprocess.run(
            ['ffmpeg', '-v', 'error', '-i', video_path,
             '-vframes', '10', '-f', 'null', '-'],
            capture_output=True, text=True, timeout=20,
        )
        if decode.stderr.strip():
            return False, f"Bitstream corupt: {decode.stderr.strip()[:300]}"

        return True, None

    except subprocess.TimeoutExpired:
        return False, "Timeout validare (fisier posibil corupt sau blocat)"
    except FileNotFoundError:
        return None, "ffprobe/ffmpeg nu sunt instalate — validare omisa"
    except Exception as exc:
        return None, f"validate_video_file exceptie: {exc}"

def _probe_video(video_path: str):
    """Ia dimensiuni si fps din fisier."""
    try:
        result = subprocess.run(
            [
                'ffprobe', '-v', 'error', '-select_streams', 'v:0',
                '-show_entries', 'stream=width,height,r_frame_rate',
                '-of', 'default=noprint_wrappers=1',
                video_path,
            ],
            capture_output=True, text=True, timeout=15,
        )
        info = dict(
            line.split('=', 1)
            for line in result.stdout.strip().splitlines()
            if '=' in line
        )
        w   = int(info.get('width', 1280))
        h   = int(info.get('height', 720))
        num, den = info.get('r_frame_rate', '30/1').split('/')
        fps = max(1, round(int(num) / int(den)))
        return w, h, fps
    except Exception:
        return 1280, 720, 30

def _open_video_source(video_path: str):
    """Deschide fisier sau stream. Returneaza (source, is_pipe, w, h, fps)."""
    is_live  = video_path.startswith(('http', 'rtsp'))
    ext      = os.path.splitext(video_path)[1].lower()
    use_pipe = is_live or ext in _FFMPEG_PIPE_EXTS

    if use_pipe:
        if is_live:
            print(f"[READER] HLS/RTSP via ffmpeg pipe: {video_path}")
            w, h, fps = _probe_video(video_path)
            if w == 0 or h == 0:
                w, h, fps = 1280, 720, 25
        else:
            print(f"[READER] {ext} via ffmpeg pipe (HEVC-safe): {os.path.basename(video_path)}")
            w, h, fps = _probe_video(video_path)

        proc = subprocess.Popen(
            ['ffmpeg', '-i', video_path, '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-'],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=10 ** 8,
        )
        return proc, True, w, h, fps

    cap = cv2.VideoCapture(video_path)
    w   = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h   = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = int(cap.get(cv2.CAP_PROP_FPS)) or 30
    return cap, False, w, h, fps

def _read_frame(source, is_pipe: bool, orig_w: int, orig_h: int):
    """Citeste un frame. Returneaza (ok, frame)."""
    if not is_pipe:
        return source.read()

    frame_bytes = orig_w * orig_h * 3
    if source.poll() is not None:
        return False, None

    ready, _, _ = select.select([source.stdout], [], [], STREAM_READ_TIMEOUT)
    if not ready:
        print(f"[READER] Nicio data in {STREAM_READ_TIMEOUT}s — stream mort.")
        return False, None

    raw = source.stdout.read(frame_bytes)
    if not raw or len(raw) < frame_bytes:
        return False, None

    frame = np.frombuffer(raw, dtype=np.uint8).reshape((orig_h, orig_w, 3)).copy()
    return True, frame

def _release_source(source, is_pipe: bool):
    if is_pipe:
        try:
            source.stdout.close()
        except Exception:
            pass
        try:
            source.terminate()
            source.wait(timeout=3)
        except Exception:
            try:
                source.kill()
            except Exception:
                pass
    else:
        source.release()

def _encode_browser_mp4(input_path: str, output_path: str):
    last_error = None
    codecs = [
        {"vcodec": "libx264", "preset": "ultrafast"},
        {"vcodec": "h264_nvenc", "preset": "p1"},
    ]

    for opts in codecs:
        try:
            (
                ffmpeg
                .input(input_path)
                .output(
                    output_path,
                    pix_fmt="yuv420p",
                    movflags="+faststart",
                    loglevel="error",
                    **opts,
                )
                .overwrite_output()
                .run(capture_stdout=True, capture_stderr=True)
            )
            return True
        except ffmpeg.Error as exc:
            last_error = exc.stderr.decode("utf-8", errors="ignore") if exc.stderr else str(exc)
            print(f"[ENCODE][WARN] {opts['vcodec']} failed: {last_error}")
        except Exception as exc:
            last_error = str(exc)
            print(f"[ENCODE][WARN] {opts['vcodec']} failed: {last_error}")

    raise RuntimeError(f"Browser-compatible H.264 encode failed: {last_error}")

def _get_total_frames(source, is_pipe: bool, is_live: bool, video_path: str, fps: int) -> int:
    """Estimeaza frame-urile totale. 0 daca nu se stie."""
    if is_live:
        return 0
    if not is_pipe:
        return int(source.get(cv2.CAP_PROP_FRAME_COUNT))
    try:
        r = subprocess.run(
            [
                'ffprobe', '-v', 'error', '-select_streams', 'v:0',
                '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1',
                video_path,
            ],
            capture_output=True, text=True, timeout=15,
        )
        dur = float(next(
            (l.split('=')[1] for l in r.stdout.splitlines() if 'duration' in l), '0'
        ))
        return int(dur * fps)
    except Exception:
        return 0

# ---------------------------------------------------------------------------
# Adnotare frame
# ---------------------------------------------------------------------------

def _annotate_frame(frame: np.ndarray, boxes_xyxy: np.ndarray, track_ids) -> list:
    """Deseneaza boxuri pe frame. Returneaza lista de detectii."""
    detected = []
    for i, box in enumerate(boxes_xyxy):
        x1, y1, x2, y2 = map(int, box)
        tid = int(track_ids[i]) if track_ids is not None else None
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
        if tid is not None:
            cv2.putText(
                frame, str(tid), (x1, y1 - 4),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1,
            )
        detected.append({
            'id':   tid if tid is not None else i,
            'bbox': [x1, y1, x2 - x1, y2 - y1],
        })
    return detected

# ---------------------------------------------------------------------------
# Pipeline principal
# ---------------------------------------------------------------------------

def process_video_stream(
    video_path:       str,
    output_dir:       str,
    socketio,
    video_id,
    model_instance,
    processing_state: dict = None,
):
    """
    Pipeline YOLO detection + ByteTrack.

    Arhitectura:
        Thread Reader → frame_q → Thread Inferrer
                                       ├── scrie frame in VideoWriter
                                       └── emite spre frontend (throttled)

    Emit-ul se face exclusiv din Inferrer — un singur thread apeleaza
    socketio.emit(), eliminand orice risc de blocare cu async_mode='threading'.

    Returneaza acelasi dict ca versiunea anterioara.
    """
    os.makedirs(output_dir, exist_ok=True)

    if processing_state is None:
        processing_state = {'mode': 'detection'}

    def stop_requested() -> bool:
        return bool(processing_state.get('stop_requested'))

    # ── Deschide sursa ───────────────────────────────────────────────────────
    is_live = video_path.startswith(('http', 'rtsp'))

    try:
        source, is_pipe, orig_w, orig_h, fps = _open_video_source(video_path)
    except Exception as exc:
        return {'error': f"Nu s-a putut deschide sursa video: {exc}"}

    if orig_w == 0 or orig_h == 0:
        _release_source(source, is_pipe)
        return {'error': 'Dimensiuni video invalide (0×0) — stream indisponibil'}

    processing_state['source_handle']    = source
    processing_state['is_stream_source'] = is_pipe

    total_frames   = _get_total_frames(source, is_pipe, is_live, video_path, fps)
    display_height = int(orig_h * DISPLAY_WIDTH / orig_w)

    # ── Paths output ─────────────────────────────────────────────────────────
    base_name       = f"live_{video_id}" if is_live else os.path.splitext(os.path.basename(video_path))[0]
    proc_filename   = f"processed_{base_name}.mp4"
    temp_proc_path  = os.path.join(output_dir, f"temp_{proc_filename}")
    final_proc_path = os.path.join(output_dir, proc_filename)

    out_writer = cv2.VideoWriter(
        temp_proc_path,
        cv2.VideoWriter_fourcc(*'mp4v'),
        fps,
        (DISPLAY_WIDTH, display_height),
    )

    # ── Reset tracker state din procesarea anterioara ────────────────────────
    if getattr(model_instance, 'predictor', None) is not None:
        model_instance.predictor = None

    # ── Coada reader → inferrer ──────────────────────────────────────────────
    frame_q = queue.Queue(maxsize=QUEUE_MAXSIZE)

    # ── Statistici — scrise DOAR din Inferrer, fara lock necesar ─────────────
    stats = {
        'frame_count':      0,
        'processed_count':  0,
        'max_people_seen':  0,
        'total_detections': 0,
        'track_data':       {},     # tid → {'start': int, 'end': int}
        'was_stopped':      False,
        'start_time':       time.time(),
    }

    emit_interval  = 1.0 / EMIT_FPS
    last_emit_time = 0.0

    # ── Thread 1: Reader ─────────────────────────────────────────────────────
    def reader_thread():
        try:
            while not stop_requested():
                ok, frame = _read_frame(source, is_pipe, orig_w, orig_h)
                if not ok:
                    if not is_pipe and total_frames > 0:
                        socketio.emit('status_update', {
                            'msg': 'Cadre procesate 100%. Se finalizeaza video-ul...'
                        })
                    break
                # back-pressure natural: blocheaza daca Inferrer e mai lent
                frame_q.put(frame)
        except Exception as exc:
            print(f"[READER] Exceptie: {exc}")
        finally:
            frame_q.put(_SENTINEL)

    # ── Thread 2: Inferrer + Writer + Emit ───────────────────────────────────
    def inferrer_thread():
        nonlocal last_emit_time

        while True:
            item = frame_q.get()

            # Sentinel → video terminat normal
            if item is _SENTINEL:
                break

            # Stop solicitat extern
            if stop_requested():
                stats['was_stopped'] = True
                # Golim coada ca Reader-ul sa nu ramana blocat in frame_q.put()
                while True:
                    try:
                        frame_q.get_nowait()
                    except queue.Empty:
                        break
                break

            frame = item
            stats['frame_count'] += 1
            frame_idx = stats['frame_count']

            # ── Inferenta YOLO detection-only ────────────────────────────────
            # Pentru aerial detection/counting folosim predict(), nu track(),
            # ca sa evitam overhead-ul ByteTrack si ID-urile instabile.
            # Rezolutia ramane 1280, deci nu pierdem avantajul pentru persoane mici.
            t0 = time.time()
            results = model_instance.predict(
                frame,
                imgsz=1280,
                conf=0.25,
                iou=0.45,
                classes=[0],
                verbose=False,
            )
            inf_time = time.time() - t0

            # ── Extragere detectii ───────────────────────────────────────────
            boxes      = results[0].boxes
            n_people   = len(boxes)
            boxes_xyxy = boxes.xyxy.cpu().numpy() if n_people > 0 else np.empty((0, 4))
            # In detection-only mode nu folosim ID-uri ByteTrack.
            track_ids = None

            # ── Actualizare statistici ───────────────────────────────────────
            density_coeff = 0.0
            stats['processed_count'] += 1

            if n_people > 0:
                if n_people > stats['max_people_seen']:
                    stats['max_people_seen'] = n_people
                stats['total_detections'] += n_people

                areas = (
                    (boxes_xyxy[:, 2] - boxes_xyxy[:, 0]) *
                    (boxes_xyxy[:, 3] - boxes_xyxy[:, 1])
                )
                density_coeff = float(round(
                    np.sum(areas) / (orig_w * orig_h) * 100, 2
                ))

                if track_ids is not None:
                    for tid in track_ids.tolist():
                        if tid not in stats['track_data']:
                            stats['track_data'][tid] = {'start': frame_idx, 'end': frame_idx}
                        else:
                            stats['track_data'][tid]['end'] = frame_idx

            # ── Adnotare + resize ────────────────────────────────────────────
            detected_objects = _annotate_frame(frame, boxes_xyxy, track_ids)
            final_frame = cv2.resize(
                frame, (DISPLAY_WIDTH, display_height),
                interpolation=cv2.INTER_LINEAR,
            )

            # ── Scriere VideoWriter ──────────────────────────────────────────
            out_writer.write(final_frame)

            # ── Emit throttled spre frontend ─────────────────────────────────
            # Emit-ul e din acest thread — singurul care apeleaza socketio,
            # deci nu exista race condition cu async_mode='threading'.
            now = time.time()
            if (now - last_emit_time) >= emit_interval and not stop_requested():
                last_emit_time = now
                _, buf = cv2.imencode(
                    '.jpg', final_frame,
                    [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY],
                )
                progress = (
                    round(frame_idx / total_frames * 100, 1)
                    if total_frames > 0 else 0
                )
                socketio.emit('frame', {
                    'frame':                base64.b64encode(buf).decode('utf-8'),
                    'heatmap':              None,
                    'density_coeff':        density_coeff,
                    'people_count':         n_people,
                    'people_count_yolo':    n_people,
                    'people_count_dmcount': None,
                    'is_crowd_mode':        False,
                    'progress':             progress,
                    'metadata':             detected_objects,
                    'video_id':             video_id,
                    'frame_number':         frame_idx,
                    'total_frames':         total_frames,
                    'inference_time':       inf_time,
                    'timestamp':            now,
                })

    # ── Pornire thread-uri ───────────────────────────────────────────────────
    t_reader   = threading.Thread(target=reader_thread,   daemon=True, name="yolo-reader")
    t_inferrer = threading.Thread(target=inferrer_thread, daemon=True, name="yolo-inferrer")

    t_reader.start()
    t_inferrer.start()

    t_reader.join()
    t_inferrer.join()

    # ── Cleanup ──────────────────────────────────────────────────────────────
    _release_source(source, is_pipe)
    out_writer.release()

    processing_state.pop('source_handle',    None)
    processing_state.pop('is_stream_source', None)

    # ── Daca s-a oprit manual ────────────────────────────────────────────────
    if stats['was_stopped'] or stop_requested():
        for p in [temp_proc_path, final_proc_path]:
            if os.path.exists(p):
                try:
                    os.remove(p)
                except OSError:
                    pass
        return {
            'stopped':                    True,
            'processed_filename':         None,
            'processed_heatmap_filename': None,
            'processing_time':            round(time.time() - stats['start_time'], 2),
            'resolution':                 f"{orig_w}x{orig_h}",
        }

    # ── Recompresie H.264 ────────────────────────────────────────────────────
    if not is_live:
        _encode_browser_mp4(temp_proc_path, final_proc_path)
        if os.path.exists(temp_proc_path):
            os.remove(temp_proc_path)
        try:
            ffmpeg.input(temp_proc_path).output(
                final_proc_path,
                vcodec   = 'libx264',
                preset   = 'ultrafast',
                loglevel = 'quiet',
            ).overwrite_output().run()
            if os.path.exists(temp_proc_path):
                os.remove(temp_proc_path)
        except Exception:
            # Fallback: folosim fisierul temp necomprimat
            if os.path.exists(temp_proc_path):
                os.rename(temp_proc_path, final_proc_path)
        socketio.emit('status_update', {'msg': 'Finalizare video completa.'})

    # ── Statistici finale ────────────────────────────────────────────────────
    track_data      = stats['track_data']
    processed_count = max(stats['processed_count'], 1)

    TRACK_MIN_FRAMES = 5

    filtered_track_data = {
        tid: d
        for tid, d in track_data.items()
        if (d.get('end', 0) - d.get('start', 0) + 1) >= TRACK_MIN_FRAMES
    }

    analytics_data = {
        str(tid): {'start_frame': d['start'], 'end_frame': d['end']}
        for tid, d in filtered_track_data.items()
    }

    max_people_in_frame = stats['max_people_seen']
    avg_people_per_frame = round(stats['total_detections'] / processed_count, 2)

    return {
        'max_people_in_frame':        max_people_in_frame,
        'avg_people_per_frame':       avg_people_per_frame,

        # Pentru aerial/top-view counting, asta e estimarea mai corecta.
        # Nu folosim len(track_data), pentru ca ByteTrack poate crea ID-uri multiple
        # pentru aceeasi persoana.
        'unique_people':              max_people_in_frame,

        # Metrici tehnice, daca vrei sa le afisezi separat.
        'raw_track_ids':              len(track_data),
        'filtered_track_ids':         len(filtered_track_data),
        'track_min_frames':           TRACK_MIN_FRAMES,

        'analytics_data':             analytics_data,
        'fps':                        fps,
        'processed_filename':         proc_filename if not is_live else None,
        'processed_heatmap_filename': None,
        'processing_time':            round(time.time() - stats['start_time'], 2),
        'resolution':                 f"{orig_w}x{orig_h}",
    }
