"""
Pytest configuration and shared fixtures for processing_server tests
"""
import os
import sys
import pytest
import numpy as np
import cv2
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture
def temp_video_dir():
    """Create a temporary directory for test videos"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def sample_frame():
    """Create a sample 640x480 BGR frame (numpy array)"""
    return np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)


@pytest.fixture
def sample_frame_large():
    """Create a sample 1920x1080 BGR frame"""
    return np.random.randint(0, 255, (1080, 1920, 3), dtype=np.uint8)


@pytest.fixture
def sample_video_file(temp_video_dir):
    """Create a real test video file (10 frames, 30 FPS, 640x480)"""
    video_path = os.path.join(temp_video_dir, "test_video.mp4")

    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(video_path, fourcc, 30.0, (640, 480))

    for i in range(10):
        frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
        out.write(frame)

    out.release()
    yield video_path

    if os.path.exists(video_path):
        os.remove(video_path)


@pytest.fixture
def mock_env_vars():
    """Mock environment variables"""
    with patch.dict(os.environ, {
        'DATABASE_URL': 'postgresql://test:test@localhost/test_db',
        'MINIO_ENDPOINT': '127.0.0.1:19000',
        'MINIO_ACCESS_KEY': 'minioadmin',
        'MINIO_SECRET_KEY': 'minioadmin',
        'MINIO_BUCKET': 'videos',
        'MINIO_SECURE': '0',
        'PROCESSING_SERVER_PORT': '5001',
        'USE_SEGMENTATION_FOR_REID': '0',
        'REID_THRESHOLD': '0.75',
        'REID_CONF_THRESHOLD': '0.25',
    }):
        yield


@pytest.fixture
def mock_yolo_model():
    """Mock YOLO model"""
    mock_model = MagicMock()
    mock_results = MagicMock()

    # Mock detection results
    mock_results.boxes = MagicMock()
    mock_results.boxes.xyxy = np.array([[100, 100, 200, 250], [300, 150, 400, 280]])  # 2 boxes
    mock_results.boxes.conf = np.array([0.95, 0.87])
    mock_results.boxes.cls = np.array([0, 0])
    mock_results.boxes.id = np.array([1, 2])  # Track IDs

    mock_model.track.return_value = [mock_results]
    mock_model.predict.return_value = [mock_results]

    return mock_model


@pytest.fixture
def mock_transreid_model():
    """Mock TransReID embedding model"""
    mock_model = MagicMock()
    # Return 768-d embedding vector
    mock_model.return_value = np.random.randn(1, 768).astype(np.float32)
    return mock_model


@pytest.fixture
def mock_dmcount_model():
    """Mock DM-Count density counting model"""
    mock_model = MagicMock()
    mock_model.predict.return_value = (42.5, np.random.rand(240, 320))  # count, heatmap
    return mock_model


@pytest.fixture
def sample_detection():
    """Sample detection dict"""
    return {
        'bbox': [100, 100, 200, 250],
        'conf': 0.95,
        'track_id': 1,
        'embedding': np.random.randn(768),
        'crop': np.random.randint(0, 255, (150, 100, 3), dtype=np.uint8)
    }


@pytest.fixture
def sample_gallery():
    """Sample global gallery (person embeddings)"""
    return {
        1: {'embedding': np.random.randn(768), 'last_seen': 100},
        2: {'embedding': np.random.randn(768), 'last_seen': 95},
        3: {'embedding': np.random.randn(768), 'last_seen': 50},
    }


@pytest.fixture
def mock_database():
    """Mock database session"""
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = MagicMock(id=1)
    mock_db.execute.return_value = MagicMock()
    return mock_db


@pytest.fixture
def mock_minio_client():
    """Mock MinIO client"""
    mock_client = MagicMock()
    mock_client.put_object.return_value = MagicMock(etag='abc123')
    return mock_client


@pytest.fixture
def mock_socketio():
    """Mock Socket.IO instance"""
    mock_io = MagicMock()
    mock_io.emit.return_value = None
    return mock_io
