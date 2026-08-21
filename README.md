# Compliance Automation Prototype

A Vanta-like continuous compliance automation prototype. This repository currently contains a working Python/FastAPI backend, PostgreSQL schema, seed data, a Podman-based local test flow, and a RAG (Retrieval-Augmented Generation) service for compliance Q&A.

## What is included

| Directory | Purpose |
|---|---|
| `docs/` | Design documents: case study, framework mapping, architecture, data model, control normalization, connectors, scheduling, security, scalability, roadmap, and implementation status |
| `architecture/` | Mermaid source files for end-to-end and data-model diagrams |
| `data/` | Seed JSON files: frameworks, common controls, mappings, resource types, sample resources, evidence, tenant, and integration catalog |
| `prototype/` | FastAPI backend (`app.py`), rule engine, worker, RAG pipeline, Pydantic models, and database schema |
| `prompts/` | Implementation prompts: original `build-prototype.md` and the repo-aligned RAG prompt |
| `podman/` | `test.sh` script for spinning up a local PostgreSQL + Redis test environment |
| `scripts/` | `generate_seed_data.py` and `validate_seed_data.py` |

## Quick start

1. Install Python dependencies:
   ```bash
   python3 -m venv .venv
   .venv/bin/pip install -r prototype/requirements.txt
   ```

2. Start the local test database:
   ```bash
   ./podman/test.sh start
   ```

3. Run the FastAPI backend locally:
   ```bash
   .venv/bin/uvicorn app:app --app-dir prototype --port 8000 --reload
   ```

4. In a separate terminal, seed the database (uses the running podman Postgres):
   ```bash
   .venv/bin/python podman/seed_test_db.py
   ```

5. Try a RAG query:
   ```bash
   curl -X POST http://localhost:8000/api/v1/rag/query \
     -H "X-Tenant-Id: 00000000-0000-0000-0000-000000000001" \
     -H "X-User-Id: <user-id-from-sample-tenant>" \
     -H "Content-Type: application/json" \
     -d '{"query": "What is the current status of SOC 2 CC6.1?"}'
   ```

For local dry runs without a populated `user` table, set `MOCK_AUTH=1` and use the `X-User-Role` header:
   ```bash
   MOCK_AUTH=1 .venv/bin/uvicorn app:app --app-dir prototype --port 8000
   ```

## Regenerate and validate seed data

```bash
python3 scripts/generate_seed_data.py
python3 scripts/validate_seed_data.py
python3 scripts/validate_seed_data.py --strict-warnings
```

## Run the local test suite

```bash
PYTHONPATH=prototype .venv/bin/pytest prototype/tests/ -q
```

For the full Podman-based integration test (validate, start, seed, assertions):

```bash
./podman/test.sh test
```

## Core API surface

- Tenant: `POST /api/v1/tenants`, `GET /api/v1/tenants/{id}/readiness`
- Integrations: `POST /api/v1/integrations`, `POST /api/v1/integrations/{id}/sync`, `GET /api/v1/integrations`
- Resources: `GET /api/v1/resources`
- Controls: `GET /api/v1/controls`, `GET /api/v1/controls/{id}/status`
- Tests: `POST /api/v1/tests`, `POST /api/v1/tests/{id}/run`
- Evidence: `GET /api/v1/evidence`
- Posture: `GET /api/v1/dashboards/posture`
- Audits: `GET /api/v1/audits`, `GET /api/v1/audits/{id}/requests`, `POST /api/v1/audits/{id}/requests`
- RAG: `POST /api/v1/rag/query`, `POST /api/v1/rag/index/rebuild`, `POST /api/v1/rag/index/entity`, `GET /api/v1/rag/health`

## Tech stack

- Backend: Python 3.11 + FastAPI + Pydantic v2
- Database: PostgreSQL 15 (psycopg 3)
- Rule engine: Python (`prototype/engine.py`)
- Worker: Python (`prototype/worker.py`) with mock AWS/Okta resource sync
- Local infrastructure: Podman (`podman/test.sh`)
- Frontend: **not yet implemented**
- Queue/Scheduler/Drift: **not yet implemented**

## Auth headers

By default, `auth.py` validates the `X-User-Id` header against the `user` table. For mock/dry-run scenarios, set `MOCK_AUTH=1` and pass:

- `X-Tenant-Id`
- `X-User-Id` (optional)
- `X-User-Role` (`admin`, `compliance_manager`, `control_owner`, `auditor`, `read_only`, `external_auditor`)

## Public sources used

Public Vanta engineering blogs, developer docs, integration guides, and the open Vanta control set informed this design. URLs are listed in `docs/01-case-study.md`.

