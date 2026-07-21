# Vanta Technical Case Study

## Overview
Vanta is a continuous trust-management platform. It automates up to 90% of the work needed to prepare for and maintain security and privacy certifications such as SOC 2, ISO 27001, HIPAA, GDPR, PCI DSS, CIS, and NIST.

Public sources show that Vanta is API-first, multi-tenant, and organized around a Trust Graph: a continuously refreshed model of a customer's compliance posture built from hundreds of integrations and thousands of automated tests.

## Core Value Proposition
- Continuous evidence collection instead of point-in-time screenshots.
- Pre-built integrations with 350+ common business systems.
- Cross-framework mapping so one piece of evidence satisfies many controls.
- Automated tests run on hourly cadences.
- Auditor portals, access reviews, vendor risk, policy management, and AI-assisted workflows.

## Publicly Described Architecture

### Ingestion Layer
Vanta connects to systems using read-only APIs. It pulls metadata, not customer data, into a per-tenant data store. Examples:
- AWS: cross-account IAM role (`vanta-auditor`) with `SecurityAudit` and supplemental read-only policies.
- Okta: OAuth 2.0 private-key app with six read-only scopes (users, groups, apps, policies, roles, appGrants).
- GitHub: GitHub App with read-only repository and organization permissions.
- Google Workspace: service account with read-only admin SDK scopes.
- HRIS, MDM, vulnerability, and code scanning tools via partner APIs or the Build Integrations API.

Vanta separates ingestion into three API surfaces:
1. Build Integrations API: the only API that accepts inbound data from partners and private integrations.
2. Manage Vanta API: customer automation surface for controls, tests, personnel, vendors, documents.
3. Auditor API: read-only audit-firm surface for audits, information requests, and evidence review.

### Normalization & Trust Graph
Synced data is normalized into resource types such as `UserAccount`, `Computer`, `Vulnerability`, `TrainingRecord`, `BackgroundCheck`, and custom resources. These resources form the Trust Graph. AI features read from this graph instead of raw APIs.

### Controls, Tests, and Evidence
A test is an automated configuration check evaluated per resource. Each resource is tested against a declarative rule (for example, `mfaEnabled == true`). The per-resource results roll up into a test status (`OK`, `NEEDS_ATTENTION`, etc.) and feed every control the test maps to.

Vanta supports:
- Built-in tests, authored and versioned by Vanta, auto-created when an integration is connected.
- Custom tests, authored by customers against any synced resource type, with join support for up to two resource types.
- Custom controls and custom frameworks, imported via CSV and mapped to tests.

### Policy and Document Engine
Policies and documents are stored as versioned artifacts. Employees can acknowledge policies; Vanta records timestamps and audit logs. Document evidence is attached to relevant controls.

### Workflows and Remediation
Failed controls trigger workflows:
- Remediation tasks with owner assignment.
- Ticketing integrations (Jira, ServiceNow) to track fixes.
- Access review campaigns with automatic flagging of terminated or transferred employees.
- Notifications via Slack and email.
- Vanta AI Agent: agentic workflows for evidence collection, questionnaire responses, vendor review, and policy drafting.

### Scheduling and Drift Detection
Tests and integrations run on a schedule (hourly by default). Status flips automatically when new sync data arrives. Vanta detects drift by comparing current resource state against expected controls and alerting owners.

### Security & Authorization
Vanta publishes:
- Read-only scanner access, metadata-only collection, and per-account IAM roles with external IDs.
- A centralized authorization platform that supports broad organizational roles plus resource-level delegation.
- Audit logging, encryption at rest/in transit, SOC 2 / ISO 27001 / HIPAA / GDPR compliance, and data residency (US, EU, AU, Gov clouds).

### AI & Agentic Platform
Recent Vanta posts describe the Agentic Trust Platform powered by Vanta AI Agent 2.0:
- Context and memory across the customer's environment.
- Sandboxed tool use for file analysis and complex workflows.
- Traceability: every AI call, prompt, response, and tool invocation is logged.
- Public API and MCP server to let customers consume Vanta intelligence from their own tools.

## Scale
- 16,000+ companies use Vanta continuously.
- 350+ integrations, 30+ frameworks, hourly automated tests.
- Supports enterprise scoping across business units, geographies, and acquisitions.

## Sources
- https://www.vanta.com/resources/how-does-vanta-work
- https://www.vanta.com/resources/automated-evidence-collection-for-compliance-all-you-need-to-know
- https://www.vanta.com/resources/vanta-delivers-vanta-control-framework
- https://www.vanta.com/resources/powering-the-future-of-grc
- https://www.vanta.com/resources/how-we-built-authorization-as-a-platform-lessons-from-scaling-fine-grained-access-controls-at-vanta
- https://www.vanta.com/resources/trustcraft-how-we-build-ai-products-at-vanta
- https://www.vanta.com/resources/introducing-vantas-agentic-trust-platform
- https://www.vanta.com/resources/giving-the-vanta-agent-a-computer
- https://developer.vanta.com/docs/concepts/integrations
- https://developer.vanta.com/reference/build-integrations/overview
- https://developer.vanta.com/docs/concepts/tests
- https://github.com/VantaInc/vanta-control-set
- https://docs.cloudposse.com/components/library/aws/vanta/
