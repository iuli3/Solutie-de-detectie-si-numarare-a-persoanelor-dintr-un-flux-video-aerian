from app import db
from models import TrackingSession, TrackingSessionCamera, User, Video


def _user_id(email="ana@example.com"):
    return User.query.filter_by(email=email).first().id


def _create_tracking_session(user_id):
    video = Video(filename="cam-a.mp4", minio_path="user_1/cam-a.mp4", status="Completed", user_id=user_id)
    db.session.add(video)
    db.session.flush()
    session = TrackingSession(
        job_id="job-123",
        user_id=user_id,
        status="Completed",
        n_people=3,
        reid_config={"preset": "balanced"},
        global_people_summary={"G1": {"cameras": ["A"]}},
        summary_json_path="sessions/job-123/summary.json",
    )
    db.session.add(session)
    db.session.flush()
    camera = TrackingSessionCamera(
        session_id=session.id,
        video_id=video.id,
        camera_name="Camera A",
        camera_order=1,
        status="Completed",
        detections_json_path="sessions/job-123/cam-a.json",
        processed_video_path="sessions/job-123/cam-a.mp4",
    )
    db.session.add(camera)
    db.session.commit()
    return session


def test_list_tracking_sessions_returns_only_current_user(client, auth_header):
    from conftest import auth_headers

    other_header = auth_headers(client, email="other-tracking@example.com")
    with client.application.app_context():
        mine = _create_tracking_session(_user_id("ana@example.com"))
        _create_tracking_session(_user_id("other-tracking@example.com"))
        mine_id = mine.id

    response = client.get("/api/tracking-sessions", headers=auth_header)

    assert response.status_code == 200
    sessions = response.get_json()["sessions"]
    assert len(sessions) == 1
    assert sessions[0]["id"] == mine_id
    assert sessions[0]["cameras"][0]["camera_name"] == "Camera A"


def test_get_tracking_session_requires_owner(client, auth_header):
    from conftest import auth_headers

    other_header = auth_headers(client, email="tracking-owner@example.com")
    with client.application.app_context():
        other = _create_tracking_session(_user_id("tracking-owner@example.com"))
        other_id = other.id

    response = client.get(f"/api/tracking-sessions/{other_id}", headers=auth_header)

    assert response.status_code == 404


def test_delete_tracking_session_removes_session_and_cameras(client, auth_header):
    with client.application.app_context():
        session = _create_tracking_session(_user_id())
        session_id = session.id

    response = client.delete(f"/api/tracking-sessions/{session_id}", headers=auth_header)

    assert response.status_code == 200
    with client.application.app_context():
        assert db.session.get(TrackingSession, session_id) is None
        assert TrackingSessionCamera.query.count() == 0
