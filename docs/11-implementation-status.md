# Implementation Status

This document tracks what is currently built in the `prototype/` directory versus what is still described only in the design docs and roadmap.

## Implemented

- **FastAPI API** (`prototype/app.py`)
  - Tenant, integration (with health + sync), resource, control, test, evidence, posture, audit, dashboard, policy, and RAG endpoints
  - Header-based tenant context and RBAC, plus JWT `Bearer` token support and a token endpoint
  - DB-backed user/role validation when `MOCK_AUTH` is not set
  - Audit logging middleware writing to `audit_log`
- **Database schema** (`prototype/schema.sql`)
  - All core tables: tenant, organization, user, framework, section, common_control, framework_control, control_test, test, test_run, resource, test_result, evidence, policy, access_review, vendor, audit, audit_log, and RAG index tables
- **Rule engine** (`prototype/engine.py`)
  - Operators: `eq`, `ne`, `in`, `not_in`, `gt`, `lt`, `gte`, `lte`, `exists`, `and`, `or`
  - Nested field support
- **Worker** (`prototype/worker.py`)
  - Connector SDK wired: `AWSConnector` and `OktaConnector` are used when no real credentials are present
  - Resource upsert with content hashing
  - Test execution and evidence insertion
- **RAG service** (`prototype/rag.py`)
  - Query classification, entity extraction, SQL-first retrieval, keyword trigram fallback
  - Context builder with citations and MockLLMProvider
  - Endpoints: `POST /api/v1/rag/query`, `POST /api/v1/rag/index/rebuild`, `POST /api/v1/rag/index/entity`, `GET /api/v1/rag/health`
- **Seed data and validation** (`data/*.json`, `scripts/validate_seed_data.py`, `scripts/generate_seed_data.py`)
- **Local test flows**
  - `podman/test.sh` (Podman PostgreSQL + Redis, schema load, seed, DB count assertions)
  - `docker-compose.yml` (Docker Compose Postgres + Redis + FastAPI)
  - `scripts/e2e_phase0_2.py` (Phase 0-2 end-to-end smoke test)
- **Unit tests** (`prototype/tests/`)
  - RAG, rule engine, and auth (mock mode + JWT)

## Not yet implemented

- **Frontend**: No React/Vite/Tailwind app exists
- **Full-stack build prompt**: `prompts/build-prototype.md` still describes the original Node/Express/Prisma/React spec
- **Production auth**: SSO, SAML/OIDC, SCIM, and field-level encryption
- **Real connectors**: Adapters still fall back to mock samples for AWS/Okta; no live API calls
- **Queue/scheduler**: No BullMQ, Redis-backed scheduler, or recurring sync
- **Drift detection**: No continuous drift engine or stale-evidence alerts
- **Workflow engine**: No remediation, ticketing, or SLA escalation
- **Audit portal**: `GET /api/v1/audits/{id}/requests` exists but is not a dedicated UI
- **Multi-tenancy features**: No regional cells, data residency, or tenant-scoped connection pools
- **Cross-resource joins**: `engine.py` evaluates one resource at a time

## Roadmap mapping

- **Phase 0** (Foundation): largely complete — schema, JWT token support, header and DB auth, RBAC, and audit logging are implemented
- **Phase 1** (MVP ingestion + SOC 2): largely complete — connector SDK, integration health, sync wiring, dashboards, and evidence collection are implemented; frontend and real API adapters are not
- **Phase 2** (Multi-framework + custom controls): largely complete — custom control creation, framework mapping lookup, policy management, acknowledgements, and manual evidence upload are implemented
- **Phase 3** (Workflows + audit portal): not started
- **Phase 4** (Scale + intelligence): not started
