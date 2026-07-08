from app import db
from models import Video


def _current_user_id():
    from models import User
    return User.query.filter_by(email="ana@example.com").first().id


def _create_video(user_id, **kwargs):
    defaults = {
        "filename": "processed.mp4",
        "minio_path": "user_1/original.mp4",
        "processed_video_path": "user_1/processed.mp4",
        "heatmap_video_path": "user_1/heatmap.mp4",
        "status": "Completed",
        "total_unique_people": 12,
        "max_people_in_frame": 5,
        "avg_people_per_frame": 2.5,
        "dm_model_used": None,
        "user_id": user_id,
    }
    defaults.update(kwargs)
    video = Video(**defaults)
    db.session.add(video)
    db.session.commit()
    return video


def test_video_metadata_returns_detection_fields(client, auth_header):
    with client.application.app_context():
        video = _create_video(_current_user_id())
        video_id = video.id

    response = client.get(f"/api/videos/{video_id}/metadata", headers=auth_header)

    assert response.status_code == 200
    body = response.get_json()
    assert body["filename"] == "processed.mp4"
    assert body["processing_mode"] == "detection"
    assert body["has_heatmap"] is True
    assert body["processed_video_url"] == f"/api/video/watch/{video_id}?variant=normal"


def test_video_metadata_marks_crowd_mode(client, auth_header):
    with client.application.app_context():
        video = _create_video(_current_user_id(), dm_model_used="qnrf", filename="crowd.mp4")
        video_id = video.id

    response = client.get(f"/api/videos/{video_id}/metadata", headers=auth_header)

    assert response.status_code == 200
    assert response.get_json()["processing_mode"] == "crowd"


def test_watch_variants_requires_processed_video(client):
    from conftest import auth_headers

    headers = auth_headers(client)
    with client.application.app_context():
        video = _create_video(_current_user_id(), processed_video_path=None, heatmap_video_path=None)
        video_id = video.id

    response = client.get(f"/api/video/watch/{video_id}/variants", headers=headers)

    assert response.status_code == 404


def test_watch_variants_returns_heatmap_info(client, auth_header):
    with client.application.app_context():
        video = _create_video(_current_user_id())
        video_id = video.id

    response = client.get(f"/api/video/watch/{video_id}/variants")

    assert response.status_code == 200
    body = response.get_json()
    assert body["heatmap_available"] is True
    assert body["normal"] == f"/api/video/watch/{video_id}?variant=normal"


def test_delete_video_removes_owner_video(client, auth_header):
    with client.application.app_context():
        video = _create_video(_current_user_id(), filename="delete-me.mp4")
        video_id = video.id

    response = client.delete(f"/api/videos/{video_id}", headers=auth_header)

    assert response.status_code == 200
    assert response.get_json()["message"] == "Deleted"
    with client.application.app_context():
        assert db.session.get(Video, video_id) is None
