# Compliance Prototype Frontend

A React + Vite + Tailwind CSS single-page application for the Compliance Automation Prototype.

## Run

Start the FastAPI backend on port `8002`:

```bash
cd prototype
MOCK_AUTH=1 PYTHONPATH=.. .venv/bin/python -m uvicorn app:app --port 8002
```

Then start the dev server:

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`.

## Build

```bash
cd frontend
npm run build
```

## Pages

- **Dashboard** — posture summary and latest failing controls
- **Integrations** — list, test, sync, and sync-job status
- **Controls** — list controls, create custom controls, view framework mappings
- **Evidence** — list evidence and upload manual evidence files
- **Policies** — create and acknowledge policies
