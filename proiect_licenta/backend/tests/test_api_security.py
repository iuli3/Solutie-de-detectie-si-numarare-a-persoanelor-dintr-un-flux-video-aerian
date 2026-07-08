from io import BytesIO

from conftest import auth_headers


def test_dashboard_requires_authentication(client):
    response = client.get("/api/dashboard-stats")

    assert response.status_code == 401


def test_upload_requires_authentication(client):
    response = client.post(
        "/upload",
        data={"video": (BytesIO(b"fake video"), "clip.mp4")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 401


def test_upload_rejects_missing_file(client, auth_header):
    response = client.post("/upload", headers=auth_header, data={}, content_type="multipart/form-data")

    assert response.status_code == 400
    assert response.get_json()["error"] == "No file uploaded"


def test_user_cannot_access_other_users_video_metadata(client, auth_header):
    from app import Video, db

    other_header = auth_headers(client, email="other@example.com")
    upload = client.post(
        "/upload",
        headers=other_header,
        data={"video": (BytesIO(b"fake video"), "other.mp4")},
        content_type="multipart/form-data",
    )
    assert upload.status_code == 201
    video_id = upload.get_json()["video_id"]

    response = client.get(f"/api/videos/{video_id}/metadata", headers=auth_header)

    assert response.status_code == 404


def test_delete_video_is_scoped_to_owner(client, auth_header):
    other_header = auth_headers(client, email="owner@example.com")
    upload = client.post(
        "/upload",
        headers=other_header,
        data={"video": (BytesIO(b"fake video"), "private.mp4")},
        content_type="multipart/form-data",
    )
    assert upload.status_code == 201

    response = client.delete(f"/api/videos/{upload.get_json()['video_id']}", headers=auth_header)

    assert response.status_code == 404
