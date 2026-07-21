# Data Model and Entity Relationships

## Core Entities

```mermaid
erDiagram
    TENANT ||--o{ ORGANIZATION : has
    ORGANIZATION ||--o{ USER : contains
    ORGANIZATION ||--o{ FRAMEWORK : subscribes
    FRAMEWORK ||--|{ SECTION : contains
    SECTION ||--o{ FRAMEWORK_CONTROL : defines
    COMMON_CONTROL ||--o{ FRAMEWORK_CONTROL : maps_to
    COMMON_CONTROL ||--o{ CONTROL_TEST : validated_by
    TEST ||--o{ CONTROL_TEST : assigned
    TEST ||--o{ TEST_RUN : produces
    TEST_RUN ||--|{ TEST_RESULT : has
    TEST_RESULT ||--o{ EVIDENCE : supports
    INTEGRATION ||--o{ CONNECTOR : uses
    CONNECTOR ||--o{ SYNC_JOB : runs
    SYNC_JOB ||--o{ RESOURCE : ingests
    RESOURCE }o--|| RESOURCE_TYPE : typed
    RESOURCE ||--o{ TEST_RESULT : evaluated
    POLICY ||--o{ POLICY_ACK : acknowledged
    ACCESS_REVIEW ||--o{ ACCESS_REVIEW_ITEM : includes
    VENDOR ||--o{ VENDOR_ASSESSMENT : has
    AUDIT ||--o{ AUDIT_REQUEST : contains
    AUDIT_REQUEST ||--o{ AUDIT_EVIDENCE : references
```

## Table Descriptions

- `tenant`: top-level account. Isolates all data.
- `organization`: business unit or subsidiary within a tenant.
- `user`: employees, admins, auditors, owners.
- `role` and `permission`: RBAC definitions.
- `framework`: SOC 2, ISO 27001, HIPAA, GDPR, etc.
- `section`: framework clause (e.g., SOC 2 CC6.1).
- `common_control`: normalized control statement and domain.
- `framework_control`: framework-specific requirement and mapping to common controls.
- `control_test`: join table linking controls to tests.
- `test`: automated or manual test definition, rule, schedule.
- `test_run`: scheduled or ad-hoc execution snapshot.
- `test_result`: per-resource pass/fail and reason.
- `evidence`: artifact, snapshot, or document attached to a result.
- `integration`: connected system with credentials and settings.
- `connector`: type definition and schema for a source system.
- `sync_job`: scheduled or triggered ingestion job.
- `resource`: normalized record from an integration.
- `resource_type`: canonical schema for resources.
- `policy`: policy document version.
- `policy_ack`: employee acknowledgement record.
- `access_review` / `access_review_item`: access review campaigns and per-user/per-system decisions.
- `vendor` / `vendor_assessment`: third-party vendor and security questionnaire.
- `audit` / `audit_request` / `audit_evidence`: auditor engagement and information request workflow.

## Key Conventions
- Every table has `tenant_id` for row-level isolation.
- All timestamp fields use UTC.
- `external_id` stores the source-system identifier.
- Soft deletes preserve audit history.
- Evidence snapshots are immutable once written for a test run.

See `architecture/data-model.mmd` for the Mermaid source and `prototype/schema.sql` for a DDL starter.
