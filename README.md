# Solutie de detectie si numarare a persoanelor dintr-un flux video aerian

Proiect de licenta

Profesor coordonator: de completat

Autor: Iuliana Turcanu

## Descriere generala

Acest proiect implementeaza o platforma web pentru analiza fluxurilor video aeriene, cu accent pe detectia, numararea si urmarirea persoanelor. Aplicatia permite incarcarea de imagini si videoclipuri, procesarea fluxurilor live sau a linkurilor YouTube, vizualizarea rezultatelor in timp real si consultarea istoricului de procesare.

Solutia este gandita ca un sistem distribuit format dintr-o interfata web, un backend de aplicatie si un server separat de procesare GPU. Serverul de procesare ruleaza modelele de computer vision, iar backend-ul gestioneaza autentificarea, persistenta datelor, stocarea fisierelor si comunicarea dintre frontend si clusterul de procesare.

## Functionalitati principale

- Detectia persoanelor in imagini, videoclipuri si fluxuri live.
- Numararea persoanelor din cadre video aeriene.
- Procesare in timp real prin Socket.IO.
- Estimarea densitatii multimii folosind DM-Count.
- Tracking temporal cu ByteTrack.
- Re-identificare multi-camera folosind TransReID.
- Salvarea fisierelor originale si procesate in MinIO, compatibil S3.
- Persistenta metadatelor si rezultatelor in PostgreSQL.
- Dashboard cu statistici si istoric de procesare.
- Autentificare utilizatori cu JWT.
- Interfata React pentru incarcare, vizualizare rezultate si analiza sesiuni.

## Arhitectura proiectului

Repository-ul contine doua componente mari:

```text
.
|-- proiect_licenta/
|   |-- backend/                 Backend Flask pentru API, autentificare si DB
|   |-- frontend/yoloclient/     Frontend React + Vite
|   `-- docker-compose.yml       PostgreSQL, MinIO, backend si frontend
|
|-- processing_server/
|   |-- core/                    Server Flask + Socket.IO pentru procesare GPU
|   |-- inference/               Module YOLO, DM-Count, tracking si Re-ID
|   |-- utils/                   Utilitare MinIO, DB si Re-ID
|   |-- DM-count/                Modul pentru crowd counting
|   `-- models/                  Modele ML versionate cu Git LFS
```

Fluxul principal este:

```text
Frontend React
    |
    | HTTP + Socket.IO
    v
Backend Flask - port 5000
    |
    | PostgreSQL + MinIO
    v
Date persistente si fisiere video
    |
    | Socket.IO / HTTP catre cluster
    v
Processing Server GPU - port 5001
    |
    v
YOLO / ByteTrack / TransReID / DM-Count
```

## Tehnologii folosite

Frontend:

- React 19
- Vite
- Tailwind CSS
- Axios
- Socket.IO Client
- React Router
- Lucide React
- Playwright pentru teste end-to-end

Backend aplicatie:

- Python 3.12
- Flask
- Flask-SocketIO
- Flask-JWT-Extended
- Flask-Bcrypt
- Flask-SQLAlchemy
- PostgreSQL
- MinIO
- yt-dlp
- ffmpeg

Processing server:

- Python 3.10+
- Flask + Socket.IO
- PyTorch
- Ultralytics YOLO
- OpenCV
- TensorRT / CUDA
- ByteTrack
- TransReID
- DM-Count

Infrastructura:

- Docker Compose
- PostgreSQL 16
- MinIO
- Nginx pentru frontend-ul construit
- Git LFS pentru modelele mari

## Modele incluse

Modelele sunt pastrate in `processing_server/models/` si sunt versionate prin Git LFS:

```text
processing_server/models/best.pt
processing_server/models/yolo11n.pt
processing_server/models/yolo11n-seg.pt
processing_server/models/yolo26best.engine
processing_server/models/yolo11m_smallperson_aerial_1280.engine
processing_server/models/vit_transreid_msmt.pth
processing_server/models/vgg19-dcbb9e9d.pth
processing_server/models/model_qnrf.pth
processing_server/models/model_nwpu.pth
```

La clonarea proiectului este necesar Git LFS, altfel fisierele mari vor fi descarcate doar ca pointere text.

## Cerinte

Pentru rulare completa:

- Git
- Git LFS
- Docker si Docker Compose
- Python 3.10+ pentru `processing_server`
- Python 3.12 pentru backend, daca se ruleaza local fara Docker
- Node.js 20+ pentru frontend, daca se ruleaza local fara Docker
- NVIDIA GPU cu CUDA 12.x pentru procesarea accelerata
- ffmpeg disponibil in sistem
- Spatiu liber suficient pentru dependinte si modele, recomandat cel putin 20 GB

Pentru rulare doar cu infrastructura Docker:

- Docker Desktop
- Git LFS
- Un processing server pornit separat pe masina/cluster cu GPU

## Clonare repository

```bash
git clone https://github.com/iuli3/Solutie-de-detectie-si-numarare-a-persoanelor-dintr-un-flux-video-aerian.git
cd Solutie-de-detectie-si-numarare-a-persoanelor-dintr-un-flux-video-aerian
git lfs pull
```

La clonare se descarca:

- codul sursa pentru frontend, backend si processing server;
- fisierele de configurare exemplu (`.env.example`);
- modelele ML din `processing_server/models/`, prin Git LFS;
- documentatia si fisierele Docker.

Nu se descarca si nu sunt versionate:

- fisierele locale `.env`;
- mediile virtuale Python (`venv/`, `venv_*/`);
- `node_modules/`;
- `__pycache__/` si cache-uri de testare;
- upload-uri, rezultate generate si loguri runtime.

Verificare modele:

```bash
git lfs ls-files
```

## Configurare variabile de mediu

Fisierele `.env` locale nu sunt urcate in GitHub. Ele trebuie create pe fiecare masina.

### Processing server

```bash
cd processing_server
cp .env.example .env
```

Exemplu de configuratie:

```ini
CUDA_VISIBLE_DEVICES=0,1,2
PROCESSING_SERVER_PORT=5001
DATABASE_URL=postgresql://admin:parola_sigura@127.0.0.1:5433/licenta_db
MINIO_ENDPOINT=127.0.0.1:9000
MINIO_ACCESS_KEY=admin
MINIO_SECRET_KEY=parola_sigura
MINIO_BUCKET=licenta-videos
MINIO_SECURE=False
MODEL_PATH=models/yolo11m_smallperson_aerial_1280.engine
```

### Backend Flask

Creati fisierul:

```bash
proiect_licenta/backend/.env
```

Exemplu:

```ini
DATABASE_URL=postgresql://admin:parola_sigura@localhost:5433/licenta_db
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=admin
MINIO_SECRET_KEY=parola_sigura
MINIO_BUCKET=licenta-videos
MINIO_SECURE=False
PROCESSING_SERVER_URL=http://localhost:5001
FLASK_PORT=5000
FLASK_DEBUG=false
JWT_SECRET_KEY=schimba_aceasta_valoare
```

In Docker Compose, backend-ul primeste o parte din aceste valori direct din `docker-compose.yml`.

### Frontend React

Pentru rulare locala:

```bash
proiect_licenta/frontend/yoloclient/.env
```

Exemplu:

```ini
VITE_API_URL=http://localhost:5000
```

## Pornire infrastructura cu Docker Compose

Din folderul `proiect_licenta`:

```bash
cd proiect_licenta
docker compose up -d postgres minio
```

Servicii disponibile:

- PostgreSQL: `localhost:5433`
- MinIO API: `http://localhost:9000`
- MinIO Console: `http://localhost:9001`

Credentialele implicite din `docker-compose.yml`:

```text
PostgreSQL database: licenta_db
PostgreSQL user: admin
PostgreSQL password: parola_sigura
MinIO user: admin
MinIO password: parola_sigura
```

Pentru pornirea backend-ului si frontend-ului tot prin Docker:

```bash
docker compose up -d --build
```

Pentru instalari mai vechi, unde este disponibil `docker-compose` v1:

```bash
docker-compose -f docker-compose.yml up -d --build
```

Daca `docker-compose` v1 da eroarea `KeyError: 'ContainerConfig'`, folositi Docker Compose v2:

```bash
docker compose up -d --build
```

Verificare containere:

```bash
docker compose ps
```

Atentie: in `docker-compose.yml`, variabila `PROCESSING_SERVER_URL` si argumentul `VITE_API_URL` pot contine IP-uri locale din mediul de dezvoltare. Pentru alta masina, actualizati aceste valori astfel incat backend-ul sa poata ajunge la serverul de procesare, iar frontend-ul sa poata ajunge la backend.

## Pornire processing server

Serverul de procesare se ruleaza separat, de regula pe masina cu GPU.

```bash
cd processing_server
python -m venv venv
```

Activare mediu virtual:

Windows:

```powershell
venv\Scripts\activate
```

Linux/macOS:

```bash
source venv/bin/activate
```

Instalare dependinte:

```bash
pip install -r requirements.txt
```

Initializare tabele:

```bash
python run_migrations.py
```

Pornire server:

```bash
cd core
python processing_server.py
```

La pornire, serverul ar trebui sa fie disponibil pe:

```text
http://127.0.0.1:5001
```

Startup-ul poate dura 30-60 secunde, deoarece sunt incarcate modelele YOLO, DM-Count si Re-ID.

## Pornire backend local

Daca nu folositi containerul Docker pentru backend:

```bash
cd proiect_licenta/backend
python -m venv venv
```

Windows:

```powershell
venv\Scripts\activate
```

Linux/macOS:

```bash
source venv/bin/activate
```

Instalare dependinte:

```bash
pip install -r requirements.txt
```

Pornire:

```bash
python app.py
```

Backend-ul ruleaza pe:

```text
http://localhost:5000
```

## Pornire frontend local

```bash
cd proiect_licenta/frontend/yoloclient
npm install
npm run dev
```

Frontend-ul Vite va afisa in consola URL-ul local, de obicei:

```text
http://localhost:5173
```

Pentru build de productie:

```bash
npm run build
```

Pentru preview local al build-ului:

```bash
npm run preview
```

## Ordinea recomandata de pornire

Pentru rulare completa locala:

1. Porniti PostgreSQL si MinIO:

```bash
cd proiect_licenta
docker compose up -d postgres minio
```

2. Porniti processing server-ul:

```bash
cd processing_server/core
python processing_server.py
```

3. Porniti backend-ul:

```bash
cd proiect_licenta/backend
python app.py
```

4. Porniti frontend-ul:

```bash
cd proiect_licenta/frontend/yoloclient
npm run dev
```

5. Deschideti aplicatia in browser la URL-ul afisat de Vite.

## Utilizare aplicatie

Aplicatia permite:

- crearea unui cont si autentificare;
- incarcarea unei imagini pentru detectie;
- incarcarea unui videoclip pentru procesare;
- procesarea unui link YouTube;
- conectarea la un stream live;
- alegerea modului de analiza: detectie, crowd counting sau tracking;
- vizualizarea cadrelor procesate in timp real;
- consultarea istoricului de procesari;
- inspectarea rezultatelor pentru sesiuni de tracking multi-camera.

## Testare

### Backend Flask

```bash
cd proiect_licenta/backend
pytest
```

Exista teste pentru autentificare, securitate API, workflow-uri video, stergere si metadate.

### Frontend

```bash
cd proiect_licenta/frontend/yoloclient
npm run lint
npm run test:e2e
```

Testele Playwright acopera autentificarea, rutele protejate, dashboard-ul, detectia si upload-ul pentru cluster.

### Processing server

```bash
cd processing_server
pytest tests/ -v
```

Sau, pe Linux/macOS:

```bash
./run_tests.sh quick
./run_tests.sh yolo
./run_tests.sh crowd
./run_tests.sh reid
```

## Troubleshooting

### Modelele nu se descarca la clone

Verificati ca Git LFS este instalat:

```bash
git lfs install
git lfs pull
```

### Processing server nu vede GPU-ul

```bash
nvidia-smi
python -c "import torch; print(torch.cuda.is_available())"
```

Verificati `CUDA_VISIBLE_DEVICES` in `processing_server/.env`.

### Backend-ul nu se conecteaza la processing server

Verificati:

```ini
PROCESSING_SERVER_URL=http://localhost:5001
```

Daca processing server-ul ruleaza pe alta masina, folositi IP-ul acelei masini.

### Eroare la baza de date

Verificati ca PostgreSQL ruleaza:

```bash
cd proiect_licenta
docker compose ps
```

Verificati si `DATABASE_URL` din `.env`.

### Eroare MinIO

Verificati consola MinIO:

```text
http://localhost:9001
```

Asigurati-va ca bucket-ul configurat prin `MINIO_BUCKET` exista sau poate fi creat de aplicatie.

### Port ocupat

Porturi folosite implicit:

- `5000` pentru backend
- `5001` pentru processing server
- `5173` pentru Vite dev server
- `5433` pentru PostgreSQL expus local
- `9000` pentru MinIO API
- `9001` pentru MinIO Console
- `80` pentru frontend in Docker/Nginx

Schimbati porturile in `.env` sau in `docker-compose.yml` daca exista conflicte.

## Observatii despre GitHub si Git LFS

Modelele ML sunt fisiere mari si nu pot fi pastrate eficient in Git normal. Repository-ul foloseste Git LFS pentru extensiile:

```text
*.pt
*.pth
*.engine
*.onnx
*.weights
```

Dupa clonare, rulati mereu:

```bash
git lfs pull
```

Fisierele ignorate intentionat:

- `.env` si secrete locale;
- medii virtuale Python;
- `node_modules`;
- build-uri frontend;
- upload-uri si rezultate generate;
- cache-uri de testare.

## Documentatie suplimentara

- `processing_server/README.md` - detalii despre serverul GPU si modulele ML.
- `processing_server/SETUP.md` - ghid detaliat pentru setup processing server.
- `processing_server/QUICK_START.txt` - pasi rapizi pentru pornirea processing server.
- `proiect_licenta/backend/TESTING.md` - informatii despre testarea backend-ului.
- `proiect_licenta/TESTARE_APLICATIE.md` - scenarii de testare pentru aplicatie.
- `proiect_licenta/frontend/yoloclient/E2E.md` - informatii despre testele end-to-end.

## Licenta

Proiect realizat in scop academic, pentru lucrarea de licenta.
