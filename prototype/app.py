import asyncio
import json
import os
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, status

from auth import TenantContext, get_tenant_context, issue_token, require_admin_role
from connectors import (
    AWSConnector,
    AWSCredentials,
    OktaConnector,
    OktaCredentials,
)
from db import db
from engine import evaluate_rule
from models import (
    AuditRequestCreate,
    AuditRequestOut,
    ControlStatus,
    EvidenceOut,
    FrameworkReadiness,
    IntegrationCreate,
    IntegrationOut,
    PostureSummary,
    TestCreate,
    TestRunSummary,
)
from worker import SyncWorker, run_test
from rag import RAGQuery, RAGResponse, RAGIndexRequest, rag as rag_service

app = FastAPI(title="Compliance Automation Prototype", version="0.1.0")
worker = SyncWorker(db)

AUDITABLE_METHODS = {"POST", "PUT", "DELETE", "PATCH"}


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
        return True
    except ValueError:
        return False


def _audit_resource_type(path: str) -> str:
    parts = [p for p in path.split("/") if p and not p.startswith("api")]
    for p in parts:
        if p.startswith("v"):
            continue
        return p
    return parts[-1] if parts else "unknown"


def _audit_resource_id(request: Request) -> str | None:
    for key in ("id", "integration_id", "test_id", "control_id", "audit_id", "tenant_id"):
        value = request.path_params.get(key)
        if value:
            return value
    return None


def _log_audit(
    tenant_id: str,
    actor_id: str | None,
    action: str,
    resource_type: str,
    resource_id: str | None,
    details: str,
) -> None:
    try:
        if db._pool is None:
            return
        if not tenant_id or not _is_uuid(tenant_id):
            return
        if not db.fetchone("SELECT id FROM tenant WHERE id = %s", (tenant_id,)):
            return
        if actor_id and _is_uuid(actor_id):
            if not db.fetchone('SELECT id FROM "user" WHERE id = %s', (actor_id,)):
                actor_id = None
        else:
            actor_id = None
        db.execute(
            """INSERT INTO audit_log (id, tenant_id, actor_id, action, resource_type, resource_id, metadata, created_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s)""",
            (
                str(uuid.uuid4()),
                tenant_id,
                actor_id,
                action,
                resource_type,
                resource_id if resource_id and _is_uuid(resource_id) else None,
                details,
                _now(),
            ),
        )
    except Exception:
        pass


@app.middleware("http")
async def audit_log_middleware(request: Request, call_next):
    response = await call_next(request)
    if request.method not in AUDITABLE_METHODS or db._pool is None:
        return response
    tenant_id = request.headers.get("X-Tenant-Id") or request.path_params.get("tenant_id")
    actor_id = request.headers.get("X-User-Id")
    resource_type = _audit_resource_type(request.url.path)
    resource_id = _audit_resource_id(request)
    details = json.dumps({
        "method": request.method,
        "path": request.url.path,
        "status_code": response.status_code,
        "path_params": dict(request.path_params),
    })
    await asyncio.to_thread(_log_audit, tenant_id, actor_id, request.method, resource_type, resource_id, details)
    return response


@app.on_event("startup")
def startup() -> None:
    db.configure()
    schema_path = Path(__file__).resolve().parent / "schema.sql"
    db.init_schema(str(schema_path))


@app.on_event("shutdown")
def shutdown() -> None:
    if db._pool:
        db._pool.closeall()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_uuid(value: str) -> str:
    try:
        return str(uuid.UUID(value))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid UUID: {value}") from exc


# ---------------------------------------------------------------------------
# Tenant / posture
# ---------------------------------------------------------------------------


@app.post("/api/v1/tenants")
def create_tenant(
    name: str,
    region: str = "us",
    _: None = Depends(require_admin_role),
):
    tenant_id = str(uuid.uuid4())
    db.execute(
        "INSERT INTO tenant (id, name, region) VALUES (%s, %s, %s)",
        (tenant_id, name, region),
    )
    return {"id": tenant_id, "name": name, "region": region}


@app.post("/api/v1/auth/token")
def auth_token(
    tenant_id: str,
    user_id: str,
    role: str = Query(default="read_only"),
):
    return {"token": issue_token(tenant_id, user_id, role)}


@app.get("/api/v1/tenants/{tenant_id}/readiness", response_model=PostureSummary)
def tenant_readiness(
    tenant_id: str,
    ctx: TenantContext = Depends(get_tenant_context),
):
    ctx.require_role("admin", "compliance_manager", "control_owner", "auditor", "read_only")
    return _compute_posture(tenant_id)


# ---------------------------------------------------------------------------
# Integrations
# ---------------------------------------------------------------------------


@app.post("/api/v1/integrations", response_model=IntegrationOut)
def create_integration(
    payload: IntegrationCreate,
    ctx: TenantContext = Depends(get_tenant_context),
):
    ctx.require_role("admin", "compliance_manager")
    integration_id = str(uuid.uuid4())
    db.execute(
        """INSERT INTO integration (id, tenant_id, connector, name, config, credentials, status)
           VALUES (%s, %s, %s, %s, %s, %s, %s)""",
        (integration_id, ctx.tenant_id, payload.connector, payload.name,
         json.dumps(payload.config), json.dumps(payload.credentials), "pending"),
    )
    return _integration_row(integration_id, ctx.tenant_id)


@app.get("/api/v1/integrations")
def list_integrations(
    ctx: TenantContext = Depends(get_tenant_context),
    status_filter: str | None = Query(default=None, alias="status"),
):
    ctx.require_role("admin", "compliance_manager", "control_owner", "auditor", "read_only")
    sql = "SELECT * FROM integration WHERE tenant_id = %s"
    params: list[Any] = [ctx.tenant_id]
    if status_filter:
        sql += " AND status = %s"
        params.append(status_filter)
    return db.execute(sql, tuple(params))


@app.post("/api/v1/integrations/{integration_id}/sync")
def sync_integration(
    integration_id: str,
    ctx: TenantContext = Depends(get_tenant_context),
):
    ctx.require_role("admin", "compliance_manager", "control_owner")
    integration = _get_integration(integration_id, ctx.tenant_id)
    job_id = worker.sync_integration(integration, triggered_by=ctx.user_id)
    return {"sync_job_id": job_id}


def _connector_credentials(integration: dict[str, Any]) -> tuple[AWSConnector | OktaConnector, str]:
    connector = integration["connector"].lower()
    credentials = integration.get("credentials") or {}
    if connector == "aws":
        creds = AWSCredentials(
            access_key_id=credentials.get("access_key_id"),
            secret_access_key=credentials.get("secret_access_key"),
            region=credentials.get("region"),
        )
        return AWSConnector(creds), "aws"
    elif connector == "okta":
        creds = OktaCredentials(
            api_token=credentials.get("api_token"),
            base_url=credentials.get("base_url"),
        )
        return OktaConnector(creds), "okta"
    return None, connector


@app.get("/api/v1/integrations/{integration_id}", response_model=IntegrationOut)
def get_integration(
    integration_id: str,
    ctx: TenantContext = Depends(get_tenant_context),
):
    ctx.require_role("admin", "compliance_manager", "control_owner", "auditor", "read_only")
    return _integration_row(integration_id, ctx.tenant_id)


@app.get("/api/v1/integrations/{integration_id}/health")
def integration_health(
    integration_id: str,
    ctx: TenantContext = Depends(get_tenant_context),
):
    ctx.require_role("admin", "compliance_manager", "control_owner")
    integration = _get_integration(integration_id, ctx.tenant_id)
    connector, name = _connector_credentials(integration)
    if connector is None:
        result = {"configured": False, "reason": "Unknown connector"}
    else:
        result = connector.health_check()
    return {"integration_id": integration_id, "connector": name, **result}


@app.post("/api/v1/integrations/{integration_id}/test")
def test_integration(
    integration_id: str,
    ctx: TenantContext = Depends(get_tenant_context),
):
    ctx.require_role("admin", "compliance_manager")
    integration = _get_integration(integration_id, ctx.tenant_id)
    connector, name = _connector_credentials(integration)
    if connector is None:
        db.execute(
            "UPDATE integration SET status = 'error' WHERE id = %s",
            (_parse_uuid(integration_id),),
        )
        return {
            "integration_id": integration_id,
            "connector": name,
            "configured": False,
            "reason": "Unknown connector",
            "tested_at": _now(),
        }
    health = connector.health_check()
    if not health.get("configured"):
        db.execute(
            "UPDATE integration SET status = 'error' WHERE id = %s",
            (_parse_uuid(integration_id),),
        )
        return {"integration_id": integration_id, "connector": name, **health, "tested_at": _now()}
    db.execute(
        "UPDATE integration SET status = 'connected' WHERE id = %s",
        (_parse_uuid(integration_id),),
    )
    return {"integration_id": integration_id, "connector": name, **health, "tested_at": _now()}


@app.get("/api/v1/integrations/{integration_id}/sync-jobs")
def list_integration_sync_jobs(
    integration_id: str,
    ctx: TenantContext = Depends(get_tenant_context),
):
    ctx.require_role("admin", "compliance_manager", "control_owner", "auditor", "read_only")
    _get_integration(integration_id, ctx.tenant_id)
    return db.execute(
        "SELECT * FROM sync_job WHERE tenant_id = %s AND integration_id = %s ORDER BY started_at DESC",
        (ctx.tenant_id, _parse_uuid(integration_id)),
    )


@app.get("/api/v1/sync-jobs/{job_id}")
def get_sync_job(
    job_id: str,
    ctx: TenantContext = Depends(get_tenant_context),
):
    ctx.require_role("admin", "compliance_manager", "control_owner", "auditor", "read_only")
    row = db.fetchone(
        """SELECT sj.*, i.connector
           FROM sync_job sj
           JOIN integration i ON i.id = sj.integration_id
           WHERE sj.id = %s AND sj.tenant_id = %s""",
        (_parse_uuid(job_id), ctx.tenant_id),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Sync job not found")
    return row


# ---------------------------------------------------------------------------
# Resources
# ---------------------------------------------------------------------------


@app.get("/api/v1/resources")
def list_resources(
    ctx: TenantContext = Depends(get_tenant_context),
    resource_type: str | None = Query(default=None),
    integration_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
):
    ctx.require_role("admin", "compliance_manager", "control_owner", "auditor", "read_only")
    sql = """SELECT r.*, rt.name as resource_type_name
             FROM resource r
             JOIN resource_type rt ON rt.id = r.resource_type_id
             WHERE r.tenant_id = %s"""
    params: list[Any] = [ctx.tenant_id]
    if resource_type:
        sql += " AND rt.name = %s"
        params.append(resource_type)
    if integration_id:
        sql += " AND r.integration_id = %s"
        params.append(_parse_uuid(integration_id))
    sql += " ORDER BY r.collected_at DESC"
    return db.execute(sql, tuple(params))


# ---------------------------------------------------------------------------
# Controls
# ---------------------------------------------------------------------------


@app.get("/api/v1/controls")
def list_controls(
    ctx: TenantContext = Depends(get_tenant_context),
    framework_code: str | None = Query(default=None),
):
    ctx.require_role("admin", "compliance_manager", "control_owner", "auditor", "read_only")
    controls = _list_common_controls(ctx.tenant_id, framework_code)
    return [_hydrate_control_status(c, ctx.tenant_id) for c in controls]


@app.get("/api/v1/controls/{control_id}/status")
def control_status(
    control_id: str,
    ctx: TenantContext = Depends(get_tenant_context),
):
    ctx.require_role("admin", "compliance_manager", "control_owner", "auditor", "read_only")
    control = _get_common_control(control_id, ctx.tenant_id)
    return _control_detail(control, ctx.tenant_id)


@app.post("/api/v1/controls")
def create_control(
    code: str,
    statement: str,
    domain: str = Query(default="uncategorized"),
    owner_email: str | None = Query(default=None),
    framework_code: str | None = Query(default=None),
    section_code: str | None = Query(default=None),
    requirement_text: str = Query(default=""),
    ctx: TenantContext = Depends(get_tenant_context),
):
    ctx.require_role("admin", "compliance_manager")
    owner_id = None
    if owner_email:
        user = db.fetchone(
            'SELECT id FROM "user" WHERE tenant_id = %s AND email = %s',
            (ctx.tenant_id, owner_email),
        )
        owner_id = user["id"] if user else None
    control_id = str(uuid.uuid4())
    db.execute(
        """INSERT INTO common_control (id, tenant_id, code, domain, statement, owner_id)
           VALUES (%s, %s, %s, %s, %s, %s)""",
        (control_id, ctx.tenant_id, code, domain, statement, owner_id),
    )
    if framework_code and requirement_text:
        framework = db.fetchone(
            "SELECT id FROM framework WHERE tenant_id = %s AND code = %s",
            (ctx.tenant_id, framework_code),
        )
        if framework:
            section_id = None
            if section_code:
                section = db.fetchone(
                    "SELECT id FROM section WHERE framework_id = %s AND code = %s",
                    (framework["id"], section_code),
                )
                section_id = section["id"] if section else None
            db.execute(
                """INSERT INTO framework_control (id, tenant_id, framework_id, section_id, common_control_id, requirement_text)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (str(uuid.uuid4()), ctx.tenant_id, framework["id"], section_id, control_id, requirement_text),
            )
    return _get_common_control(control_id, ctx.tenant_id)


@app.get("/api/v1/controls/{control_id}/frameworks")
def control_frameworks(
    control_id: str,
    ctx: TenantContext = Depends(get_tenant_context),
):
    ctx.require_role("admin", "compliance_manager", "control_owner", "auditor", "read_only", "external_auditor")
    _get_common_control(control_id, ctx.tenant_id)
    return db.execute(
        """SELECT f.id, f.code, f.name, fc.requirement_text, s.code as section_code, s.title as section_title
           FROM framework_control fc
           JOIN framework f ON f.id = fc.framework_id
           LEFT JOIN section s ON s.id = fc.section_id
           WHERE fc.common_control_id = %s AND fc.tenant_id = %s""",
        (_parse_uuid(control_id), ctx.tenant_id),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@app.post("/api/v1/tests")
def create_test(
    payload: TestCreate,
    ctx: TenantContext = Depends(get_tenant_context),
):
    ctx.require_role("admin", "compliance_manager", "control_owner")
    test_id = str(uuid.uuid4())
    db.execute(
        """INSERT INTO test (id, tenant_id, name, resource_type, rule, schedule)
           VALUES (%s, %s, %s, %s, %s, %s)""",
        (test_id, ctx.tenant_id, payload.name, payload.resource_type,
         json.dumps(payload.rule), payload.schedule),
    )
    for cc_id in payload.common_control_ids:
        db.execute(
            "INSERT INTO control_test (id, tenant_id, common_control_id, test_id) VALUES (%s, %s, %s, %s)",
            (str(uuid.uuid4()), ctx.tenant_id, _parse_uuid(cc_id), test_id),
        )
    return {"id": test_id, "name": payload.name, "resource_type": payload.resource_type}


@app.post("/api/v1/tests/{test_id}/run", response_model=TestRunSummary)
def run_test_endpoint(
    test_id: str,
    ctx: TenantContext = Depends(get_tenant_context),
):
    ctx.require_role("admin", "compliance_manager", "control_owner")
    test = _get_test(test_id, ctx.tenant_id)
    return run_test(db, test)


# ---------------------------------------------------------------------------
# Evidence
# ---------------------------------------------------------------------------


@app.get("/api/v1/evidence", response_model=list[EvidenceOut])
def list_evidence(
    ctx: TenantContext = Depends(get_tenant_context),
    resource_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
):
    ctx.require_role("admin", "compliance_manager", "control_owner", "auditor", "read_only")
    sql = """SELECT e.id, t.name as test_name, r.external_id as resource_external_id,
                    tr.status, e.evidence_type, e.description, e.collected_at, e.expires_at
             FROM evidence e
             JOIN test_result tr ON tr.id = e.test_result_id
             JOIN test_run trun ON trun.id = tr.test_run_id
             JOIN test t ON t.id = trun.test_id
             LEFT JOIN resource r ON r.id = tr.resource_id
             WHERE e.tenant_id = %s"""
    params: list[Any] = [ctx.tenant_id]
    if resource_id:
        sql += " AND tr.resource_id = %s"
        params.append(_parse_uuid(resource_id))
    if status:
        sql += " AND tr.status = %s"
        params.append(status)
    sql += " ORDER BY e.collected_at DESC"
    rows = db.execute(sql, tuple(params))
    return [EvidenceOut(**r) for r in rows]


@app.post("/api/v1/evidence")
def create_evidence(
    test_result_id: str,
    evidence_type: str = Query(default="document"),
    description: str | None = Query(default=None),
    storage_path: str | None = Query(default=None),
    ctx: TenantContext = Depends(get_tenant_context),
):
    ctx.require_role("admin", "compliance_manager", "control_owner")
    # Manual evidence can be attached to an existing test result for now
    tr = db.fetchone(
        "SELECT id FROM test_result WHERE id = %s AND tenant_id = %s",
        (_parse_uuid(test_result_id), ctx.tenant_id),
    )
    if not tr:
        raise HTTPException(status_code=404, detail="Test result not found")
    evidence_id = str(uuid.uuid4())
    db.execute(
        """INSERT INTO evidence (id, tenant_id, test_result_id, evidence_type, storage_path, description, expires_at)
           VALUES (%s, %s, %s, %s, %s, %s, %s)""",
        (evidence_id, ctx.tenant_id, test_result_id, evidence_type, storage_path, description, _now()),
    )
    return db.fetchone("SELECT * FROM evidence WHERE id = %s", (evidence_id,))


@app.get("/api/v1/evidence/{evidence_id}")
def get_evidence(
    evidence_id: str,
    ctx: TenantContext = Depends(get_tenant_context),
):
    ctx.require_role("admin", "compliance_manager", "control_owner", "auditor", "read_only")
    row = db.fetchone(
        """SELECT e.*, t.name as test_name, r.external_id as resource_external_id,
                  tr.status
           FROM evidence e
           JOIN test_result tr ON tr.id = e.test_result_id
           JOIN test_run trun ON trun.id = tr.test_run_id
           JOIN test t ON t.id = trun.test_id
           LEFT JOIN resource r ON r.id = tr.resource_id
           WHERE e.id = %s AND e.tenant_id = %s""",
        (_parse_uuid(evidence_id), ctx.tenant_id),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Evidence not found")
    return row


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


@app.get("/api/v1/dashboards/posture", response_model=PostureSummary)
def dashboard_posture(
    ctx: TenantContext = Depends(get_tenant_context),
):
    ctx.require_role("admin", "compliance_manager", "control_owner", "auditor", "read_only")
    return _compute_posture(ctx.tenant_id)


@app.get("/api/v1/dashboards/failures")
def dashboard_failures(
    ctx: TenantContext = Depends(get_tenant_context),
):
    ctx.require_role("admin", "compliance_manager", "control_owner", "auditor", "read_only", "external_auditor")
    rows = db.execute(
        """SELECT cc.id AS control_id,
                  cc.code AS control_code,
                  cc.statement,
                  r.external_id AS resource_external_id,
                  tr.status,
                  tr.reason,
                  tr.evaluated_at
           FROM test_result tr
           JOIN test_run trun ON trun.id = tr.test_run_id
           JOIN control_test ct ON ct.test_id = trun.test_id AND ct.tenant_id = tr.tenant_id
           JOIN common_control cc ON cc.id = ct.common_control_id AND cc.tenant_id = tr.tenant_id
           LEFT JOIN resource r ON r.id = tr.resource_id
           WHERE tr.tenant_id = %s
             AND tr.status = 'NEEDS_ATTENTION'
             AND trun.completed_at = (SELECT MAX(completed_at)
                                      FROM test_run trun2
                                      WHERE trun2.test_id = trun.test_id
                                        AND trun2.tenant_id = tr.tenant_id)
           ORDER BY tr.evaluated_at DESC""",
        (ctx.tenant_id,),
    )
    return {"tenant_id": ctx.tenant_id, "failing_results": rows}


# ---------------------------------------------------------------------------
# Audits
# ---------------------------------------------------------------------------


@app.get("/api/v1/audits")
def list_audits(
    ctx: TenantContext = Depends(get_tenant_context),
):
    ctx.require_role("admin", "compliance_manager", "auditor", "external_auditor")
    return db.execute(
        """SELECT a.*, f.code as framework_code, f.name as framework_name
           FROM audit a
           JOIN framework f ON f.id = a.framework_id
           WHERE a.tenant_id = %s
           ORDER BY a.created_at DESC""",
        (ctx.tenant_id,),
    )


@app.get("/api/v1/audits/{audit_id}/requests", response_model=list[AuditRequestOut])
def list_audit_requests(
    audit_id: str,
    ctx: TenantContext = Depends(get_tenant_context),
):
    ctx.require_role("admin", "compliance_manager", "auditor", "external_auditor")
    _get_audit(audit_id, ctx.tenant_id)
    rows = db.execute(
        """SELECT ar.*, cc.code as control_code
           FROM audit_request ar
           LEFT JOIN common_control cc ON cc.id = ar.control_id
           WHERE ar.tenant_id = %s AND ar.audit_id = %s
           ORDER BY ar.created_at DESC""",
        (ctx.tenant_id, _parse_uuid(audit_id)),
    )
    return [AuditRequestOut(**r) for r in rows]


@app.post("/api/v1/audits/{audit_id}/requests", response_model=AuditRequestOut)
def create_audit_request(
    audit_id: str,
    payload: AuditRequestCreate,
    ctx: TenantContext = Depends(get_tenant_context),
):
    ctx.require_role("admin", "compliance_manager", "auditor")
    _get_audit(audit_id, ctx.tenant_id)
    request_id = str(uuid.uuid4())
    db.execute(
        """INSERT INTO audit_request (id, tenant_id, audit_id, control_id, request_text, status)
           VALUES (%s, %s, %s, %s, %s, %s)""",
        (request_id, ctx.tenant_id, _parse_uuid(audit_id),
         _parse_uuid(payload.control_id) if payload.control_id else None,
         payload.request_text, "open"),
    )
    return _get_audit_request(request_id)


# ---------------------------------------------------------------------------
# Policies
# ---------------------------------------------------------------------------


@app.get("/api/v1/policies")
def list_policies(
    ctx: TenantContext = Depends(get_tenant_context),
):
    ctx.require_role("admin", "compliance_manager", "control_owner", "auditor", "read_only")
    return db.execute(
        "SELECT * FROM policy WHERE tenant_id = %s AND active = true ORDER BY id DESC",
        (ctx.tenant_id,),
    )


@app.post("/api/v1/policies")
def create_policy(
    title: str,
    content: str | None = Query(default=None),
    version: str | None = Query(default="1.0"),
    ctx: TenantContext = Depends(get_tenant_context),
):
    ctx.require_role("admin", "compliance_manager")
    policy_id = str(uuid.uuid4())
    db.execute(
        """INSERT INTO policy (id, tenant_id, title, content, version)
           VALUES (%s, %s, %s, %s, %s)""",
        (policy_id, ctx.tenant_id, title, content, version),
    )
    return db.fetchone("SELECT * FROM policy WHERE id = %s", (policy_id,))


@app.post("/api/v1/policies/{policy_id}/acknowledge")
def acknowledge_policy(
    policy_id: str,
    ctx: TenantContext = Depends(get_tenant_context),
):
    ctx.require_role("admin", "compliance_manager", "control_owner", "auditor", "read_only")
    if not ctx.user_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing user id")
    ack_id = str(uuid.uuid4())
    db.execute(
        """INSERT INTO policy_ack (id, tenant_id, policy_id, user_id)
           VALUES (%s, %s, %s, %s)""",
        (ack_id, ctx.tenant_id, _parse_uuid(policy_id), ctx.user_id),
    )
    return {"acknowledgement_id": ack_id, "policy_id": policy_id, "user_id": ctx.user_id}


# ---------------------------------------------------------------------------
# RAG
# ---------------------------------------------------------------------------


@app.post("/api/v1/rag/query", response_model=RAGResponse)
def rag_query(
    payload: RAGQuery,
    ctx: TenantContext = Depends(get_tenant_context),
):
    ctx.require_role("admin", "compliance_manager", "control_owner", "auditor", "read_only")
    return rag_service.query(payload.query, ctx.tenant_id, ctx.user_role)


@app.post("/api/v1/rag/index/rebuild")
def rag_index_rebuild(
    ctx: TenantContext = Depends(get_tenant_context),
):
    ctx.require_role("admin", "compliance_manager")
    counts = rag_service.index_rebuild(ctx.tenant_id)
    return {"indexed": counts}


@app.post("/api/v1/rag/index/entity")
def rag_index_entity(
    payload: RAGIndexRequest,
    ctx: TenantContext = Depends(get_tenant_context),
):
    ctx.require_role("admin", "compliance_manager")
    count = rag_service.index_entity(ctx.tenant_id, payload.entity_type, payload.entity_id)
    return {"indexed": count}


@app.get("/api/v1/rag/health")
def rag_health(
    ctx: TenantContext = Depends(get_tenant_context),
):
    ctx.require_role("admin", "compliance_manager", "control_owner", "auditor", "read_only")
    return rag_service.health(ctx.tenant_id)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_integration(integration_id: str, tenant_id: str) -> dict[str, Any]:
    row = db.fetchone(
        "SELECT * FROM integration WHERE id = %s AND tenant_id = %s",
        (_parse_uuid(integration_id), tenant_id),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Integration not found")
    return dict(row)


def _integration_row(integration_id: str, tenant_id: str) -> IntegrationOut:
    row = db.fetchone(
        "SELECT * FROM integration WHERE id = %s AND tenant_id = %s",
        (_parse_uuid(integration_id), tenant_id),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Integration not found")
    return IntegrationOut(**row)


def _get_common_control(control_id: str, tenant_id: str) -> dict[str, Any]:
    row = db.fetchone(
        """SELECT cc.*, u.email as owner_email
           FROM common_control cc
           LEFT JOIN "user" u ON u.id = cc.owner_id
           WHERE cc.id = %s AND cc.tenant_id = %s""",
        (_parse_uuid(control_id), tenant_id),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Control not found")
    return dict(row)


def _list_common_controls(tenant_id: str, framework_code: str | None) -> list[dict[str, Any]]:
    sql = """SELECT cc.*, u.email as owner_email
             FROM common_control cc
             LEFT JOIN "user" u ON u.id = cc.owner_id
             WHERE cc.tenant_id = %s"""
    params: list[Any] = [tenant_id]
    if framework_code:
        sql += """ AND cc.id IN (
            SELECT common_control_id FROM framework_control fc
            JOIN framework f ON f.id = fc.framework_id
            WHERE f.code = %s AND fc.tenant_id = %s
        )"""
        params.extend([framework_code, tenant_id])
    sql += " ORDER BY cc.domain, cc.code"
    rows = db.execute(sql, tuple(params))
    return [dict(r) for r in rows]


def _get_test(test_id: str, tenant_id: str) -> dict[str, Any]:
    row = db.fetchone(
        "SELECT * FROM test WHERE id = %s AND tenant_id = %s",
        (_parse_uuid(test_id), tenant_id),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Test not found")
    return dict(row)


def _get_audit(audit_id: str, tenant_id: str) -> dict[str, Any]:
    row = db.fetchone(
        "SELECT * FROM audit WHERE id = %s AND tenant_id = %s",
        (_parse_uuid(audit_id), tenant_id),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Audit not found")
    return dict(row)


def _get_audit_request(request_id: str) -> dict[str, Any]:
    row = db.fetchone(
        """SELECT ar.*, cc.code as control_code
           FROM audit_request ar
           LEFT JOIN common_control cc ON cc.id = ar.control_id
           WHERE ar.id = %s""",
        (_parse_uuid(request_id),),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Audit request not found")
    return dict(row)


def _control_detail(control: dict[str, Any], tenant_id: str) -> dict[str, Any]:
    status_data = _control_status(tenant_id, control["id"])
    results = db.execute(
        """SELECT t.name as test_name, r.external_id as resource_external_id,
                  tr.status, tr.reason, tr.evaluated_at
           FROM control_test ct
           JOIN test t ON t.id = ct.test_id
           LEFT JOIN LATERAL (
               SELECT trun.id
               FROM test_run trun
               WHERE trun.test_id = t.id AND trun.tenant_id = %s AND trun.status = 'completed'
               ORDER BY trun.completed_at DESC
               LIMIT 1
           ) latest_run ON true
           JOIN test_result tr ON tr.test_run_id = latest_run.id
           LEFT JOIN resource r ON r.id = tr.resource_id
           WHERE ct.common_control_id = %s AND ct.tenant_id = %s
           ORDER BY tr.evaluated_at DESC""",
        (tenant_id, control["id"], tenant_id),
    )
    return {
        **ControlStatus(
            control_id=control["id"],
            code=control["code"],
            statement=control["statement"],
            owner=control.get("owner_email"),
            status=status_data["status"],
            evidence_count=status_data["evidence_count"],
            last_evaluated_at=status_data["last_evaluated_at"],
        ).dict(),
        "latest_results": [dict(r) for r in results],
    }


def _hydrate_control_status(control: dict[str, Any], tenant_id: str) -> dict[str, Any]:
    status_data = _control_status(tenant_id, control["id"])
    return {
        **ControlStatus(
            control_id=control["id"],
            code=control["code"],
            statement=control["statement"],
            owner=control.get("owner_email"),
            status=status_data["status"],
            evidence_count=status_data["evidence_count"],
            last_evaluated_at=status_data["last_evaluated_at"],
        ).dict(),
    }


def _control_status(tenant_id: str, common_control_id: str) -> dict[str, Any]:
    rows = db.execute(
        """SELECT t.id as test_id, tr.status, e.id as evidence_id, tr.evaluated_at
           FROM control_test ct
           JOIN test t ON t.id = ct.test_id
           LEFT JOIN LATERAL (
               SELECT trun.id, trun.completed_at
               FROM test_run trun
               WHERE trun.test_id = t.id AND trun.tenant_id = %s AND trun.status = 'completed'
               ORDER BY trun.completed_at DESC
               LIMIT 1
           ) latest_run ON true
           LEFT JOIN test_result tr ON tr.test_run_id = latest_run.id
           LEFT JOIN evidence e ON e.test_result_id = tr.id
           WHERE ct.common_control_id = %s AND ct.tenant_id = %s""",
        (tenant_id, common_control_id, tenant_id),
    )
    if not rows:
        return {"status": "NOT_TESTED", "evidence_count": 0, "last_evaluated_at": None}

    statuses = [r["status"] for r in rows if r["status"]]
    evidence_count = sum(1 for r in rows if r["evidence_id"])
    last_evaluated = max(
        (r["evaluated_at"] for r in rows if r["evaluated_at"]), default=None
    )

    if not statuses:
        return {"status": "NOT_TESTED", "evidence_count": 0, "last_evaluated_at": None}
    if "NEEDS_ATTENTION" in statuses:
        overall = "NEEDS_ATTENTION"
    elif "INVALID" in statuses:
        overall = "INVALID"
    elif all(s == "OK" for s in statuses):
        overall = "OK"
    else:
        overall = "NEEDS_ATTENTION"
    return {"status": overall, "evidence_count": evidence_count, "last_evaluated_at": last_evaluated}


def _framework_readiness(tenant_id: str, framework_id: str) -> FrameworkReadiness:
    framework = db.fetchone(
        "SELECT * FROM framework WHERE id = %s AND tenant_id = %s",
        (framework_id, tenant_id),
    )
    controls = db.execute(
        """SELECT DISTINCT common_control_id
           FROM framework_control
           WHERE framework_id = %s AND tenant_id = %s""",
        (framework_id, tenant_id),
    )
    total = len(controls)
    if total == 0:
        return FrameworkReadiness(
            framework_id=framework_id,
            code=framework["code"],
            name=framework["name"],
            total_controls=0,
            ok_controls=0,
            needs_attention_controls=0,
            readiness_pct=0.0,
        )

    ok = 0
    na = 0
    for c in controls:
        st = _control_status(tenant_id, c["common_control_id"])
        if st["status"] == "OK":
            ok += 1
        elif st["status"] == "NEEDS_ATTENTION":
            na += 1

    pct = round((ok / total) * 100, 2) if total > 0 else 0.0
    return FrameworkReadiness(
        framework_id=framework_id,
        code=framework["code"],
        name=framework["name"],
        total_controls=total,
        ok_controls=ok,
        needs_attention_controls=na,
        readiness_pct=pct,
    )


def _compute_posture(tenant_id: str) -> PostureSummary:
    frameworks = db.execute(
        "SELECT id FROM framework WHERE tenant_id = %s",
        (tenant_id,),
    )
    readiness = [_framework_readiness(tenant_id, f["id"]) for f in frameworks]

    total_controls = db.execute(
        "SELECT COUNT(*) as c FROM common_control WHERE tenant_id = %s",
        (tenant_id,),
    )[0]["c"]

    ok = 0
    na = 0
    for cc in db.execute(
        "SELECT id FROM common_control WHERE tenant_id = %s", (tenant_id,)
    ):
        st = _control_status(tenant_id, cc["id"])
        if st["status"] == "OK":
            ok += 1
        elif st["status"] == "NEEDS_ATTENTION":
            na += 1

    overall_pct = round((ok / total_controls) * 100, 2) if total_controls > 0 else 0.0
    return PostureSummary(
        tenant_id=tenant_id,
        frameworks=readiness,
        overall_controls=total_controls,
        overall_ok=ok,
        overall_needs_attention=na,
        overall_readiness_pct=overall_pct,
    )
