# Processing Server - Backend

Real-time GPU-accelerated computer vision server. Multi-camera person detection, re-identification, tracking, and crowd density estimation with Socket.IO streaming.

## Features

- YOLO11 Detection - Real-time person detection with optional segmentation
- ByteTrack - Temporal tracking consistency across frames
- TransReID - Cross-camera person re-identification (768-d embeddings)
- DM-Count - Deep learning crowd density estimation
- TensorRT - GPU-optimized inference engines
- Socket.IO - Real-time frame streaming to frontend
- PostgreSQL - Tracking logs & analytics storage
- MinIO S3 - Video file management

## Tech Stack

- Framework: Flask + Socket.IO
- GPU: PyTorch, TensorRT, CUDA 12+
- Database: PostgreSQL
- Storage: MinIO (S3-compatible)
- Python: 3.10+

## Quick Start

### 1. Prerequisites

- Python 3.10+
- NVIDIA GPU + CUDA 12.x
- PostgreSQL 13+
- MinIO server (or S3-compatible)

### 2. Clone & Setup

```bash
cd processing_server/

# Create virtual environment (venv)
python -m venv venv
source venv/bin/activate          # Linux/Mac
# OR
venv\Scripts\activate.bat         # Windows

# OR with conda
conda create -n processing_server python=3.10
conda activate processing_server
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

This installs 123+ packages:
- Core: Flask, Socket.IO, SQLAlchemy
- ML/Vision: PyTorch (2.1.2), YOLO, OpenCV, TransReID, DM-Count
- Storage: MinIO, PostgreSQL (psycopg2)
- Dev: pytest, rich

Installation time: 15-20 minutes
Installation size: ~15-20GB (PyTorch ~2.5GB)
Requires: Free disk space, good internet

Note: nvidia-tensorrt installs automatically via ultralytics if needed.

### 4. Configure `.env`

```bash
cp .env.example .env
```

Edit `.env` with your environment:

```ini
# GPU
CUDA_VISIBLE_DEVICES=0,1,2

# Server
PROCESSING_SERVER_PORT=5001

# Database
DATABASE_URL=postgresql://admin:password@your-db-host:5432/licenta_db

# MinIO/S3
MINIO_ENDPOINT=your-minio-host:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET=licenta-videos

# Models (relative to this directory)
MODEL_PATH=models/yolo11m_smallperson_aerial_1280.engine
```

See `.env.example` for all available options.

### 5. Initialize Database

```bash
python run_migrations.py
```

Creates tables: `video`, `person_log`, `global_person`, `multicam_log`

### 6. Run Server

```bash
cd core/
python processing_server.py
```

Expected output (takes 30-60 sec at startup):
```
[INIT] CUDA_VISIBLE_DEVICES=0,1,2
[INIT] torch.cuda.device_count()=3
[INIT] AVAILABLE_GPUS=[0, 1, 2]
[INIT] Strategie: Lazy loading YOLO models (on-demand per GPU)
[INIT] Model YOLO incarcat pe cuda:2 ✓
[INIT] Ambele modele DM-Count incarcate si cached. ✓
[INIT] tracking_inference importat cu succes. ✓
[INIT] Modele tracking preloadede pe GPU: [0] ✓
Processing Server - Port: 5001 - GPU YOLO: [2] ✓
 * Running on http://127.0.0.1:5001
```

Server is ready at `http://127.0.0.1:5001`

All models loaded, all GPUs initialized, ready for frames!

## Project Structure

```
processing_server/
├── core/                          -- Server core
│   ├── processing_server.py       (1,600+ lines)
│   ├── gpu_manager.py
│   └── video_utils.py
│
├── inference/                     -- ML inference modules
│   ├── yolo_inference.py          (YOLO detection + validation)
│   ├── tracking_inference.py      (Re-ID + ByteTrack)
│   ├── crowd_inference.py         (Crowd density)
│   └── dmcount_inference.py       (DM-Count model)
│
├── utils/                         -- Utilities
│   ├── minio_client.py            (S3/MinIO upload/download)
│   ├── reid_utils.py              (Re-ID camera prep)
│   └── migrate_db.py              (DB initialization)
│
├── models/                        -- 1.3GB inference models
│   ├── best.pt                    (YOLO detection main)
│   ├── yolo11n.pt
│   ├── yolo11n-seg.pt             (YOLO with segmentation)
│   ├── vit_transreid_msmt.pth     (TransReID 768-d embeddings)
│   ├── vgg19-dcbb9e9d.pth         (Crowd counting backbone)
│   ├── model_qnrf.pth             (DM-Count QNRF)
│   ├── model_nwpu.pth             (DM-Count NWPU)
│   ├── yolo11m_smallperson_aerial_1280.engine  (TensorRT)
│   └── yolo26best.engine
│
├── DM-count/                      -- Crowd counting module
│   ├── models.py
│   └── ...
│
├── datasets/                      -- Training datasets (YOLO data.yaml)
├── runs/                          -- Training results
├── tests/                         -- Unit tests
│
├── .env                           -- Local config (git-ignored)
├── .env.example                   -- Config template
├── .gitignore
├── requirements.txt               -- Python dependencies
├── SETUP.md                       -- Detailed setup guide
├── README.md                      -- This file
└── ...
```

## Key Modules

### core/processing_server.py
Main Flask+Socket.IO server. Handles:
- HTTP API endpoints
- Video upload & streaming
- GPU queue management
- Mode selection (detection / crowd / tracking)
- Re-ID workflow coordination

Socket.IO Events:
```
Input:  upload_video, start_processing, stop_processing, start_reid, stop_reid
Output: status_update, frame_data, reid_complete, processing_stopped
```

### inference/yolo_inference.py
YOLO11 detection & validation:
- Video file validation (codec, resolution)
- Frame-by-frame inference
- Bounding box annotation
- Segmentation mask overlay (optional)

### inference/tracking_inference.py
Multi-camera Re-ID pipeline:
- ByteTrack temporal tracking
- TransReID embedding extraction (768-d)
- Cosine distance matching (0-2 range)
- Cross-camera person linking
- Database persistence

### inference/crowd_inference.py
DM-Count crowd density estimation:
- Density map generation
- Person count estimation
- Frame-by-frame aggregation

### utils/minio_client.py
S3/MinIO integration:
- Video upload/download
- Bandwidth-optimized streaming
- Automatic fallback to local cache

## Configuration

All configuration via `.env` (see `.env.example`):

| Variable | Default | Purpose |
|----------|---------|---------|
| CUDA_VISIBLE_DEVICES | 0,1,2 | GPU selection |
| PROCESSING_SERVER_PORT | 5001 | Server listen port |
| DATABASE_URL | postgresql://... | PostgreSQL connection |
| MINIO_ENDPOINT | 127.0.0.1:19000 | MinIO/S3 endpoint |
| MODEL_PATH | models/yolo11m_...engine | Main detection model |
| REID_DETECTOR_MODEL | yolo11n.pt | Re-ID detector |
| USE_SEGMENTATION_FOR_REID | 1 | Enable segmentation masking |
| KEEP_REID_CACHE | 1 | Cache Re-ID gallery between runs |

## Development

### Run Tests

```bash
pytest tests/ -v
```

### Create Training Scripts

Training scripts in `../train1280/` use relative paths and are git-portable:

```bash
cd processing_server/
python ../train1280/train_yolo26m_balanced.py
```

### Logging

Structured console output via `rich`:
- [INIT] - Initialization logs
- [GPU] - GPU allocation
- [YOLO] - Detection
- [REID] - Re-ID workflow
- [CROWD] - Crowd counting
- [DB] - Database operations
- [SOCKET] - Socket.IO events

## Deployment

### Docker (Recommended)

```dockerfile
FROM nvidia/cuda:12.1-runtime-ubuntu22.04
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY processing_server/ .
CMD ["python", "core/processing_server.py"]
```

### Bare Metal

```bash
# SSH tunnel to remote DB
ssh -L 5433:db-host:5432 -R 5001:127.0.0.1:5001 user@cluster

# Start server
cd processing_server/core/
python processing_server.py
```

## Performance

- Detection: 25-40 FPS (YOLO11n @ 1280px, 3 GPUs)
- Re-ID: 8-15 camera pairs/sec (TransReID embeddings)
- Crowd: 60+ FPS (DM-Count @ 480px)
- Memory: ~8GB per GPU (lazy loading)

## Troubleshooting

### Import Errors
```bash
# Verify venv active
which python  # should show venv/bin/python

# Reinstall deps
pip install --upgrade -r requirements.txt
```

### GPU Not Found
```bash
# Check CUDA
nvidia-smi
echo $CUDA_VISIBLE_DEVICES

# Verify PyTorch
python -c "import torch; print(torch.cuda.is_available())"
```

### Model Not Found
```
[INIT] ERROR ERROR: 'models/...' does not exist
```
- Verify model files in ./models/
- Check MODEL_PATH in .env
- All paths are relative to processing_server/

### Database Connection
```
sqlalchemy.exc.OperationalError
```
- Verify DATABASE_URL in .env
- Check PostgreSQL is running
- Verify credentials & network access

## References

- YOLO: https://docs.ultralytics.com/
- ByteTrack: https://github.com/ifzhang/ByteTrack
- TransReID: https://github.com/michuanhaohao/TransReID
- DM-Count: https://github.com/cvlab-stonybrook/DM-Count
- Flask-SocketIO: https://flask-socketio.readthedocs.io/

## License

Internal use only.

---

Questions? Check SETUP.md for detailed setup instructions.
