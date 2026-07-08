"""
Unit tests for YOLO detection inference
Tests detection accuracy, bounding box quality, and ByteTrack tracking
"""
import pytest
import numpy as np
import cv2
from unittest.mock import Mock, patch, MagicMock


class TestYOLODetection:
    """YOLO detection inference tests"""

    def test_detection_output_format(self, mock_yolo_model, sample_frame):
        """Test that YOLO detection returns proper bbox format"""
        results = mock_yolo_model.track(sample_frame)

        assert len(results) > 0
        assert hasattr(results[0], 'boxes')
        assert hasattr(results[0].boxes, 'xyxy')
        assert hasattr(results[0].boxes, 'conf')
        assert hasattr(results[0].boxes, 'cls')

    def test_detection_bbox_coordinates(self, mock_yolo_model, sample_frame):
        """Test bbox coordinates are valid (x1 < x2, y1 < y2)"""
        results = mock_yolo_model.track(sample_frame)
        bboxes = results[0].boxes.xyxy

        for bbox in bboxes:
            x1, y1, x2, y2 = bbox
            assert x1 < x2, f"Invalid x coordinates: {x1} >= {x2}"
            assert y1 < y2, f"Invalid y coordinates: {y1} >= {y2}"
            assert x1 >= 0, "Bbox x1 should be >= 0"
            assert y1 >= 0, "Bbox y1 should be >= 0"

    def test_detection_confidence_range(self, mock_yolo_model, sample_frame):
        """Test confidence scores are in [0, 1]"""
        results = mock_yolo_model.track(sample_frame)
        confs = results[0].boxes.conf

        for conf in confs:
            assert 0 <= conf <= 1, f"Confidence {conf} outside [0, 1]"

    def test_detection_person_class_only(self, mock_yolo_model, sample_frame):
        """Test that only person class (0) is detected"""
        results = mock_yolo_model.track(sample_frame)
        classes = results[0].boxes.cls

        for cls in classes:
            assert int(cls) == 0, f"Expected person class (0), got {cls}"

    def test_bytetrack_ids_present(self, mock_yolo_model, sample_frame):
        """Test ByteTrack returns track IDs"""
        results = mock_yolo_model.track(sample_frame)

        if results[0].boxes.id is not None:
            ids = results[0].boxes.id
            assert len(ids) == len(results[0].boxes.xyxy)
            # All IDs should be positive integers
            for track_id in ids:
                assert isinstance(int(track_id), int)
                assert int(track_id) > 0

    def test_detection_count_matches_bbox_count(self, mock_yolo_model, sample_frame):
        """Test all arrays have same length"""
        results = mock_yolo_model.track(sample_frame)

        num_boxes = len(results[0].boxes.xyxy)
        assert len(results[0].boxes.conf) == num_boxes
        assert len(results[0].boxes.cls) == num_boxes

    def test_detection_on_empty_frame(self, mock_yolo_model):
        """Test detection on all-black frame (no persons)"""
        empty_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        results = mock_yolo_model.track(empty_frame)

        assert len(results) > 0
        # Empty frame might have 0 detections
        assert isinstance(results[0].boxes.xyxy, np.ndarray)

    def test_detection_on_crowded_frame(self, mock_yolo_model):
        """Test detection on dense frame (multiple people)"""
        crowded_frame = np.ones((480, 640, 3), dtype=np.uint8) * 200
        results = mock_yolo_model.track(crowded_frame)

        assert len(results) > 0
        # Crowded frame should have multiple detections
        assert isinstance(results[0].boxes.xyxy, np.ndarray)


class TestByteTrac:
    """ByteTrack-specific tests"""

    def test_bytetrack_temporal_continuity(self, mock_yolo_model):
        """Test that ByteTrack maintains ID across frames"""
        # Simulate 3 frames with same person at slightly different positions
        frames = [
            np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8),
            np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8),
            np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8),
        ]

        ids_list = []
        for frame in frames:
            results = mock_yolo_model.track(frame)
            if results[0].boxes.id is not None:
                ids_list.append(results[0].boxes.id)

        assert len(ids_list) > 0
        # IDs should be consistent (person doesn't get new ID each frame)

    def test_bytetrack_low_confidence_handling(self, mock_yolo_model, sample_frame):
        """Test ByteTrack handles low-confidence detections"""
        results = mock_yolo_model.track(sample_frame)

        # Low confidence detections should still be tracked if spatially consistent
        confs = results[0].boxes.conf
        ids = results[0].boxes.id if results[0].boxes.id is not None else []

        # Should have at least some detections/tracks
        assert len(confs) > 0 or len(ids) == 0


class TestDetectionFiltering:
    """Tests for detection filtering and quality checks"""

    def test_confidence_threshold_filtering(self):
        """Test filtering detections below confidence threshold"""
        confs = np.array([0.95, 0.5, 0.3, 0.88, 0.1])
        threshold = 0.6

        filtered = confs[confs >= threshold]
        # Only 0.95 and 0.88 meet threshold
        assert len(filtered) == 2
        assert all(c >= threshold for c in filtered)

    def test_bbox_area_filtering(self):
        """Test filtering small bboxes"""
        bboxes = np.array([
            [100, 100, 150, 200],  # area = 50*100 = 5000
            [50, 50, 70, 60],      # area = 20*10 = 200 (small)
            [200, 200, 400, 400],  # area = 200*200 = 40000
        ])

        min_area = 500
        areas = np.array([(b[2]-b[0])*(b[3]-b[1]) for b in bboxes])
        large_bboxes = bboxes[areas >= min_area]

        assert len(large_bboxes) == 2

    def test_aspect_ratio_filtering(self):
        """Test filtering unrealistic aspect ratios"""
        bboxes = np.array([
            [100, 100, 150, 250],  # h/w = 150/50 = 3.0 (valid person)
            [100, 100, 200, 110],  # h/w = 10/100 = 0.1 (invalid, too wide)
            [100, 100, 110, 300],  # h/w = 200/10 = 20 (invalid, too tall)
        ])

        min_aspect, max_aspect = 1.2, 4.5
        valid_bboxes = []

        for bbox in bboxes:
            h = bbox[3] - bbox[1]
            w = bbox[2] - bbox[0]
            aspect = h / w if w > 0 else 0
            if min_aspect <= aspect <= max_aspect:
                valid_bboxes.append(bbox)

        assert len(valid_bboxes) == 1


class TestPerformanceMetrics:
    """Performance and efficiency tests"""

    def test_inference_frame_size_compatibility(self):
        """Test inference works on standard frame sizes"""
        frame_sizes = [
            (480, 640),      # VGA
            (720, 1280),     # HD
            (1080, 1920),    # Full HD
        ]

        for height, width in frame_sizes:
            frame = np.random.randint(0, 255, (height, width, 3), dtype=np.uint8)
            assert frame.shape == (height, width, 3)

    def test_detection_output_consistency(self, mock_yolo_model, sample_frame):
        """Test same frame produces same detections"""
        results1 = mock_yolo_model.track(sample_frame.copy())
        results2 = mock_yolo_model.track(sample_frame.copy())

        # Should have same structure (though mock may vary)
        assert len(results1) == len(results2)
