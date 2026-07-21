# Implementation Prompt: Build a Working Compliance Automation Prototype

## Context
You are building a demo-ready compliance automation prototype similar to Vanta. The design docs and seed data are in this repository. Read them before writing code.

## Reference files
- docs/01-case-study.md
- docs/03-architecture.md
- docs/04-data-model.md
- docs/05-control-normalization.md
- docs/06-connector-architecture.md
- prototype/schema.sql
- data/*.json
- architecture/*.mmd

## Objective
Produce a runnable full-stack prototype in the `prototype/` directory. The demo must show tenant onboarding, AWS and Okta connectors, SOC 2 and ISO 27001 controls, automated tests, evidence collection, dashboards, and an auditor portal.

## Tech Stack
- Backend: Node.js 20 + Express + TypeScript
- ORM: Prisma
- Database: PostgreSQL 15
- Queue: Redis + BullMQ
- Frontend: React 18 + Vite + TailwindCSS + Recharts
- Connector worker: Python 3.11 with FastAPI or simple CLI scripts
- Infrastructure: Docker Compose

## Step 1 - Database
1. Use `prototype/schema.sql` as the starting DDL. Run it against PostgreSQL.
2. Generate a Prisma schema from the tables.
3. Create a seed script that loads `data/*.json` into the database using the Prisma client.
4. Ensure `tenant_id` is applied as a filter on every query.

## Step 2 - Backend API
Implement these endpoints under `/api/v1`:
- `POST /tenants` - create tenant
- `GET /tenants/:id/readiness` - aggregate framework readiness
- `POST /integrations` - connect a system (AWS, Okta, GitHub)
- `POST /integrations/:id/sync` - trigger a sync job
- `GET /resources` - list normalized resources with filters
- `GET /controls` - list common controls with status
- `GET /controls/:id/status` - control detail with evidence
- `POST /tests` - create a custom test
- `POST /tests/:id/run` - run a test now
- `GET /evidence` - list evidence
- `GET /dashboards/posture` - posture summary
- `GET /audits` - list audits
- `GET /audits/:id/requests` - auditor information requests
- `POST /audits/:id/requests` - create a request

Use JWT auth with role checks. Include middleware to enforce tenant isolation.

## Step 3 - Rule Engine
Build a rule engine that:
- Accepts a declarative rule JSON like `{field: 'mfa_enabled', operator: 'eq', value: true}`.
- Evaluates each resource of the rule's resource type.
- Supports `and`, `or`, `in`, `gt`, `lt`, `exists` operators.
- Supports joins across two resource types using a correlation key (e.g., `email` == `user_email`).
- Produces per-resource `OK` or `NEEDS_ATTENTION` with a reason.
- Rolls up results to a control status.

## Step 4 - Connector Worker
Create a Python worker or async job that:
- Reads integration configs from the queue.
- Has mock adapters for AWS and Okta that return sample resources from `data/sample-resources.json`.
- Has a real adapter skeleton that calls the actual provider API when credentials are present.
- Normalizes output into the canonical `resource` schema.
- Writes resources to PostgreSQL and triggers the rule engine.
- Updates `integration.last_sync_at` and status.

## Step 5 - Frontend
Build a React SPA with these pages:
- `/login` - username/password or mock SSO.
- `/dashboard` - overall posture, framework readiness donut chart, open failures.
- `/frameworks` - framework list and section coverage.
- `/controls` - control grid with status, owner, and evidence links.
- `/control/:id` - control detail, test history, evidence.
- `/integrations` - connect and manage integrations.
- `/resources` - browse normalized resources.
- `/audits` - auditor portal (read-only) with information requests.
- `/access-reviews` - list and complete access review items.
- `/policies` - policy list and acknowledgement tracking.

Use Recharts for charts and Tailwind for styling. Make it demo-friendly with sample data.

## Step 6 - Scheduling and Drift
- Use BullMQ to schedule connector syncs every hour.
- Run tests automatically after a sync completes.
- Compute evidence freshness in the dashboard.
- Highlight drift when a resource changes from OK to NEEDS_ATTENTION.

## Step 7 - Security
- Hash passwords with bcrypt or use mock SSO.
- Enforce role checks on every route.
- Encrypt integration credentials with a KMS key or environment secret.
- Log every mutation to `audit_log`.
- Never store plaintext secrets in the repository.

## Step 8 - Docker Compose
Provide a `docker-compose.yml` that starts:
- postgres
- redis
- api (Node backend)
- worker (Python connector worker)
- web (React dev server)

Expose ports `3000` for API and `5173` for web. Use environment variables for DB and Redis URLs.

## Acceptance Criteria
1. `docker compose up` starts all services.
2. Seed data loads on first start.
3. Dashboard shows at least three frameworks with readiness percentages.
4. Controls page lists at least 12 controls and shows pass/fail status.
5. AWS and Okta integrations can be connected (mock or real).
6. Sync job produces resources and test results.
7. Evidence pages show snapshot or API response descriptions.
8. Auditor portal is read-only and supports information requests.
9. Access review page allows approve/revoke decisions.
10. All endpoints are tenant-isolated and role-protected.
