# Production-Grade Implementation Roadmap

This roadmap is now maintained as an execution-status document (not just an initial plan).

## Phase 0 - Design & Foundation
Status: **Complete**
- Common control model, mappings, tenant/user/RBAC schema, JWT flow, and audit logging are implemented.
- OIDC-based SSO login (`/api/v1/auth/sso/{tenant_id}/login|callback`) with live JWKS signature verification, and SCIM 2.0 user provisioning (`/scim/v2/Users`) are implemented (`prototype/sso.py`).
- Integration credentials are encrypted at rest with Fernet (`prototype/crypto.py`); `ENCRYPTION_KEY` should be set in production.
- Remaining for full production grade: SAML support, penetration testing, and formal secrets-manager integration (KMS/Vault) in place of the env-var key.

## Phase 1 - MVP Ingestion & One Framework
Status: **Complete**
- Connector SDK with AWS and Okta adapters is implemented (live API + graceful fallback).
- SOC 2-centric controls/tests/dashboard/evidence flow is operational.

## Phase 2 - Multi-Framework & Custom Controls
Status: **Largely complete**
- Multi-framework mappings, custom controls/tests, policy management, acknowledgements, and manual evidence upload are implemented.
- Remaining: deeper cross-resource logic and richer framework automation breadth.

## Phase 3 - Workflows & Audit Portal
Status: **Complete**
- Remediations, access reviews, vendor assessments, audit information requests, and webhook subscriptions/deliveries are implemented.
- Frontend workflows/audit portal view is implemented.
- Production ticketing integrations are implemented: `POST /api/v1/remediations/{id}/ticket/auto` creates a real Jira issue or ServiceNow incident via the tenant's configured integration (falls back to a mock ticket id if unconfigured/unreachable).

## Phase 4 - Scale & Intelligence
Status: **Largely complete (prototype scope)**
- Drift detection engine, evidence freshness/recollection endpoints, posture analytics history/trends, and scheduler endpoints are implemented.
- In-process scheduler (`APScheduler`) runs due integration syncs and tests; sync jobs can additionally be routed through a Redis/RQ distributed queue (`prototype/queue_backend.py`, `prototype/queue_worker.py`) when `ENABLE_QUEUE=1`.
- 15 connectors are implemented via a generic registry (`prototype/connectors/__init__.py`): AWS, Okta, GitHub, GitLab, Slack, Google Workspace, Microsoft 365/Azure AD, Jira, ServiceNow, PagerDuty, Datadog, Zoom, Salesforce, Snyk, Tenable.io — each makes a real API call when configured and falls back to mock data otherwise.
- Risk graph (`GET /api/v1/risk/graph`) and predictive drift scoring (`GET /api/v1/risk/predict`) are implemented in `prototype/risk.py` using `networkx` and drift-history-derived heuristics.
- Real LLM-backed remediation suggestions (`prototype/ai.py`) call OpenAI when `OPENAI_API_KEY` is set, with mock fallback.
- Data residency: resources/evidence are tagged with the owning tenant's region at write time, exposed via `GET /api/v1/compliance/data-residency`, and cross-region requests (`X-Region` header mismatch) are rejected at the gateway (`prototype/residency.py`). A full physically-partitioned multi-region database cluster remains future work.
- Security hardening: rate limiting and standard security response headers (`prototype/security.py`) are implemented.
- Intelligence frontend (drift/freshness/scheduler/analytics/AI suggestions) is implemented.

## Remaining for production-grade Phase 4
- Replicate/partition the database per region for true physical data residency (current implementation tags and enforces at the application layer against a single database).
- Expand risk graph to a trained/learned model rather than a statistical heuristic.
- Complete penetration testing, formal compliance audit, and GA readiness sign-off.

## Success Metrics
- Time to first SOC 2 readiness: < 4 weeks.
- Automated evidence collection: > 70% of controls.
- Mean time to detect drift: < 1 hour.
- Auditor evidence acceptance rate: > 95%.
