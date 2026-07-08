# Testare aplicatie

## Backend: unit, integrare, securitate, functionare

Ruleaza toate testele backend:

```bash
cd ~/proiect_licenta/backend
venv/bin/python -m pytest
```

Cu coverage:

```bash
cd ~/proiect_licenta/backend
venv/bin/python -m pytest --cov=. --cov-report=term-missing
```

Ce acopera acum:

- 24 teste automate backend.
- Unit/basic auth: register, login, parola gresita, duplicate email.
- Integrare API: upload creeaza video in DB, dashboard vede doar datele userului curent.
- Securitate API: endpointuri protejate fara JWT, acces interzis la video-ul altui user, delete limitat la owner.
- Functionare: validari pentru upload lipsa, URL YouTube invalid, metadata video, delete video, tracking sessions si fluxuri principale cu client Flask.

Testele folosesc SQLite temporar si mock-uri pentru MinIO/processing cluster, deci nu ating Postgres, MinIO sau serverul de procesare real.

## Performanta

Porneste backend-ul normal, apoi ruleaza smoke test-ul de performanta pe endpointul de dashboard:

```bash
cd ~/proiect_licenta/backend
venv/bin/python tests/performance_smoke.py \
  --base-url http://127.0.0.1:5000 \
  --username EMAIL_EXISTENT \
  --password PAROLA \
  --requests 100 \
  --concurrency 10 \
  --max-p95-ms 500
```

Pentru server, inlocuieste `127.0.0.1` cu IP-ul/API-ul backend. Testul pica daca exista raspunsuri HTTP >= 400 sau daca p95 depaseste limita setata.

## Docker

Daca rulezi testele in containerul backend existent:

```bash
sudo docker exec -it licenta_backend python -m pytest
```

Daca lipseste pytest in container, rebuild-uieste imaginea backend dupa ce `requirements.txt` a fost actualizat.
