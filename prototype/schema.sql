-- Prototype DDL for a Vanta-like compliance automation platform
-- Target: PostgreSQL 15+

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Tenants and organizations
CREATE TABLE IF NOT EXISTS tenant (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text NOT NULL,
    region text NOT NULL DEFAULT 'us',
    created_at timestamp with time zone NOT NULL DEFAULT now(),
    updated_at timestamp with time zone NOT NULL DEFAULT now(),
    deleted_at timestamp with time zone
);

CREATE TABLE IF NOT EXISTS organization (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
    name text NOT NULL,
    created_at timestamp with time zone NOT NULL DEFAULT now()
);

-- Users and RBAC
CREATE TABLE IF NOT EXISTS "user" (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
    organization_id uuid REFERENCES organization(id) ON DELETE SET NULL,
    email text NOT NULL,
    full_name text,
    role text NOT NULL CHECK (role IN ('admin', 'compliance_manager', 'control_owner', 'auditor', 'read_only', 'external_auditor')),
    active boolean NOT NULL DEFAULT true,
    sso_id text,
    created_at timestamp with time zone NOT NULL DEFAULT now(),
    deleted_at timestamp with time zone
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_user_tenant_email ON "user"(tenant_id, email) WHERE deleted_at IS NULL;

-- Frameworks, sections, and controls
CREATE TABLE IF NOT EXISTS framework (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
    code text NOT NULL,
    name text NOT NULL,
    version text,
    active boolean NOT NULL DEFAULT true
);

CREATE TABLE IF NOT EXISTS section (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    framework_id uuid NOT NULL REFERENCES framework(id) ON DELETE CASCADE,
    code text NOT NULL,
    title text,
    description text
);

CREATE TABLE IF NOT EXISTS common_control (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
    code text NOT NULL,
    domain text NOT NULL,
    statement text NOT NULL,
    owner_id uuid REFERENCES "user"(id) ON DELETE SET NULL,
    expected_evidence text,
    active boolean NOT NULL DEFAULT true,
    created_at timestamp with time zone NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS framework_control (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
    framework_id uuid NOT NULL REFERENCES framework(id) ON DELETE CASCADE,
    section_id uuid REFERENCES section(id) ON DELETE SET NULL,
    common_control_id uuid NOT NULL REFERENCES common_control(id) ON DELETE CASCADE,
    requirement_text text NOT NULL
);

-- Tests and evidence
CREATE TABLE IF NOT EXISTS test (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
    name text NOT NULL,
    resource_type text NOT NULL,
    rule jsonb NOT NULL,
    schedule text NOT NULL DEFAULT '0 * * * *',
    active boolean NOT NULL DEFAULT true,
    created_at timestamp with time zone NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS control_test (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
    common_control_id uuid NOT NULL REFERENCES common_control(id) ON DELETE CASCADE,
    test_id uuid NOT NULL REFERENCES test(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS test_run (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
    test_id uuid NOT NULL REFERENCES test(id) ON DELETE CASCADE,
    status text NOT NULL CHECK (status IN ('running', 'completed', 'failed')),
    started_at timestamp with time zone NOT NULL DEFAULT now(),
    completed_at timestamp with time zone
);

CREATE TABLE IF NOT EXISTS resource_type (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
    name text NOT NULL,
    schema jsonb NOT NULL
);

CREATE TABLE IF NOT EXISTS integration (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
    connector text NOT NULL,
    name text NOT NULL,
    config jsonb NOT NULL DEFAULT '{}'::jsonb,
    credentials jsonb NOT NULL DEFAULT '{}'::jsonb,
    status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'connected', 'error', 'disabled')),
    last_sync_at timestamp with time zone,
    created_at timestamp with time zone NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS sync_job (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
    integration_id uuid NOT NULL REFERENCES integration(id) ON DELETE CASCADE,
    triggered_by uuid REFERENCES "user"(id) ON DELETE SET NULL,
    mode text NOT NULL DEFAULT 'manual' CHECK (mode IN ('manual', 'scheduled', 'webhook')),
    status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'running', 'completed', 'failed')),
    watermark text,
    error text,
    started_at timestamp with time zone,
    completed_at timestamp with time zone,
    created_at timestamp with time zone NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS resource (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
    integration_id uuid NOT NULL REFERENCES integration(id) ON DELETE CASCADE,
    resource_type_id uuid NOT NULL REFERENCES resource_type(id) ON DELETE CASCADE,
    external_id text NOT NULL,
    data jsonb NOT NULL,
    collected_at timestamp with time zone NOT NULL DEFAULT now(),
    hash text
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_resource_external ON resource(tenant_id, integration_id, external_id);

CREATE TABLE IF NOT EXISTS test_result (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
    test_run_id uuid NOT NULL REFERENCES test_run(id) ON DELETE CASCADE,
    resource_id uuid REFERENCES resource(id) ON DELETE SET NULL,
    status text NOT NULL CHECK (status IN ('OK', 'NEEDS_ATTENTION', 'INVALID', 'NOT_APPLICABLE', 'DEACTIVATED')),
    reason text,
    evaluated_at timestamp with time zone NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS evidence (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
    test_result_id uuid NOT NULL REFERENCES test_result(id) ON DELETE CASCADE,
    evidence_type text NOT NULL CHECK (evidence_type IN ('snapshot', 'document', 'screenshot', 'api_response')),
    storage_path text,
    description text,
    collected_at timestamp with time zone NOT NULL DEFAULT now(),
    expires_at timestamp with time zone
);

-- Policies, access reviews, vendors, audits
CREATE TABLE IF NOT EXISTS policy (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
    title text NOT NULL,
    content text,
    version text,
    owner_id uuid REFERENCES "user"(id) ON DELETE SET NULL,
    active boolean NOT NULL DEFAULT true
);

CREATE TABLE IF NOT EXISTS policy_ack (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
    policy_id uuid NOT NULL REFERENCES policy(id) ON DELETE CASCADE,
    user_id uuid NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
    acknowledged_at timestamp with time zone NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS access_review (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
    name text NOT NULL,
    due_date timestamp with time zone,
    status text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'completed', 'overdue'))
);

CREATE TABLE IF NOT EXISTS access_review_item (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
    access_review_id uuid NOT NULL REFERENCES access_review(id) ON DELETE CASCADE,
    user_id uuid REFERENCES "user"(id) ON DELETE SET NULL,
    system text,
    decision text CHECK (decision IN ('approved', 'revoked', 'pending')),
    notes text
);

CREATE TABLE IF NOT EXISTS vendor (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
    name text NOT NULL,
    category text,
    risk_level text CHECK (risk_level IN ('low', 'medium', 'high', 'critical'))
);

CREATE TABLE IF NOT EXISTS vendor_assessment (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
    vendor_id uuid NOT NULL REFERENCES vendor(id) ON DELETE CASCADE,
    status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'complete', 'expired')),
    completed_at timestamp with time zone
);

CREATE TABLE IF NOT EXISTS audit (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
    framework_id uuid NOT NULL REFERENCES framework(id) ON DELETE CASCADE,
    auditor_id uuid REFERENCES "user"(id) ON DELETE SET NULL,
    status text NOT NULL DEFAULT 'planning' CHECK (status IN ('planning', 'fieldwork', 'review', 'closed')),
    start_date timestamp with time zone,
    end_date timestamp with time zone
);

CREATE TABLE IF NOT EXISTS audit_request (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
    audit_id uuid NOT NULL REFERENCES audit(id) ON DELETE CASCADE,
    control_id uuid REFERENCES common_control(id) ON DELETE SET NULL,
    request_text text NOT NULL,
    status text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'responded', 'accepted', 'flagged')),
    created_at timestamp with time zone NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS audit_log (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
    actor_id uuid REFERENCES "user"(id) ON DELETE SET NULL,
    action text NOT NULL,
    resource_type text,
    resource_id uuid,
    metadata jsonb,
    created_at timestamp with time zone NOT NULL DEFAULT now()
);

-- Indexes for common access patterns
CREATE INDEX IF NOT EXISTS idx_resource_tenant_type ON resource(tenant_id, resource_type_id);
CREATE INDEX IF NOT EXISTS idx_test_result_run ON test_result(test_run_id);
CREATE INDEX IF NOT EXISTS idx_framework_control_common ON framework_control(common_control_id);
CREATE INDEX IF NOT EXISTS idx_control_test_test ON control_test(test_id);
CREATE INDEX IF NOT EXISTS idx_sync_job_status_created ON sync_job(status, created_at);

-- RAG support
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE IF NOT EXISTS rag_document (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
    entity_type text NOT NULL,
    entity_id uuid NOT NULL,
    source_type text NOT NULL DEFAULT 'TRUST_GRAPH',
    content text NOT NULL,
    content_hash text NOT NULL,
    version integer NOT NULL DEFAULT 1,
    created_at timestamp with time zone NOT NULL DEFAULT now(),
    updated_at timestamp with time zone NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, entity_type, entity_id)
);

CREATE INDEX IF NOT EXISTS idx_rag_document_tenant_entity ON rag_document(tenant_id, entity_type, entity_id);

CREATE TABLE IF NOT EXISTS rag_chunk (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
    rag_document_id uuid NOT NULL REFERENCES rag_document(id) ON DELETE CASCADE,
    chunk_index integer NOT NULL,
    content text NOT NULL,
    content_hash text NOT NULL,
    embedding jsonb,
    updated_at timestamp with time zone NOT NULL DEFAULT now(),
    UNIQUE (rag_document_id, chunk_index)
);

CREATE INDEX IF NOT EXISTS idx_rag_chunk_document ON rag_chunk(rag_document_id);
CREATE INDEX IF NOT EXISTS idx_rag_chunk_trgm ON rag_chunk USING gin (content gin_trgm_ops);

CREATE TABLE IF NOT EXISTS rag_query_log (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
    user_id uuid,
    query text NOT NULL,
    intent text,
    entities jsonb,
    latency_ms integer,
    answer_status text,
    created_at timestamp with time zone NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_rag_query_log_tenant_created ON rag_query_log(tenant_id, created_at);
