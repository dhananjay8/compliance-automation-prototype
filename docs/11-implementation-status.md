# Implementation Status

This document tracks what is currently built in the `prototype/` directory versus what is still described only in the design docs and roadmap.

## Implemented

- **FastAPI API** (`prototype/app.py`)
  - Tenant, integration, resource, control, test, evidence, posture, audit, and RAG endpoints
  - Header-based tenant context and RBAC
  - DB-backed user/role validation when `MOCK_AUTH` is not set
- **Database schema** (`prototype/schema.sql`)
  - All core tables: tenant, organization, user, framework, section, common_control, framework_control, control_test, test, test_run, resource, test_result, evidence, policy, access_review, vendor, audit, audit_log, and RAG index tables
- **Rule engine** (`prototype/engine.py`)
  - Operators: `eq`, `ne`, `in`, `not_in`, `gt`, `lt`, `gte`, `lte`, `exists`, `and`, `or`
  - Nested field support
- **Worker** (`prototype/worker.py`)
  - Mock AWS/Okta resource sync
  - Resource upsert with content hashing
  - Test execution and evidence insertion
- **RAG service** (`prototype/rag.py`)
  - Query classification, entity extraction, SQL-first retrieval, keyword trigram fallback
  - Context builder with citations and MockLLMProvider
  - Endpoints: `POST /api/v1/rag/query`, `POST /api/v1/rag/index/rebuild`, `POST /api/v1/rag/index/entity`, `GET /api/v1/rag/health`
- **Seed data and validation** (`data/*.json`, `scripts/validate_seed_data.py`, `scripts/generate_seed_data.py`)
- **Local test flow** (`podman/test.sh`)
  - Podman PostgreSQL + Redis, schema load, seed, and DB count assertions
- **Unit tests** (`prototype/tests/`)
  - RAG, rule engine, and auth (mock mode)

## Not yet implemented

- **Frontend**: No React/Vite/Tailwind app exists
- **Full-stack build prompt**: `prompts/build-prototype.md` still describes the original Node/Express/Prisma/React spec
- **Production auth**: SSO, SAML/OIDC, JWT, SCIM, and field-level encryption
- **Connectors**: Only mock AWS/Okta adapters; other categories described in `docs/06-connector-architecture.md` are not wired
- **Queue/scheduler**: No BullMQ, Redis-backed scheduler, or recurring sync
- **Drift detection**: No continuous drift engine or stale-evidence alerts
- **Workflow engine**: No remediation, ticketing, or SLA escalation
- **Audit portal**: `GET /api/v1/audits/{id}/requests` exists but is not a dedicated UI
- **Multi-tenancy features**: No regional cells, data residency, or tenant-scoped connection pools
- **Cross-resource joins**: `engine.py` evaluates one resource at a time
- **Docker Compose**: Only `podman/test.sh` is provided

## Roadmap mapping

- **Phase 0** (Foundation): partial — schema, basic auth headers, RBAC checks, and mock-auth mode exist; SSO, audit logging, and field-level encryption are in progress or not started
- **Phase 1** (MVP ingestion + SOC 2): partial — mock sync and test execution exist; dashboard UI and real connectors do not
- **Phase 2** (Multi-framework + custom controls): partial — multi-framework mappings exist in seed data; policy management and manual evidence are not implemented
- **Phase 3** (Workflows + audit portal): not started
- **Phase 4** (Scale + intelligence): not started
