import os
import json
from flask import request, jsonify
from werkzeug.utils import secure_filename
from extensions import db
from models import Video, PersonLog

UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", "/tmp/uploads")

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

def update_video_status(video_id, status, app):
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

def save_results_to_db(video_id, stats, processed_video_path=None, heatmap_video_path=None, app=None):
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
