from io import BytesIO


def test_upload_creates_video_record(client, auth_header):
    response = client.post(
        "/upload",
        headers=auth_header,
        data={"video": (BytesIO(b"fake video"), "camera-one.mp4")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 201
    body = response.get_json()
    assert body["message"] == "Upload success"
    assert body["storage"] == "cluster"
    assert body["video_id"] > 0


def test_upload_rejects_duplicate_filename_for_same_user(client, auth_header):
    first = client.post(
        "/upload",
        headers=auth_header,
        data={"video": (BytesIO(b"first"), "same-name.mp4")},
        content_type="multipart/form-data",
    )
    second = client.post(
        "/upload",
        headers=auth_header,
        data={"video": (BytesIO(b"second"), "same-name.mp4")},
        content_type="multipart/form-data",
    )

    assert first.status_code == 201
    assert second.status_code == 409


def test_dashboard_stats_include_only_current_user_videos(client, auth_header):
    from conftest import auth_headers

    client.post(
        "/upload",
        headers=auth_header,
        data={"video": (BytesIO(b"one"), "mine.mp4")},
        content_type="multipart/form-data",
    )
    other_header = auth_headers(client, email="someone@example.com")
    client.post(
        "/upload",
        headers=other_header,
        data={"video": (BytesIO(b"two"), "theirs.mp4")},
        content_type="multipart/form-data",
    )

    response = client.get("/api/dashboard-stats", headers=auth_header)

    assert response.status_code == 200
    body = response.get_json()
    assert body["total_videos"] == 1
    assert body["recent_activity"][0]["filename"] == "mine.mp4"


def test_process_youtube_rejects_invalid_url(client, auth_header):
    response = client.post("/process_youtube", headers=auth_header, json={"youtube_url": "not-a-youtube-url"})

    assert response.status_code == 400
    assert "Invalid YouTube" in response.get_json()["error"]
