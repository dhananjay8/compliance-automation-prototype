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
  - Phase 4 scale/intelligence endpoints: drift detection, evidence freshness/recollection, posture analytics/trend, scheduled job runner, and mock AI remediation suggestions
  - Header-based tenant context and RBAC, plus JWT `Bearer` token support and a token endpoint
  - DB-backed user/role validation when `MOCK_AUTH` is not set
  - Audit logging middleware writing to `audit_log`
- **Database schema** (`prototype/schema.sql`)
  - All core tables: tenant, organization, user, framework, section, common_control, framework_control, control_test, test, test_run, resource, test_result, evidence, policy, access_review, vendor, audit, audit_log, and RAG index tables
  - Phase 3 tables/columns: remediation, webhook subscriptions/deliveries, vendor questionnaires/responses, audit request responses
  - Phase 4 tables/columns: drift detection, resource baselines, posture history, integration/test schedule metadata
- **Rule engine** (`prototype/engine.py`)
  - Operators: `eq`, `ne`, `in`, `not_in`, `gt`, `lt`, `gte`, `lte`, `exists`, `and`, `or`
  - Nested field support
- **Connectors** (`prototype/connectors/`)
  - 15 connectors registered generically in `CONNECTOR_REGISTRY` (`connectors/__init__.py`): AWS, Okta, GitHub, GitLab, Slack, Google Workspace, Microsoft 365/Azure AD, Jira, ServiceNow, PagerDuty, Datadog, Zoom, Salesforce, Snyk, Tenable.io
  - Each connector makes a real API call via `boto3`/`requests` when credentials are configured; falls back to deterministic mock samples on errors or missing credentials
  - `build_connector()`/`list_connector_catalog()` let `app.py`/`worker.py` resolve any connector generically (no per-connector if/elif chains); exposed to the frontend via `GET /api/v1/connectors/catalog`
  - Health checks verify live connectivity per-provider
- **Worker** (`prototype/worker.py`)
  - Connector SDK wired generically via the registry, with graceful fallback to sample resources
  - Resource upsert with content hashing and data-residency region tagging
  - Test execution and evidence insertion (also region-tagged)
- **Credential encryption** (`prototype/crypto.py`)
  - Integration credentials are encrypted at rest with Fernet before being persisted; decrypted only in-memory when a connector needs to make a live call (`resolve_credentials`)
- **Distributed queue** (`prototype/queue_backend.py`, `prototype/queue_worker.py`)
  - Sync jobs are enqueued to Redis/RQ when `ENABLE_QUEUE=1`, processed by one or more `queue_worker.py` processes; falls back to synchronous in-process execution otherwise
  - `GET /api/v1/queue/status` reports queue connectivity/depth
- **Risk graph & predictive drift** (`prototype/risk.py`)
  - `GET /api/v1/risk/graph` builds an integration→resource risk graph (via `networkx`) weighted by drift severity/recency
  - `GET /api/v1/risk/predict` scores each integration's near-term drift risk from 7-day vs prior-7-day trend
- **AI remediation suggestions** (`prototype/ai.py`)
  - Calls a real OpenAI chat completion when `OPENAI_API_KEY` is set; falls back to a mock suggestion list otherwise
- **SSO / SCIM** (`prototype/sso.py`)
  - OIDC authorization-code login (`/api/v1/auth/sso/{tenant_id}/login|callback`) with live JWKS signature verification against the configured issuer
  - SCIM 2.0 user provisioning (`/scim/v2/Users`) authenticated with a per-tenant bearer token
- **Ticketing integrations** (`connectors/extra.py`, `POST /api/v1/remediations/{id}/ticket/auto`)
  - Creates a real Jira issue or ServiceNow incident via the tenant's configured integration; falls back to a mock ticket id if unconfigured/unreachable
- **Data residency & security hardening** (`prototype/residency.py`, `prototype/security.py`)
  - Resources/evidence tagged with the owning tenant's region at write time; `GET /api/v1/compliance/data-residency` reports the breakdown; requests declaring a mismatched `X-Region` are rejected with 403
  - Rate limiting (per-tenant/IP sliding window) and standard security response headers (HSTS, CSP, X-Frame-Options, etc.) applied to all `/api/*` requests
- **Drift engine** (`prototype/drift.py`)
  - Baseline-based drift detection for added/removed/changed resources
  - Severity assignment and acknowledgement flow support
- **Scheduler** (`prototype/scheduler.py`)
  - In-process APScheduler ticker for due sync/test execution
  - Stores `last_run_at`/`next_run_at` on integrations and tests
- **Analytics** (`prototype/analytics.py`)
  - Shared readiness/posture computation used by dashboard, scheduler, and analytics endpoints
- **RAG service** (`prototype/rag.py`)
  - Query classification, entity extraction, SQL-first retrieval, keyword trigram fallback
  - Context builder with citations and MockLLMProvider
  - Endpoints: `POST /api/v1/rag/query`, `POST /api/v1/rag/index/rebuild`, `POST /api/v1/rag/index/entity`, `GET /api/v1/rag/health`
- **Seed data and validation** (`data/*.json`, `scripts/validate_seed_data.py`, `scripts/generate_seed_data.py`)
- **Local test flows**
  - `podman/test.sh` (Podman PostgreSQL + Redis, schema load, seed, DB count assertions)
  - `docker-compose.yml` (Docker Compose Postgres + Redis + FastAPI)
  - `scripts/e2e_phase0_2.py` (Phase 0-4 end-to-end smoke test; filename retained for backward compatibility)
- **Unit tests** (`prototype/tests/`)
  - RAG, rule engine, and auth (mock mode + JWT)
- **Frontend** (`frontend/`)
  - React + Vite + Tailwind CSS SPA
  - Dashboard, integrations, controls, evidence, and policies views
  - Phase 3 Workflow & Audit portal view with remediations, access reviews, vendors, audits, and webhooks
  - Phase 4 Intelligence view with drift detection, evidence freshness, scheduler, analytics, and AI suggestions
  - Wired to FastAPI with CORS and Vite proxy

## Not yet implemented

- **Full-stack build prompt**: `prompts/build-prototype.md` still describes the original Node/Express/Prisma/React spec
- **SAML SSO**: only OIDC is implemented; SAML is not
- **Physical multi-region database partitioning**: data residency is currently enforced/tagged at the application layer against a single database, not a physically-partitioned regional cluster
- **Cross-resource joins**: `engine.py` evaluates one resource at a time
- **Trained ML risk model**: the risk graph/predictive scoring in `prototype/risk.py` is a deterministic statistical heuristic, not a trained model
- **Formal secrets manager integration**: `ENCRYPTION_KEY` is an env var; production should source it from KMS/Vault
- **Penetration testing / formal compliance audit / GA sign-off**

## Roadmap mapping

- **Phase 0** (Foundation): complete — schema, JWT token support, header and DB auth, RBAC, audit logging, OIDC SSO, SCIM provisioning, and credential encryption at rest are implemented
- **Phase 1** (MVP ingestion + SOC 2): complete — real AWS/Okta adapters, frontend, connector SDK, integration health, sync wiring, dashboards, and evidence collection are implemented
- **Phase 2** (Multi-framework + custom controls): largely complete — custom control creation, framework mapping lookup, policy management, acknowledgements, and manual evidence upload are implemented
- **Phase 3** (Workflows + audit portal): complete — remediation workflows, access review campaigns, vendor risk questionnaires, auditor portal with information requests, webhook subscriptions/deliveries, real Jira/ServiceNow ticketing, and frontend coverage are implemented
- **Phase 4** (Scale + intelligence): largely complete (prototype scope) — drift detection engine, evidence freshness monitoring, in-process scheduler + optional distributed Redis/RQ queue, posture history/trend analytics, 15-connector registry, risk graph/predictive drift, real LLM remediation suggestions, data-residency tagging/enforcement, rate limiting/security headers, and frontend Intelligence view are implemented
