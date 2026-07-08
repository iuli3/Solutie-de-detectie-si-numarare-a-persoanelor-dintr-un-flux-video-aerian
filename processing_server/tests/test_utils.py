"""
Utility functions for testing
Includes mock helpers, test data generators, and assertion helpers
"""
import numpy as np
import cv2
from typing import Tuple, List, Dict


class FrameGenerator:
    """Generate synthetic test frames"""

    @staticmethod
    def create_blank_frame(height: int = 480, width: int = 640) -> np.ndarray:
        """Create blank/black frame"""
        return np.zeros((height, width, 3), dtype=np.uint8)

    @staticmethod
    def create_random_frame(height: int = 480, width: int = 640) -> np.ndarray:
        """Create random noise frame"""
        return np.random.randint(0, 255, (height, width, 3), dtype=np.uint8)

    @staticmethod
    def create_gradient_frame(height: int = 480, width: int = 640) -> np.ndarray:
        """Create gradient frame (useful for testing scaling)"""
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        for i in range(height):
            intensity = int((i / height) * 255)
            frame[i, :] = [intensity, intensity, intensity]
        return frame

    @staticmethod
    def create_frame_with_circle(
        height: int = 480,
        width: int = 640,
        center: Tuple[int, int] = (320, 240),
        radius: int = 50,
        color: Tuple[int, int, int] = (0, 255, 0)
    ) -> np.ndarray:
        """Create frame with colored circle (simulates person)"""
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        cv2.circle(frame, center, radius, color, -1)
        return frame

    @staticmethod
    def create_frame_with_rectangles(
        height: int = 480,
        width: int = 640,
        num_rects: int = 3
    ) -> np.ndarray:
        """Create frame with multiple rectangles (simulates people)"""
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        for i in range(num_rects):
            x1 = np.random.randint(0, width - 100)
            y1 = np.random.randint(0, height - 150)
            x2 = x1 + np.random.randint(50, 150)
            y2 = y1 + np.random.randint(100, 200)
            color = (np.random.randint(0, 255), np.random.randint(0, 255), np.random.randint(0, 255))
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, -1)
        return frame


class DetectionGenerator:
    """Generate synthetic detection results"""

    @staticmethod
    def create_detection(
        x1: float, y1: float, x2: float, y2: float,
        conf: float = 0.95,
        track_id: int = 1,
        class_id: int = 0
    ) -> Dict:
        """Create single detection dict"""
        return {
            'x1': x1, 'y1': y1, 'x2': x2, 'y2': y2,
            'conf': conf,
            'track_id': track_id,
            'class_id': class_id,
            'bbox': [x1, y1, x2, y2]
        }

    @staticmethod
    def create_batch_detections(num_detections: int = 5) -> List[Dict]:
        """Create batch of random detections"""
        detections = []
        for i in range(num_detections):
            x1 = np.random.randint(0, 500)
            y1 = np.random.randint(0, 350)
            x2 = x1 + np.random.randint(50, 150)
            y2 = y1 + np.random.randint(100, 200)
            conf = np.random.uniform(0.5, 0.99)

            detections.append(DetectionGenerator.create_detection(
                x1, y1, x2, y2, conf=conf, track_id=i+1
            ))

        return detections


class EmbeddingGenerator:
    """Generate synthetic embeddings"""

    @staticmethod
    def create_embedding(dim: int = 768) -> np.ndarray:
        """Create random normalized embedding"""
        emb = np.random.randn(dim).astype(np.float32)
        return emb / np.linalg.norm(emb)

    @staticmethod
    def create_similar_embedding(reference: np.ndarray, noise_level: float = 0.1) -> np.ndarray:
        """Create embedding similar to reference"""
        noise = np.random.randn(len(reference)) * noise_level
        emb = reference + noise
        return emb / np.linalg.norm(emb)

    @staticmethod
    def create_batch_embeddings(num_embeddings: int = 10, dim: int = 768) -> np.ndarray:
        """Create batch of embeddings"""
        embeddings = []
        for _ in range(num_embeddings):
            emb = EmbeddingGenerator.create_embedding(dim)
            embeddings.append(emb)
        return np.array(embeddings)


class MetricsComputer:
    """Compute metrics for testing"""

    @staticmethod
    def cosine_distance(v1: np.ndarray, v2: np.ndarray) -> float:
        """Compute cosine distance between two vectors"""
        similarity = np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2))
        return 1 - similarity

    @staticmethod
    def bbox_iou(bbox1: List, bbox2: List) -> float:
        """Compute Intersection over Union for two bboxes"""
        x1_min, y1_min, x1_max, y1_max = bbox1
        x2_min, y2_min, x2_max, y2_max = bbox2

        # Intersection
        xi_min = max(x1_min, x2_min)
        yi_min = max(y1_min, y2_min)
        xi_max = min(x1_max, x2_max)
        yi_max = min(y1_max, y2_max)

        if xi_max < xi_min or yi_max < yi_min:
            return 0.0

        intersection = (xi_max - xi_min) * (yi_max - yi_min)

        # Union
        area1 = (x1_max - x1_min) * (y1_max - y1_min)
        area2 = (x2_max - x2_min) * (y2_max - y2_min)
        union = area1 + area2 - intersection

        return intersection / union if union > 0 else 0.0

    @staticmethod
    def bbox_area(bbox: List) -> float:
        """Compute bounding box area"""
        x1, y1, x2, y2 = bbox
        return (x2 - x1) * (y2 - y1)

    @staticmethod
    def crop_aspect_ratio(bbox: List) -> float:
        """Compute aspect ratio of bbox"""
        x1, y1, x2, y2 = bbox
        h = y2 - y1
        w = x2 - x1
        return h / w if w > 0 else 0


class AssertionHelpers:
    """Custom assertion helpers"""

    @staticmethod
    def assert_valid_bbox(bbox: List, frame_h: int = 480, frame_w: int = 640):
        """Assert bbox is valid"""
        x1, y1, x2, y2 = bbox
        assert x1 < x2, f"Invalid x: {x1} >= {x2}"
        assert y1 < y2, f"Invalid y: {y1} >= {y2}"
        assert x1 >= 0 and y1 >= 0, "Negative coordinates"
        assert x2 <= frame_w and y2 <= frame_h, "Coordinates outside frame"

    @staticmethod
    def assert_valid_embedding(emb: np.ndarray, dim: int = 768):
        """Assert embedding is valid"""
        assert len(emb) == dim, f"Expected {dim}-d, got {len(emb)}"
        assert np.all(np.isfinite(emb)), "Embedding contains NaN/Inf"
        norm = np.linalg.norm(emb)
        assert abs(norm - 1.0) < 0.01, f"Embedding not normalized, norm={norm}"

    @staticmethod
    def assert_valid_frame(frame: np.ndarray):
        """Assert frame is valid"""
        assert len(frame.shape) == 3, "Frame should be 3D array"
        assert frame.shape[2] == 3, "Frame should have 3 channels"
        assert frame.dtype == np.uint8, "Frame should be uint8"
        assert np.all(frame >= 0) and np.all(frame <= 255), "Frame values should be [0, 255]"


class PerformanceProfiler:
    """Profile performance metrics"""

    @staticmethod
    def measure_inference_time(model_func, input_data, num_runs: int = 10) -> Tuple[float, float]:
        """Measure model inference time"""
        import time

        times = []
        for _ in range(num_runs):
            start = time.time()
            _ = model_func(input_data)
            elapsed = time.time() - start
            times.append(elapsed * 1000)  # Convert to ms

        return np.mean(times), np.std(times)

    @staticmethod
    def measure_throughput(model_func, input_data, duration: float = 1.0) -> float:
        """Measure throughput (frames per second)"""
        import time

        start = time.time()
        count = 0

        while time.time() - start < duration:
            _ = model_func(input_data)
            count += 1

        return count / duration
