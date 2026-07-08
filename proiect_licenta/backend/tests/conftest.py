import importlib
import os
import sys
from pathlib import Path

import pytest


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-with-at-least-32-bytes")
os.environ.setdefault("DIRECT_CLUSTER_MAX_MB", "1000")
os.environ.setdefault("CLUSTER_COMPRESS_MAX_MB", "1000")
os.environ.setdefault("PROCESSING_SERVER_URL", "http://processing.test")

# app.py initializes MinIO at import time; replace it before importing app.
minio_client_module = importlib.import_module("minio_client")
minio_client_module.init_minio = lambda: None

app_module = importlib.import_module("app")
app = app_module.app
db = app_module.db
from models import User, Video


class DummyStat:
    size = 1024


class DummyMinio:
    def stat_object(self, bucket, key):
        return DummyStat()

    def remove_object(self, bucket, key):
        return None

    def get_object(self, bucket, key):
        raise FileNotFoundError(key)

    def put_object(self, *args, **kwargs):
        return None


@pytest.fixture(autouse=True)
def test_app_config(monkeypatch):
    app.config.update(TESTING=True)
    monkeypatch.setattr(app_module, "minio_client", DummyMinio())
    monkeypatch.setattr(app_module, "upload_file_to_minio", lambda *args, **kwargs: True)
    monkeypatch.setattr(app_module, "upload_file_to_cluster", lambda *args, **kwargs: {"ok": True})


@pytest.fixture(autouse=True)
def clean_database():
    with app.app_context():
        db.drop_all()
        db.create_all()
    yield
    with app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client():
    return app.test_client()


def register_user(client, email="ana@example.com", password="StrongPass123!", **extra):
    payload = {"email": email, "password": password, "firstName": "Ana", "lastName": "Test"}
    payload.update(extra)
    return client.post("/auth/register", json=payload)


def auth_headers(client, email="ana@example.com", password="StrongPass123!"):
    response = register_user(client, email=email, password=password)
    assert response.status_code == 201, response.get_json()
    token = response.get_json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth_header(client):
    return auth_headers(client)
