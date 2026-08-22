# Implementation Status

This document tracks what is currently built in the `prototype/` directory versus what is still described only in the design docs and roadmap.

## Implemented

- **FastAPI API** (`prototype/app.py`)
  - CORS enabled for the React frontend
  - Tenant, integration, resource, control, test, evidence, posture, audit, dashboard, policy, and RAG endpoints
  - Integration: create, get, health, test, sync, sync-job status, and sync-job listing
  - Controls: create custom controls, framework mapping lookup, bulk multi-framework mappings, custom tests per control, and framework-specific control listing
  - Evidence: list, create, detail, and file upload with local storage
  - Phase 3 workflow/audit portal endpoints: remediations, access review campaigns, vendor risk questionnaires, audit information requests, and webhook subscriptions/deliveries
  - Header-based tenant context and RBAC, plus JWT `Bearer` token support and a token endpoint
  - DB-backed user/role validation when `MOCK_AUTH` is not set
  - Audit logging middleware writing to `audit_log`
- **Database schema** (`prototype/schema.sql`)
  - All core tables: tenant, organization, user, framework, section, common_control, framework_control, control_test, test, test_run, resource, test_result, evidence, policy, access_review, vendor, audit, audit_log, and RAG index tables
- **Rule engine** (`prototype/engine.py`)
  - Operators: `eq`, `ne`, `in`, `not_in`, `gt`, `lt`, `gte`, `lte`, `exists`, `and`, `or`
  - Nested field support
- **Connectors** (`prototype/connectors/`)
  - `AWSConnector` lists live IAM users and EC2 instances via `boto3` when credentials are configured; falls back to mock samples on errors or missing credentials
  - `OktaConnector` lists live users and factors via `requests` when token + base URL are configured; falls back to mock samples on errors or missing credentials
  - Health checks verify live connectivity with STS and `/api/v1/users`
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
- **Frontend** (`frontend/`)
  - React + Vite + Tailwind CSS SPA
  - Dashboard, integrations, controls, evidence, and policies views
  - Phase 3 Workflow & Audit portal view with remediations, access reviews, vendors, audits, and webhooks
  - Wired to FastAPI with CORS and Vite proxy

## Not yet implemented

- **Full-stack build prompt**: `prompts/build-prototype.md` still describes the original Node/Express/Prisma/React spec
- **Production auth**: SSO, SAML/OIDC, SCIM, and field-level encryption
- **Queue/scheduler**: No BullMQ, Redis-backed scheduler, or recurring sync
- **Drift detection**: No continuous drift engine or stale-evidence alerts
- **Production ticketing integrations**: No Jira / ServiceNow adapters; only ticket ID attachment
- **Multi-tenancy features**: No regional cells, data residency, or tenant-scoped connection pools
- **Cross-resource joins**: `engine.py` evaluates one resource at a time

## Roadmap mapping

- **Phase 0** (Foundation): largely complete — schema, JWT token support, header and DB auth, RBAC, and audit logging are implemented
- **Phase 1** (MVP ingestion + SOC 2): complete — real AWS/Okta adapters, frontend, connector SDK, integration health, sync wiring, dashboards, and evidence collection are implemented
- **Phase 2** (Multi-framework + custom controls): largely complete — custom control creation, framework mapping lookup, policy management, acknowledgements, and manual evidence upload are implemented
- **Phase 3** (Workflows + audit portal): largely complete — remediation workflows, access review campaigns, vendor risk questionnaires, auditor portal with information requests, webhook subscriptions/deliveries, and frontend coverage are implemented
- **Phase 4** (Scale + intelligence): not started
