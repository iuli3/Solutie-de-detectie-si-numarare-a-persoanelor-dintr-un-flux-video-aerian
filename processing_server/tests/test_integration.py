"""
Integration tests for processing_server
End-to-end pipeline tests combining multiple components
"""
import pytest
import numpy as np
import cv2
from unittest.mock import Mock, patch, MagicMock


class TestDetectionToCropPipeline:
    """Integration: Detection → Crop Extraction → Quality Filtering"""

    def test_bbox_to_crop_extraction(self, sample_frame):
        """Test extracting person crop from detection bbox"""
        bbox = [100, 100, 200, 250]
        x1, y1, x2, y2 = bbox

        crop = sample_frame[y1:y2, x1:x2]

        assert crop.shape == (y2 - y1, x2 - x1, 3)
        assert crop.dtype == np.uint8

    def test_crop_quality_filtering_pipeline(self):
        """Test complete crop filtering pipeline"""
        bboxes = [
            (100, 100, 200, 300),  # h=200, w=100, area=20000 (valid)
            (50, 50, 70, 60),      # h=10, w=20, area=200 (too small)
            (300, 200, 500, 600),  # h=400, w=200, area=80000 (valid)
        ]

        min_h, min_w, min_area = 50, 18, 1200
        min_aspect, max_aspect = 1.2, 4.5

        valid_crops = []
        for bbox in bboxes:
            x1, y1, x2, y2 = bbox
            h = y2 - y1
            w = x2 - x1
            area = h * w
            aspect = h / w if w > 0 else 0

            if (h >= min_h and
                w >= min_w and
                area >= min_area and
                min_aspect <= aspect <= max_aspect):
                valid_crops.append(bbox)

        assert len(valid_crops) == 2

    def test_crop_preprocessing_for_reid(self):
        """Test preprocessing crop for TransReID"""
        crop = np.random.randint(0, 255, (150, 100, 3), dtype=np.uint8)

        # Resize to standard size (e.g., 256x128 for ReID models)
        reid_size = (128, 256)
        resized = cv2.resize(crop, reid_size, interpolation=cv2.INTER_CUBIC)

        assert resized.shape == (256, 128, 3)

        # Normalize (0-1)
        normalized = resized.astype(np.float32) / 255.0
        assert normalized.min() >= 0 and normalized.max() <= 1


class TestDetectionTrackingPipeline:
    """Integration: YOLO Detection → ByteTrack → Track ID Management"""

    def test_single_frame_tracking(self, mock_yolo_model, sample_frame):
        """Test single frame detection and tracking"""
        results = mock_yolo_model.track(sample_frame)

        assert len(results) > 0
        assert hasattr(results[0].boxes, 'id')

    def test_track_consistency_across_frames(self, mock_yolo_model):
        """Test track IDs remain consistent across frames"""
        # Simulate 5 frames
        frames = [
            np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
            for _ in range(5)
        ]

        track_ids_history = []
        for frame in frames:
            results = mock_yolo_model.track(frame)
            if results[0].boxes.id is not None:
                ids = [int(id) for id in results[0].boxes.id]
                track_ids_history.append(ids)

        # Each frame should have detections with IDs
        assert len(track_ids_history) > 0

    def test_detection_to_track_conversion(self):
        """Test converting raw detections to track objects"""
        # Simulate detection
        detection = {
            'bbox': [100, 100, 200, 250],
            'conf': 0.95,
            'class': 0,
        }

        # Create track object
        track = {
            'id': 1,
            'bbox': detection['bbox'],
            'conf': detection['conf'],
            'age': 1,  # Frames alive
            'hits': 1,  # Consecutive hits
            'embeddings': []
        }

        assert track['id'] == 1
        assert track['age'] == 1


class TestEmbeddingExtractionPipeline:
    """Integration: Crop → Preprocessing → TransReID → Embedding"""

    def test_crop_to_embedding_pipeline(self, mock_transreid_model):
        """Test complete crop-to-embedding pipeline"""
        # Step 1: Extract crop
        frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
        crop = frame[100:250, 100:200]  # 150×100

        # Step 2: Resize for model
        resized = cv2.resize(crop, (128, 256), interpolation=cv2.INTER_CUBIC)

        # Step 3: Normalize
        normalized = resized.astype(np.float32) / 255.0

        # Step 4: Get embedding
        embedding = mock_transreid_model(normalized)

        assert isinstance(embedding, np.ndarray)
        assert embedding.shape[-1] == 768  # Final dimension is 768

    def test_embedding_quality_checks(self):
        """Test checking embedding quality before gallery match"""
        embedding = np.random.randn(768).astype(np.float32)
        normalized = embedding / np.linalg.norm(embedding)

        # Quality checks
        assert np.all(np.isfinite(normalized)), "No NaN/Inf"
        norm = np.linalg.norm(normalized)
        assert abs(norm - 1.0) < 0.001, "Is normalized"

    def test_embedding_averaging_for_tracks(self):
        """Test averaging multiple embeddings per track"""
        embeddings = [
            np.random.randn(768).astype(np.float32) / 768.0
            for _ in range(5)
        ]

        # Average
        avg_emb = np.mean(embeddings, axis=0)
        avg_emb = avg_emb / np.linalg.norm(avg_emb)

        assert avg_emb.shape == (768,)
        assert np.all(np.isfinite(avg_emb))


class TestCrossCamera:
    """Integration: Multi-camera gallery matching"""

    def test_camera_1_to_camera_2_reid(self):
        """Test Re-ID matching across Camera 1 and Camera 2"""
        # Camera 1 detects person
        camera1_emb = np.random.randn(768)
        camera1_emb = camera1_emb / np.linalg.norm(camera1_emb)

        # Camera 2 detects same person with VERY small noise
        camera2_emb = camera1_emb + np.random.randn(768) * 0.01  # Much smaller noise
        camera2_emb = camera2_emb / np.linalg.norm(camera2_emb)

        # Check distance
        distance = 1 - np.dot(camera1_emb, camera2_emb)

        # Should be very low (same person, minimal noise)
        assert distance < 0.15, f"Same person should have distance < 0.15, got {distance}"

    def test_global_gallery_management(self):
        """Test maintaining global gallery across cameras"""
        gallery = {}
        camera_count = 0

        # Camera 1: Detect 2 people
        for i in range(2):
            camera_count += 1
            gallery[camera_count] = {
                'emb': np.random.randn(768),
                'last_seen_camera': 1,
                'count': 1
            }

        # Camera 2: Detect 1 new person + 1 existing
        existing_person_id = 1
        gallery[existing_person_id]['count'] += 1
        gallery[existing_person_id]['last_seen_camera'] = 2

        new_person_id = max(gallery.keys()) + 1
        gallery[new_person_id] = {
            'emb': np.random.randn(768),
            'last_seen_camera': 2,
            'count': 1
        }

        assert len(gallery) == 3  # 2 from camera 1, 1 new from camera 2
        assert gallery[existing_person_id]['count'] == 2

    def test_camera_trio_coordination(self):
        """Test coordinating 3 cameras with shared gallery"""
        gallery = {
            1: {'emb': np.random.randn(768), 'cameras': set()},
            2: {'emb': np.random.randn(768), 'cameras': set()},
        }

        # Camera 1 sees person 1
        gallery[1]['cameras'].add('camera_1')

        # Camera 2 sees person 1 and 2
        gallery[1]['cameras'].add('camera_2')
        gallery[2]['cameras'].add('camera_2')

        # Camera 3 sees person 2
        gallery[2]['cameras'].add('camera_3')

        # Person 1 seen on cameras 1, 2
        assert len(gallery[1]['cameras']) == 2
        # Person 2 seen on cameras 2, 3
        assert len(gallery[2]['cameras']) == 2


class TestCrowdCountingPipeline:
    """Integration: Frame → DM-Count → Heatmap → Statistics"""

    def test_frame_to_count_pipeline(self, mock_dmcount_model, sample_frame):
        """Test complete frame-to-count pipeline"""
        # Step 1: Get frame
        assert sample_frame.shape == (480, 640, 3)

        # Step 2: Inference
        count, heatmap = mock_dmcount_model.predict(sample_frame)

        # Step 3: Validate
        assert isinstance(count, (int, float, np.number))
        assert count >= 0
        assert isinstance(heatmap, np.ndarray)
        assert len(heatmap.shape) == 2

    def test_heatmap_to_visualization_pipeline(self):
        """Test heatmap processing to visualization"""
        # DM-Count output (raw density)
        heatmap = np.random.rand(240, 320) * 100

        # Step 1: Normalize
        normalized = (heatmap / heatmap.max() * 255).astype(np.uint8)

        # Step 2: Apply colormap
        colored = cv2.applyColorMap(normalized, cv2.COLORMAP_JET)

        assert colored.shape == (240, 320, 3)
        assert colored.dtype == np.uint8

        # Step 3: Blend with original
        original = np.ones((240, 320, 3), dtype=np.uint8) * 128
        blended = cv2.addWeighted(original, 0.6, colored, 0.4, 0)

        assert blended.shape == (240, 320, 3)

    def test_statistics_accumulation_pipeline(self):
        """Test accumulating statistics across video"""
        counts = []
        max_count = 0
        total_count = 0
        frame_count = 0

        # Process 100 frames
        for _ in range(100):
            count = np.random.uniform(5, 50)  # Simulated count
            counts.append(count)
            frame_count += 1

            if count > max_count:
                max_count = count

            total_count += count

        # Calculate statistics
        avg_count = total_count / frame_count

        assert frame_count == 100
        assert max_count > 0
        assert avg_count > 0
        assert avg_count < max_count


class TestVideoProcessingPipeline:
    """Integration: Video File → Process → Save → Database"""

    def test_video_opening_and_properties(self, sample_video_file):
        """Test reading video file properties"""
        cap = cv2.VideoCapture(sample_video_file)

        assert cap.isOpened()

        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        assert width == 640
        assert height == 480
        assert fps == 30.0
        assert frame_count == 10

        cap.release()

    def test_frame_reading_loop(self, sample_video_file):
        """Test reading all frames from video"""
        cap = cv2.VideoCapture(sample_video_file)

        frames_read = 0
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break

            assert frame.shape == (480, 640, 3)
            frames_read += 1

        cap.release()

        assert frames_read == 10

    def test_output_video_writing(self, sample_video_file, temp_video_dir):
        """Test writing processed frames to output video"""
        import os

        input_path = sample_video_file
        output_path = os.path.join(temp_video_dir, "output.mp4")

        # Read input
        cap = cv2.VideoCapture(input_path)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS)

        # Write output
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

        frame_count = 0
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break

            out.write(frame)
            frame_count += 1

        cap.release()
        out.release()

        assert os.path.exists(output_path)
        assert os.path.getsize(output_path) > 0


class TestMemoryManagement:
    """Integration: Check memory handling during processing"""

    def test_gallery_memory_bounds(self):
        """Test gallery doesn't grow unbounded"""
        max_gallery_size = 1000

        # Simulate adding people over time
        gallery = {}
        for person_id in range(2000):
            gallery[person_id] = {'emb': np.random.randn(768)}

            # Prune if too large
            if len(gallery) > max_gallery_size:
                # Remove oldest
                to_remove = min(gallery.keys())
                del gallery[to_remove]

        assert len(gallery) <= max_gallery_size

    def test_embeddings_per_track_cap(self):
        """Test embeddings don't accumulate unbounded per track"""
        max_embeddings = 6
        track_embeddings = []

        # Simulate 100 detections
        for _ in range(100):
            new_emb = np.random.randn(768)
            track_embeddings.append(new_emb)

            # Keep only latest N
            if len(track_embeddings) > max_embeddings:
                track_embeddings = track_embeddings[-max_embeddings:]

        assert len(track_embeddings) == max_embeddings
