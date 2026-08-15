# Compliance Automation Prototype

A Vanta-like continuous compliance automation prototype. This repository contains a deep technical case study, framework mappings, system architecture, data model, control normalization, connector architecture, security and scalability designs, a production roadmap, and a detailed implementation prompt to build a working demo.

## What is included

| Directory | Purpose |
|---|---|
| `docs/` | Technical case study, framework mapping, architecture, data model, control normalization, connectors, scheduling, security, scalability, and roadmap |
| `architecture/` | Mermaid source files for end-to-end and data-model diagrams |
| `data/` | Seed JSON files: frameworks, common controls, mappings, resource types, sample resources, evidence, tenant, and integration catalog |
| `prototype/` | Starter database schema (`schema.sql`) and space for generated prototype code |
| `prompts/` | `build-prototype.md` - a self-contained prompt to generate a full-stack demo |
| `scripts/` | `generate_seed_data.py` - regenerates the JSON seed data |

## Quick start

1. Read `docs/01-case-study.md` for the Vanta technical case study.
2. Read `docs/03-architecture.md` and `architecture/end-to-end.mmd` for the system design.
3. Review `prototype/schema.sql` for the database DDL.
4. Inspect `data/*.json` for sample frameworks, controls, resources, and evidence.
5. Use `prompts/build-prototype.md` as the implementation prompt for an AI coding assistant or engineering team to build the demo in `prototype/`.

## Regenerate seed data

```bash
python3 scripts/generate_seed_data.py
```

Optional root override (useful in CI or non-standard checkouts):

```bash
COMPLIANCE_PROTOTYPE_ROOT=$(pwd) python3 scripts/generate_seed_data.py
```

## Dry-run validation

Run a logical validation pass across all seed JSON files without starting services:

```bash
python3 scripts/validate_seed_data.py
```

Fail on warnings as well:

```bash
python3 scripts/validate_seed_data.py --strict-warnings
```

## Tech stack recommendation

- Backend: Node.js 20 + Express + TypeScript + Prisma
- Database: PostgreSQL 15
- Queue/Cache: Redis + BullMQ
- Frontend: React 18 + Vite + TailwindCSS + Recharts
- Connector worker: Python 3.11
- Infrastructure: Docker Compose

## Public sources used

Public Vanta engineering blogs, developer docs, integration guides, and the open Vanta control set informed this design. URLs are listed in `docs/01-case-study.md`.

