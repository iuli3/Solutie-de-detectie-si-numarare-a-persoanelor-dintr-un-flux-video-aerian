# Teste End-to-End

Testele E2E folosesc Playwright si ruleaza impotriva aplicatiei pornite real: frontend, backend, baza de date si, optional, processing server-ul din cluster.

## Instalare

```bash
cd ~/proiect_licenta/frontend/yoloclient
npm install
npx playwright install chromium
```

## Rulare locala / server

Daca frontend-ul e pe portul 5173 si backend-ul pe 5000:

```bash
cd ~/proiect_licenta/frontend/yoloclient
E2E_BASE_URL=http://IP_SERVER:5173 \
E2E_API_URL=http://IP_SERVER:5000 \
npm run test:e2e
```

Daca ai mapat frontend-ul pe portul 80, foloseste doar IP-ul:

```bash
E2E_BASE_URL=http://IP_SERVER E2E_API_URL=http://IP_SERVER:5000 npm run test:e2e
```

## Test E2E cu processing cluster real

Testul de upload catre cluster este optional si ruleaza doar daca dai un fisier video mic:

```bash
E2E_BASE_URL=http://IP_SERVER \
E2E_API_URL=http://IP_SERVER:5000 \
E2E_VIDEO_PATH=/home/iuliana/test-small.mp4 \
npm run test:e2e
```

Fara `E2E_VIDEO_PATH`, testul de upload este skipped.

## Ce acopera

- register real din browser;
- login real din browser;
- dashboard incarcat din backend;
- redirect pentru rute protejate;
- pagina Detection si dropdown-ul de mode;
- optional: upload video prin UI catre flow-ul real de procesare/cluster.
