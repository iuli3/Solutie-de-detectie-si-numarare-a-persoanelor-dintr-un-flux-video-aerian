# Testarea aplicatiei OverWatch

Acest document centralizeaza testele implementate pentru aplicatie: teste unitare, de integrare, de securitate, functionale, end-to-end si de performanta.

## Rezumat rezultate

| Tip test | Tehnologie | Comanda principala | Rezultat obtinut |
|---|---|---|---|
| Unitare backend | pytest | `venv/bin/python -m pytest` | `24 passed` |
| Integrare backend | pytest + Flask test client | `venv/bin/python -m pytest` | incluse in cele `24 passed` |
| Securitate backend | pytest + JWT/API checks | `venv/bin/python -m pytest` | incluse in cele `24 passed` |
| Functionale backend | pytest + Flask test client | `venv/bin/python -m pytest` | incluse in cele `24 passed` |
| Coverage backend | pytest-cov | `venv/bin/python -m pytest --cov=. --cov-report=term-missing` | `TOTAL 40%` |
| End-to-end frontend/backend | Playwright | `npm run test:e2e` | 4 teste passed fara upload; 5 passed cu video setat |
| Upload E2E real | Playwright + deployment real | `npx playwright test e2e/cluster-upload.spec.js` | `1 passed` |
| Performanta smoke | script Python | `venv/bin/python tests/performance_smoke.py ...` | script pregatit, ruleaza contra API pornit |

## 1. Teste backend

Testele backend sunt in:

```text
backend/tests/
```

Fisier de configurare:

```text
backend/pytest.ini
backend/.coveragerc
```

Dependinte adaugate:

```text
pytest==8.4.2
pytest-cov==7.0.0
```

### Rulare

```bash
cd ~/proiect_licenta/backend
venv/bin/python -m pytest
```

Rezultat obtinut:

```text
24 passed
```

### Rulare cu coverage

```bash
cd ~/proiect_licenta/backend
venv/bin/python -m pytest --cov=. --cov-report=term-missing
```

Rezultat obtinut:

```text
24 passed
TOTAL coverage: 40%
```

Raportul de coverage exclude fisiere care nu reprezinta logica principala de aplicatie:

```text
venv/*
tests/*
migrate_*.py
sitecustomize.py
```

### 1.1 Teste unitare

Fisier:

```text
backend/tests/test_auth.py
```

Acopera:

- creare cont nou;
- verificarea faptului ca parola/hash-ul nu este expus in raspuns;
- validare register fara email/parola;
- respingere email duplicat;
- login cu credentiale corecte;
- login cu parola gresita;
- acces `/auth/me` cu si fara JWT.

Exemple de comportament validat:

- `/auth/register` returneaza `201` la user nou;
- `/auth/register` returneaza `409` la email duplicat;
- `/auth/login` returneaza `401` la parola gresita;
- `/auth/me` returneaza `401` fara token.

### 1.2 Teste de integrare backend

Fisiere:

```text
backend/tests/test_video_workflows.py
backend/tests/test_video_metadata_and_delete.py
backend/tests/test_tracking_sessions.py
```

Acopera integrarea dintre endpointuri, Flask test client si baza de date de test:

- upload video creeaza inregistrare in DB;
- upload duplicat este respins;
- dashboard-ul intoarce doar datele userului curent;
- metadata video intoarce campurile corecte;
- metadata detecteaza modurile `detection` si `crowd`;
- variantele video normal/heatmap sunt raportate corect;
- delete video sterge inregistrarea ownerului;
- listare/get/delete pentru tracking sessions.

Testele folosesc SQLite temporar si mock-uri pentru MinIO si processing cluster. Astfel, testele ruleaza rapid si nu depind de Postgres, MinIO sau clusterul real.

### 1.3 Teste de securitate backend

Fisier:

```text
backend/tests/test_api_security.py
```

Acopera:

- endpointuri protejate care cer JWT;
- upload fara autentificare respins;
- dashboard fara autentificare respins;
- un user nu poate accesa metadata video-ului altui user;
- un user nu poate sterge video-ul altui user.

Comportamente validate:

- endpointurile protejate returneaza `401` fara token;
- accesul la resursele altui user returneaza `404`, nu datele resursei.

### 1.4 Teste functionale backend

Acopera fluxuri functionale de baza:

- register -> token valid;
- login -> token valid;
- upload -> video creat;
- dashboard -> statistici corecte;
- YouTube URL invalid -> eroare controlata;
- tracking session -> listare/stergere.

## 2. Teste end-to-end

Testele E2E sunt in:

```text
frontend/yoloclient/e2e/
```

Configurare:

```text
frontend/yoloclient/playwright.config.js
frontend/yoloclient/E2E.md
```

Dependinta adaugata:

```text
@playwright/test
```

### Rulare pe deployment real

Deployment folosit la testare:

```text
Frontend: http://10.13.20.17
Backend:  http://10.13.20.17:5000
```

Comanda fara upload video:

```bash
cd ~/proiect_licenta/frontend/yoloclient
E2E_BASE_URL=http://10.13.20.17 E2E_API_URL=http://10.13.20.17:5000 npm run test:e2e
```

Rezultatul obtinut fara `E2E_VIDEO_PATH`:

```text
auth-ui.spec.js           1 passed
auth-dashboard.spec.js    1 passed
protected-route.spec.js   1 passed
detection.spec.js         1 passed
cluster-upload.spec.js    1 skipped
```

Testul de upload este `skipped` daca nu este setata variabila `E2E_VIDEO_PATH`.

### Rulare cu upload video real

Video folosit:

```text
/home/iuliana/4553748-uhd_3840_2160_24fps.mp4
```

Comanda:

```bash
cd ~/proiect_licenta/frontend/yoloclient
E2E_BASE_URL=http://10.13.20.17 E2E_API_URL=http://10.13.20.17:5000 E2E_VIDEO_PATH=/home/iuliana/4553748-uhd_3840_2160_24fps.mp4 npx playwright test e2e/cluster-upload.spec.js
```

Rezultat obtinut:

```text
1 passed
```

Testul de upload verifica:

- acces autentificat in aplicatie;
- deschiderea paginii `/detection`;
- selectarea fisierului video real;
- trimiterea requestului real `POST /upload`;
- raspuns backend `201`, adica upload acceptat si fluxul de incarcare a pornit corect.

### 2.1 Scenarii E2E implementate

#### `auth-ui.spec.js`

Tip: E2E functional + autentificare.

Acopera:

- register real din UI;
- redirect la login;
- login real din UI;
- dashboard incarcat dupa autentificare.

Rezultat:

```text
1 passed
```

#### `auth-dashboard.spec.js`

Tip: E2E functional.

Acopera:

- sesiune autentificata;
- deschidere dashboard;
- verificare elemente dashboard: `Server Online`, `Upload Video`.

Rezultat:

```text
1 passed
```

#### `protected-route.spec.js`

Tip: E2E securitate.

Acopera:

- acces la `/dashboard` fara autentificare;
- redirect automat la `/login`.

Rezultat:

```text
1 passed
```

#### `detection.spec.js`

Tip: E2E functional UI.

Acopera:

- deschidere pagina `/detection`;
- existenta zonei `Processing mode`;
- deschidere dropdown mod procesare;
- existenta celor 3 optiuni;
- selectarea unui mod crowd;
- aparitia controlului de heatmap opacity.

Rezultat:

```text
1 passed
```

#### `cluster-upload.spec.js`

Tip: E2E functional + integrare reala backend/cluster upload flow.

Acopera:

- autentificare;
- pagina Detection;
- upload fisier video real;
- request real `POST /upload`;
- validare raspuns `201`.

Rezultat cu `E2E_VIDEO_PATH` setat:

```text
1 passed
```

## 3. Teste de performanta

Script:

```text
backend/tests/performance_smoke.py
```

Tip: smoke performance test pentru API.

Ruleaza cereri concurente catre `/api/dashboard-stats` si masoara:

- numar requesturi;
- concurenta;
- throughput requesturi/secunda;
- latenta medie;
- mediana;
- p95;
- max latency;
- esecuri HTTP.

Comanda exemplu:

```bash
cd ~/proiect_licenta/backend
venv/bin/python tests/performance_smoke.py   --base-url http://10.13.20.17:5000   --username EMAIL_EXISTENT   --password PAROLA   --requests 100   --concurrency 10   --max-p95-ms 500
```

Testul pica daca:

- exista raspunsuri HTTP `>= 400`;
- p95 depaseste limita setata prin `--max-p95-ms`.

## 4. Observatii tehnice

### De ce backend coverage este 40%

Coverage-ul total este `40%` deoarece `app.py` contine foarte mult cod dependent de servicii externe:

- Socket.IO events;
- processing server din cluster;
- streaming video din MinIO;
- YouTube download/ffmpeg;
- Re-ID multi-camera;
- procesare live.

Aceste parti nu sunt rulate in testele unitare locale, deoarece testele automate nu trebuie sa depinda permanent de cluster sau fisiere video mari. Pentru ele au fost adaugate teste E2E separate, rulate pe deployment-ul real.

### De ce testele E2E sunt rulate pe spec-uri separate

Pagina de login/register include un canvas animat. In Chromium headless pe server, rularea mai multor scenarii cu acea pagina in acelasi proces Playwright a produs instabilitate. Din acest motiv scripturile E2E ruleaza spec-urile in procese separate, oferind rezultate stabile.

Scriptul principal este:

```bash
npm run test:e2e
```

Intern ruleaza:

```bash
npm run test:e2e:ui
npm run test:e2e:app
```

## 5. Comenzi utile

### Backend tests

```bash
cd ~/proiect_licenta/backend
venv/bin/python -m pytest
```

### Backend coverage

```bash
cd ~/proiect_licenta/backend
venv/bin/python -m pytest --cov=. --cov-report=term-missing
```

### E2E fara upload

```bash
cd ~/proiect_licenta/frontend/yoloclient
E2E_BASE_URL=http://10.13.20.17 E2E_API_URL=http://10.13.20.17:5000 npm run test:e2e
```

### E2E upload real

```bash
cd ~/proiect_licenta/frontend/yoloclient
E2E_BASE_URL=http://10.13.20.17 E2E_API_URL=http://10.13.20.17:5000 E2E_VIDEO_PATH=/home/iuliana/4553748-uhd_3840_2160_24fps.mp4 npm run test:e2e
```

### Doar testul de upload

```bash
cd ~/proiect_licenta/frontend/yoloclient
E2E_BASE_URL=http://10.13.20.17 E2E_API_URL=http://10.13.20.17:5000 E2E_VIDEO_PATH=/home/iuliana/4553748-uhd_3840_2160_24fps.mp4 npx playwright test e2e/cluster-upload.spec.js
```

## 6. Concluzie

Au fost implementate si rulate teste automate pentru principalele niveluri de verificare ale aplicatiei:

- teste unitare backend;
- teste de integrare backend;
- teste de securitate backend;
- teste functionale backend;
- teste end-to-end pe deployment real;
- test E2E cu upload video real;
- script de performanta pentru API.

Rezultatele obtinute confirma ca fluxurile principale functioneaza corect:

```text
Backend: 24 passed
Backend coverage: 40%
E2E fara upload: 4 passed, 1 skipped
E2E upload real: 1 passed
```
