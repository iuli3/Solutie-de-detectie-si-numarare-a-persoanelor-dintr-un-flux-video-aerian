# Processing Server - Setup

## Structura Portabila

Codul e **100% portabil** - merge pe orice mașină indiferent de paths.

```
processing_server/
├── core/              ← Server core
├── inference/         ← Inference modules
├── utils/             ← Utilities
├── models/            ← 1.3GB modele (relative paths)
├── datasets/          ← Antrenare datasets
├── runs/              ← Training results
├── .env.example       ← Template configurare
├── .env               ← Local config (git-ignored)
└── ...
```

## Primii Pasi - Setup Detaliat

### 1. Clone Repository

```bash
git clone <repo-url> processing_server
cd processing_server
```

Structura:
```
processing_server/
├── core/              -- Server core
├── inference/         -- ML modules
├── utils/             -- Utilities
├── models/            -- 1.3GB modele
├── .env.example       -- Config template
├── requirements.txt   -- Python dependencies
└── README.md          -- This project
```

### 2. Create & Activate Virtual Environment

**Option A: Using venv (Python 3.10+)**
```bash
python3 -m venv venv
source venv/bin/activate          # Linux/Mac
# OR
venv\Scripts\activate.bat         # Windows
```

**Option B: Using conda**
```bash
conda create -n processing_server python=3.10
conda activate processing_server
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

What gets installed:
- 123+ Python packages
- Flask + Socket.IO server
- PyTorch 2.1.2 + CUDA support
- YOLO, TransReID, DM-Count models
- PostgreSQL client, MinIO client
- Testing & development tools

Installation:
- Time: 15-20 minutes
- Size: ~15-20 GB (PyTorch ~2.5GB)
- Requires: Free disk space, internet connection

### 4. Configure Environment Variables

```bash
cp .env.example .env
```

Edit `.env` with your system settings:

```ini
# GPU - CUDA device IDs available on your machine
CUDA_VISIBLE_DEVICES=0,1,2

# Server port
PROCESSING_SERVER_PORT=5001

# PostgreSQL database connection
DATABASE_URL=postgresql://user:password@db-host:5432/database

# MinIO S3 storage
MINIO_ENDPOINT=minio-host:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET=videos

# Model files (relative to processing_server/)
MODEL_PATH=models/yolo11m_smallperson_aerial_1280.engine
```

See `.env.example` for all available options.

### 5. Initialize Database (Optional)

If using PostgreSQL with tracking:
```bash
python run_migrations.py
```

Creates tables: `video`, `person_log`, `global_person`, `multicam_log`

### 6. Start Server

```bash
cd core/
python processing_server.py
```

Expected startup output (takes 30-60 sec):
```
[INIT] CUDA_VISIBLE_DEVICES=0,1,2
[INIT] torch.cuda.device_count()=3
[INIT] AVAILABLE_GPUS=[0, 1, 2]
[INIT] Strategie: Lazy loading YOLO models (on-demand per GPU)
[INIT] Model YOLO incarcat pe cuda:2 ✓
[INIT] Ambele modele DM-Count incarcate si cached. ✓
[INIT] tracking_inference importat cu succes. ✓
[INIT] Modele tracking preloadede pe GPU: [0] ✓
Processing Server - Port: 5001 ✓
 * Running on http://127.0.0.1:5001
```

Server ready! All models loaded, all GPUs initialized.

## Key Points

✓ **Model paths** - automat din `models/` relativ
✓ **Data paths** - relative la processing_server/
✓ **Configs** - din `.env` (personalizabil per masina)
✓ **Zero hardcoded absolute paths** - merge oriunde
✓ **Git-friendly** - `.env` e in `.gitignore`

## Exemplu: Setup pe altă mașină

```bash
# 1. Clone
git clone <repo> processing_server
cd processing_server

# 2. Setup
cp .env.example .env
# Editeaza .env pentru DB/MinIO IPs + credentials

# 3. Run
cd core/
python processing_server.py
```

**Works everywhere!** 🚀
