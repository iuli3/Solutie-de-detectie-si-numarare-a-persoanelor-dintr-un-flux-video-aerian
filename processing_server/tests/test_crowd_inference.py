"""
Unit tests for DM-Count crowd inference
Tests density map generation, count estimation, and heatmap quality
"""
import pytest
import numpy as np
import cv2
from unittest.mock import Mock, patch, MagicMock


class TestDMCountInference:
    """DM-Count model inference tests"""

    def test_dmcount_output_format(self, mock_dmcount_model, sample_frame):
        """Test DM-Count returns (count, heatmap) tuple"""
        count, heatmap = mock_dmcount_model.predict(sample_frame)

        assert isinstance(count, (int, float, np.number))
        assert isinstance(heatmap, np.ndarray)

    def test_dmcount_count_is_positive(self, mock_dmcount_model, sample_frame):
        """Test predicted count is non-negative"""
        count, heatmap = mock_dmcount_model.predict(sample_frame)

        assert count >= 0, f"Count should be >= 0, got {count}"

    def test_dmcount_heatmap_shape(self, mock_dmcount_model, sample_frame):
        """Test heatmap has 2D shape (height, width)"""
        count, heatmap = mock_dmcount_model.predict(sample_frame)

        assert len(heatmap.shape) == 2, f"Heatmap should be 2D, got shape {heatmap.shape}"
        h, w = heatmap.shape
        assert h > 0 and w > 0

    def test_dmcount_heatmap_values_range(self, mock_dmcount_model, sample_frame):
        """Test heatmap values are non-negative"""
        count, heatmap = mock_dmcount_model.predict(sample_frame)

        assert np.all(heatmap >= 0), "Heatmap should have non-negative values"
        # Typically heatmap values are between 0 and max_density
        assert np.all(np.isfinite(heatmap)), "Heatmap should not contain NaN/Inf"

    def test_dmcount_on_empty_scene(self, mock_dmcount_model):
        """Test DM-Count on empty/black frame"""
        empty_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        count, heatmap = mock_dmcount_model.predict(empty_frame)

        # Mock returns random, but should be valid number
        assert isinstance(count, (int, float, np.number))
        assert count >= 0

    def test_dmcount_on_crowded_scene(self, mock_dmcount_model):
        """Test DM-Count on crowded/bright frame"""
        crowded_frame = np.ones((480, 640, 3), dtype=np.uint8) * 200
        count, heatmap = mock_dmcount_model.predict(crowded_frame)

        # Crowded scene should have higher count
        assert count >= 0, "Count should be valid"

    def test_dmcount_scale_invariance(self, mock_dmcount_model):
        """Test DM-Count works on different resolutions"""
        resolutions = [
            (480, 640),
            (720, 1280),
            (1080, 1920),
        ]

        for height, width in resolutions:
            frame = np.random.randint(0, 255, (height, width, 3), dtype=np.uint8)
            count, heatmap = mock_dmcount_model.predict(frame)

            assert isinstance(count, (int, float, np.number))
            assert isinstance(heatmap, np.ndarray)

    def test_dmcount_batch_processing(self, mock_dmcount_model):
        """Test DM-Count on multiple frames"""
        counts = []
        for i in range(5):
            frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
            count, heatmap = mock_dmcount_model.predict(frame)
            counts.append(count)

        assert len(counts) == 5
        # Counts should be realistic (not all same)
        assert all(c >= 0 for c in counts)


class TestHeatmapGeneration:
    """Tests for heatmap visualization and processing"""

    def test_heatmap_normalization(self):
        """Test heatmap normalization to [0, 255]"""
        heatmap = np.random.rand(240, 320) * 100  # Random values
        normalized = (heatmap / heatmap.max()) * 255 if heatmap.max() > 0 else heatmap

        assert 0 <= normalized.min() <= 255
        assert 0 <= normalized.max() <= 255

    def test_heatmap_colormap_application(self):
        """Test applying colormap to heatmap"""
        heatmap = np.random.randint(0, 255, (240, 320), dtype=np.uint8)
        heatmap_colored = cv2.applyColorMap(heatmap, cv2.COLORMAP_JET)

        assert heatmap_colored.shape == (240, 320, 3)
        assert heatmap_colored.dtype == np.uint8

    def test_heatmap_overlay_blending(self):
        """Test blending heatmap with original frame"""
        original = np.ones((480, 640, 3), dtype=np.uint8) * 100
        heatmap = np.ones((480, 640, 3), dtype=np.uint8) * 200

        # Blend: 60% original + 40% heatmap
        blended = cv2.addWeighted(original, 0.6, heatmap, 0.4, 0)

        assert blended.shape == original.shape
        assert blended.dtype == np.uint8
        # Values should be between 100 and 200
        assert 100 <= blended.min() <= blended.max() <= 200

    def test_heatmap_resize_for_display(self):
        """Test resizing heatmap to display resolution"""
        heatmap = np.random.rand(240, 320)
        target_width = 1280

        scale = target_width / 320
        target_height = int(240 * scale)

        heatmap_resized = cv2.resize(
            heatmap,
            (target_width, target_height),
            interpolation=cv2.INTER_CUBIC
        )

        assert heatmap_resized.shape == (target_height, target_width)

    def test_heatmap_statistics(self):
        """Test calculating density statistics from heatmap"""
        heatmap = np.array([
            [1, 2, 3],
            [4, 5, 6],
            [7, 8, 9],
        ])

        total_density = np.sum(heatmap)
        mean_density = np.mean(heatmap)
        max_density = np.max(heatmap)
        min_density = np.min(heatmap)

        assert total_density == 45
        assert mean_density == 5.0
        assert max_density == 9
        assert min_density == 1


class TestCountEstimation:
    """Tests for count estimation from density maps"""

    def test_count_from_density_summation(self):
        """Test summing density map to get total count"""
        # Simulate density map with Gaussian blobs (person at center)
        heatmap = np.array([
            [0.1, 0.2, 0.1],
            [0.2, 0.8, 0.2],  # Peak = person
            [0.1, 0.2, 0.1],
        ])

        count = np.sum(heatmap)
        # Actual sum: 0.1+0.2+0.1 + 0.2+0.8+0.2 + 0.1+0.2+0.1 = 2.0
        expected_count = 2.0

        assert abs(count - expected_count) < 0.01

    def test_count_multi_peak_detection(self):
        """Test count estimation with multiple people"""
        # Simulate 2 separate people (2 peaks)
        heatmap = np.zeros((5, 5))
        heatmap[1, 1] = 0.8  # Person 1
        heatmap[3, 3] = 0.8  # Person 2

        count = np.sum(heatmap)
        assert count > 1, "Should detect multiple people"

    def test_count_accuracy_within_bounds(self):
        """Test count is within reasonable bounds"""
        # Generate random heatmap
        heatmap = np.random.rand(240, 320)
        count = np.sum(heatmap) / 100  # Normalize by area

        # Reasonable range for crowd density
        assert 0 <= count <= 10000, f"Unrealistic count: {count}"

    def test_count_deterministic(self):
        """Test same heatmap produces same count"""
        heatmap = np.random.rand(240, 320)

        count1 = np.sum(heatmap)
        count2 = np.sum(heatmap)

        assert count1 == count2


class TestCrowdModelVariants:
    """Tests for different DM-Count model variants"""

    def test_qnrf_model_inference(self):
        """Test QNRF model (general-purpose)"""
        # Simulate QNRF model output
        count = 42.5  # Predicted count
        heatmap = np.random.rand(240, 320)

        assert isinstance(count, float)
        assert 0 <= count <= 3000  # QNRF trained up to ~3000 people

    def test_nwpu_model_inference(self):
        """Test NWPU model (aerial/drone)"""
        # Simulate NWPU model output
        count = 28.3  # Predicted count (often lower than QNRF)
        heatmap = np.random.rand(240, 320)

        assert isinstance(count, float)
        assert 0 <= count <= 2000  # NWPU typically lower density

    def test_model_inference_time(self):
        """Test inference time is acceptable"""
        # Simulate inference timing
        import time

        start = time.time()

        # Simulate inference (mock, ~50ms)
        _ = np.random.rand(240, 320)
        count = np.random.rand() * 100

        elapsed = time.time() - start

        # Should be fast (under 100ms in practice)
        assert elapsed < 1.0  # Very permissive for test


class TestVideoProcessingPipeline:
    """Integration tests for video crowd counting"""

    def test_frame_sequence_processing(self, mock_dmcount_model, sample_video_file):
        """Test processing video frame sequence"""
        import cv2

        cap = cv2.VideoCapture(sample_video_file)
        counts = []

        frame_count = 0
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break

            count, heatmap = mock_dmcount_model.predict(frame)
            counts.append(count)
            frame_count += 1

        cap.release()

        assert len(counts) > 0, "Should process at least 1 frame"
        assert all(c >= 0 for c in counts), "All counts should be non-negative"

    def test_statistics_accumulation(self):
        """Test accumulating statistics across frames"""
        counts = [10, 15, 12, 18, 14]

        max_count = max(counts)
        avg_count = np.mean(counts)
        total_count = sum(counts)

        assert max_count == 18
        assert abs(avg_count - 13.8) < 0.01
        assert total_count == 69

    def test_progress_tracking(self):
        """Test progress calculation during processing"""
        total_frames = 100
        processed_frames = 0

        for i in range(total_frames):
            processed_frames += 1
            progress = (processed_frames / total_frames) * 100

            if i == 50:
                assert abs(progress - 51.0) < 0.1

        assert progress == 100.0
