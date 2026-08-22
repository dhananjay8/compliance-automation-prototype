import asyncio
import json
import os
import uuid
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from analytics import _control_status, compute_posture
from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware

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
    FrameworkMappingCreate,
    FrameworkReadiness,
    IntegrationCreate,
    IntegrationOut,
    PostureSummary,
    TestCreate,
    TestRunSummary,
)
from worker import SyncWorker, run_test
from rag import RAGQuery, RAGResponse, RAGIndexRequest, rag as rag_service
from drift import detect_drift_for_integration, list_drift, acknowledge_drift
from scheduler import ComplianceScheduler, ENABLE_SCHEDULER, run_due_jobs, trigger_job_now


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.configure()
    schema_path = Path(__file__).resolve().parent / "schema.sql"
    db.init_schema(str(schema_path))
    scheduler = ComplianceScheduler(db)
    if ENABLE_SCHEDULER:
        scheduler.start()
    yield
    scheduler.shutdown()
    if db._pool:
        db._pool.closeall()


app = FastAPI(title="Compliance Automation Prototype", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
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


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_uuid(value: str) -> str:
    try:
        return str(uuid.UUID(value))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid UUID: {value}") from exc


def _opt_uuid(value: str | None) -> str | None:
    if not value:
        return None
    return _parse_uuid(value)


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
    return compute_posture(tenant_id)


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


@app.post("/api/v1/controls/{control_id}/mappings")
def create_control_mappings(
    control_id: str,
    payload: list[FrameworkMappingCreate],
    ctx: TenantContext = Depends(get_tenant_context),
):
    ctx.require_role("admin", "compliance_manager")
    _get_common_control(control_id, ctx.tenant_id)
    created: list[str] = []
    for m in payload:
        framework = db.fetchone(
            "SELECT id FROM framework WHERE tenant_id = %s AND code = %s",
            (ctx.tenant_id, m.framework_code),
        )
        if not framework:
            raise HTTPException(status_code=404, detail=f"Framework {m.framework_code} not found")
        section_id = None
        if m.section_code:
            section = db.fetchone(
                "SELECT id FROM section WHERE framework_id = %s AND code = %s",
                (framework["id"], m.section_code),
            )
            if not section:
                raise HTTPException(status_code=404, detail=f"Section {m.section_code} not found")
            section_id = section["id"]
        mapping_id = str(uuid.uuid4())
        db.execute(
            """INSERT INTO framework_control (id, tenant_id, framework_id, section_id, common_control_id, requirement_text)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (mapping_id, ctx.tenant_id, framework["id"], section_id, _parse_uuid(control_id), m.requirement_text),
        )
        created.append(mapping_id)
    return {"created_mapping_ids": created}


@app.get("/api/v1/controls/{control_id}/mappings")
def list_control_mappings(
    control_id: str,
    ctx: TenantContext = Depends(get_tenant_context),
):
    ctx.require_role("admin", "compliance_manager", "control_owner", "auditor", "read_only")
    _get_common_control(control_id, ctx.tenant_id)
    return db.execute(
        """SELECT fc.id, f.code as framework_code, f.name as framework_name,
                  s.code as section_code, s.title as section_title,
                  fc.requirement_text
           FROM framework_control fc
           JOIN framework f ON f.id = fc.framework_id
           LEFT JOIN section s ON s.id = fc.section_id
           WHERE fc.common_control_id = %s AND fc.tenant_id = %s""",
        (_parse_uuid(control_id), ctx.tenant_id),
    )


@app.delete("/api/v1/controls/{control_id}/mappings/{mapping_id}")
def delete_control_mapping(
    control_id: str,
    mapping_id: str,
    ctx: TenantContext = Depends(get_tenant_context),
):
    ctx.require_role("admin", "compliance_manager")
    _get_common_control(control_id, ctx.tenant_id)
    db.execute(
        "DELETE FROM framework_control WHERE id = %s AND common_control_id = %s AND tenant_id = %s",
        (_parse_uuid(mapping_id), _parse_uuid(control_id), ctx.tenant_id),
    )
    return {"deleted": mapping_id}


@app.post("/api/v1/controls/{control_id}/tests")
def create_control_test(
    control_id: str,
    payload: TestCreate,
    ctx: TenantContext = Depends(get_tenant_context),
):
    ctx.require_role("admin", "compliance_manager")
    _get_common_control(control_id, ctx.tenant_id)
    test_id = str(uuid.uuid4())
    db.execute(
        """INSERT INTO test (id, tenant_id, name, resource_type, rule, schedule, active)
           VALUES (%s, %s, %s, %s, %s, %s, %s)""",
        (test_id, ctx.tenant_id, payload.name, payload.resource_type, json.dumps(payload.rule),
         payload.schedule, True),
    )
    db.execute(
        """INSERT INTO control_test (id, tenant_id, common_control_id, test_id)
           VALUES (%s, %s, %s, %s)""",
        (str(uuid.uuid4()), ctx.tenant_id, _parse_uuid(control_id), test_id),
    )
    for cid in payload.common_control_ids:
        if cid != control_id:
            db.execute(
                """INSERT INTO control_test (id, tenant_id, common_control_id, test_id)
                   VALUES (%s, %s, %s, %s)
                   ON CONFLICT DO NOTHING""",
                (str(uuid.uuid4()), ctx.tenant_id, _parse_uuid(cid), test_id),
            )
    return db.fetchone("SELECT * FROM test WHERE id = %s", (test_id,))


@app.get("/api/v1/controls/{control_id}/tests")
def list_control_tests(
    control_id: str,
    ctx: TenantContext = Depends(get_tenant_context),
):
    ctx.require_role("admin", "compliance_manager", "control_owner", "auditor", "read_only")
    _get_common_control(control_id, ctx.tenant_id)
    return db.execute(
        """SELECT t.*
           FROM test t
           JOIN control_test ct ON ct.test_id = t.id
           WHERE ct.common_control_id = %s AND t.tenant_id = %s""",
        (_parse_uuid(control_id), ctx.tenant_id),
    )


@app.get("/api/v1/frameworks/{framework_code}/controls")
def framework_controls(
    framework_code: str,
    ctx: TenantContext = Depends(get_tenant_context),
):
    ctx.require_role("admin", "compliance_manager", "control_owner", "auditor", "read_only")
    framework = db.fetchone(
        "SELECT id FROM framework WHERE tenant_id = %s AND code = %s",
        (ctx.tenant_id, framework_code),
    )
    if not framework:
        raise HTTPException(status_code=404, detail="Framework not found")
    return db.execute(
        """SELECT cc.id, cc.code, cc.domain, cc.statement, cc.active,
                  fc.id as mapping_id, fc.requirement_text,
                  s.code as section_code, s.title as section_title
           FROM framework_control fc
           JOIN common_control cc ON cc.id = fc.common_control_id
           LEFT JOIN section s ON s.id = fc.section_id
           WHERE fc.framework_id = %s AND fc.tenant_id = %s
           ORDER BY s.code, cc.code""",
        (framework["id"], ctx.tenant_id),
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


@app.post("/api/v1/evidence/upload")
def upload_evidence_file(
    uploaded: UploadFile = File(...),
    ctx: TenantContext = Depends(get_tenant_context),
):
    ctx.require_role("admin", "compliance_manager", "control_owner")
    repo_root = Path(__file__).resolve().parent.parent
    evidence_dir = repo_root / "data" / "evidence_files"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    file_id = str(uuid.uuid4())
    dest = evidence_dir / f"{file_id}_{uploaded.filename}"
    dest.write_bytes(uploaded.file.read())
    return {
        "file_id": file_id,
        "filename": uploaded.filename,
        "storage_path": str(dest.relative_to(repo_root)),
    }


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


@app.get("/api/v1/dashboards/posture", response_model=PostureSummary)
def dashboard_posture(
    ctx: TenantContext = Depends(get_tenant_context),
):
    ctx.require_role("admin", "compliance_manager", "control_owner", "auditor", "read_only")
    return compute_posture(ctx.tenant_id)


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


# ---------------------------------------------------------------------------
# Phase 3 - Remediation workflows
# ---------------------------------------------------------------------------


@app.get("/api/v1/remediations")
def list_remediations(ctx: TenantContext = Depends(get_tenant_context)):
    ctx.require_role("admin", "compliance_manager", "control_owner")
    return db.execute(
        """SELECT r.*, u.email as assignee_email, cc.code as control_code
           FROM remediation r
           LEFT JOIN "user" u ON u.id = r.assignee_id
           LEFT JOIN common_control cc ON cc.id = r.control_id
           WHERE r.tenant_id = %s
           ORDER BY r.created_at DESC""",
        (ctx.tenant_id,),
    )


@app.post("/api/v1/remediations")
def create_remediation(
    title: str = Query(...),
    description: str = Query(default=""),
    test_result_id: str | None = Query(default=None),
    control_id: str | None = Query(default=None),
    assignee_email: str | None = Query(default=None),
    ctx: TenantContext = Depends(get_tenant_context),
):
    ctx.require_role("admin", "compliance_manager")
    assignee_id = None
    if assignee_email:
        user = db.fetchone(
            'SELECT id FROM "user" WHERE tenant_id = %s AND email = %s',
            (ctx.tenant_id, assignee_email),
        )
        if user:
            assignee_id = user["id"]
    rem_id = str(uuid.uuid4())
    db.execute(
        """INSERT INTO remediation
               (id, tenant_id, test_result_id, control_id, title, description, assignee_id, status)
           VALUES (%s, %s, %s, %s, %s, %s, %s, 'open')""",
        (
            rem_id,
            ctx.tenant_id,
            _opt_uuid(test_result_id),
            _opt_uuid(control_id),
            title,
            description,
            assignee_id,
        ),
    )
    _emit_webhook(ctx.tenant_id, "remediation.created", {"id": rem_id, "title": title, "status": "open"})
    return db.fetchone("SELECT * FROM remediation WHERE id = %s", (rem_id,))


@app.post("/api/v1/remediations/{remediation_id}/status")
def update_remediation_status(
    remediation_id: str,
    status: str = Query(...),
    ctx: TenantContext = Depends(get_tenant_context),
):
    ctx.require_role("admin", "compliance_manager", "control_owner")
    if status not in ("open", "in_progress", "resolved", "closed"):
        raise HTTPException(status_code=400, detail="Invalid status")
    resolved_at: datetime | None = None
    if status in ("resolved", "closed"):
        resolved_at = _now()
    db.execute(
        "UPDATE remediation SET status = %s, resolved_at = %s WHERE id = %s AND tenant_id = %s",
        (status, resolved_at, _parse_uuid(remediation_id), ctx.tenant_id),
    )
    _emit_webhook(
        ctx.tenant_id,
        "remediation.status_changed",
        {"id": remediation_id, "status": status},
    )
    return db.fetchone("SELECT * FROM remediation WHERE id = %s", (_parse_uuid(remediation_id),))


@app.post("/api/v1/remediations/{remediation_id}/ticket")
def attach_remediation_ticket(
    remediation_id: str,
    ticket_id: str = Query(...),
    ctx: TenantContext = Depends(get_tenant_context),
):
    ctx.require_role("admin", "compliance_manager")
    db.execute(
        "UPDATE remediation SET ticket_id = %s WHERE id = %s AND tenant_id = %s",
        (ticket_id, _parse_uuid(remediation_id), ctx.tenant_id),
    )
    return db.fetchone("SELECT * FROM remediation WHERE id = %s", (_parse_uuid(remediation_id),))


# ---------------------------------------------------------------------------
# Phase 3 - Access review campaigns
# ---------------------------------------------------------------------------


@app.get("/api/v1/access-reviews")
def list_access_reviews(ctx: TenantContext = Depends(get_tenant_context)):
    ctx.require_role("admin", "compliance_manager", "auditor")
    return db.execute(
        "SELECT * FROM access_review WHERE tenant_id = %s ORDER BY due_date",
        (ctx.tenant_id,),
    )


@app.post("/api/v1/access-reviews")
def create_access_review(
    name: str = Query(...),
    due_date: str | None = Query(default=None),
    ctx: TenantContext = Depends(get_tenant_context),
):
    ctx.require_role("admin", "compliance_manager")
    ar_id = str(uuid.uuid4())
    db.execute(
        "INSERT INTO access_review (id, tenant_id, name, due_date) VALUES (%s, %s, %s, %s)",
        (ar_id, ctx.tenant_id, name, due_date),
    )
    _emit_webhook(ctx.tenant_id, "access_review.created", {"id": ar_id, "name": name})
    return db.fetchone("SELECT * FROM access_review WHERE id = %s", (ar_id,))


@app.get("/api/v1/access-reviews/{access_review_id}/items")
def list_access_review_items(
    access_review_id: str,
    ctx: TenantContext = Depends(get_tenant_context),
):
    ctx.require_role("admin", "compliance_manager", "auditor")
    return db.execute(
        """SELECT i.*, u.email as user_email
           FROM access_review_item i
           LEFT JOIN "user" u ON u.id = i.user_id
           WHERE i.access_review_id = %s AND i.tenant_id = %s""",
        (_parse_uuid(access_review_id), ctx.tenant_id),
    )


@app.post("/api/v1/access-reviews/{access_review_id}/items")
def add_access_review_item(
    access_review_id: str,
    user_email: str = Query(...),
    system: str = Query(...),
    ctx: TenantContext = Depends(get_tenant_context),
):
    ctx.require_role("admin", "compliance_manager")
    user = db.fetchone(
        'SELECT id FROM "user" WHERE tenant_id = %s AND email = %s',
        (ctx.tenant_id, user_email),
    )
    user_id = user["id"] if user else None
    item_id = str(uuid.uuid4())
    db.execute(
        """INSERT INTO access_review_item
               (id, tenant_id, access_review_id, user_id, system, decision)
           VALUES (%s, %s, %s, %s, %s, 'pending')""",
        (item_id, ctx.tenant_id, _parse_uuid(access_review_id), user_id, system),
    )
    return db.fetchone("SELECT * FROM access_review_item WHERE id = %s", (item_id,))


@app.post("/api/v1/access-reviews/{access_review_id}/items/{item_id}/decide")
def decide_access_review_item(
    access_review_id: str,
    item_id: str,
    decision: str = Query(...),
    notes: str = Query(default=""),
    ctx: TenantContext = Depends(get_tenant_context),
):
    ctx.require_role("admin", "compliance_manager", "auditor")
    if decision not in ("approved", "revoked"):
        raise HTTPException(status_code=400, detail="Invalid decision")
    db.execute(
        """UPDATE access_review_item
           SET decision = %s, notes = %s
           WHERE id = %s AND access_review_id = %s AND tenant_id = %s""",
        (decision, notes, _parse_uuid(item_id), _parse_uuid(access_review_id), ctx.tenant_id),
    )
    _emit_webhook(
        ctx.tenant_id,
        "access_review.decided",
        {"access_review_id": access_review_id, "item_id": item_id, "decision": decision},
    )
    return db.fetchone("SELECT * FROM access_review_item WHERE id = %s", (_parse_uuid(item_id),))


# ---------------------------------------------------------------------------
# Phase 3 - Vendor risk questionnaires
# ---------------------------------------------------------------------------


@app.get("/api/v1/vendors")
def list_vendors(ctx: TenantContext = Depends(get_tenant_context)):
    ctx.require_role("admin", "compliance_manager", "auditor")
    return db.execute("SELECT * FROM vendor WHERE tenant_id = %s", (ctx.tenant_id,))


@app.post("/api/v1/vendors")
def create_vendor(
    name: str = Query(...),
    category: str = Query(default=""),
    risk_level: str = Query(default="medium"),
    ctx: TenantContext = Depends(get_tenant_context),
):
    ctx.require_role("admin", "compliance_manager")
    if risk_level not in ("low", "medium", "high", "critical"):
        raise HTTPException(status_code=400, detail="Invalid risk_level")
    vendor_id = str(uuid.uuid4())
    db.execute(
        "INSERT INTO vendor (id, tenant_id, name, category, risk_level) VALUES (%s, %s, %s, %s, %s)",
        (vendor_id, ctx.tenant_id, name, category, risk_level),
    )
    return db.fetchone("SELECT * FROM vendor WHERE id = %s", (vendor_id,))


@app.get("/api/v1/vendors/{vendor_id}/assessments")
def list_vendor_assessments(
    vendor_id: str,
    ctx: TenantContext = Depends(get_tenant_context),
):
    ctx.require_role("admin", "compliance_manager", "auditor")
    return db.execute(
        "SELECT * FROM vendor_assessment WHERE vendor_id = %s AND tenant_id = %s",
        (_parse_uuid(vendor_id), ctx.tenant_id),
    )


@app.post("/api/v1/vendors/{vendor_id}/assessments")
def create_vendor_assessment(
    vendor_id: str,
    questionnaire: str = Query(default=""),
    ctx: TenantContext = Depends(get_tenant_context),
):
    ctx.require_role("admin", "compliance_manager")
    assessment_id = str(uuid.uuid4())
    parsed = json.loads(questionnaire) if questionnaire else {}
    db.execute(
        """INSERT INTO vendor_assessment
               (id, tenant_id, vendor_id, questionnaire, status)
           VALUES (%s, %s, %s, %s, 'pending')""",
        (assessment_id, ctx.tenant_id, _parse_uuid(vendor_id), json.dumps(parsed)),
    )
    return db.fetchone("SELECT * FROM vendor_assessment WHERE id = %s", (assessment_id,))


@app.post("/api/v1/vendors/{vendor_id}/assessments/{assessment_id}/respond")
def respond_vendor_assessment(
    vendor_id: str,
    assessment_id: str,
    responses: str = Query(default=""),
    ctx: TenantContext = Depends(get_tenant_context),
):
    ctx.require_role("admin", "compliance_manager")
    parsed = json.loads(responses) if responses else {}
    db.execute(
        """UPDATE vendor_assessment
           SET responses = %s, status = 'complete', completed_at = %s
           WHERE id = %s AND vendor_id = %s AND tenant_id = %s""",
        (json.dumps(parsed), _now(), _parse_uuid(assessment_id), _parse_uuid(vendor_id), ctx.tenant_id),
    )
    _emit_webhook(
        ctx.tenant_id,
        "vendor_assessment.completed",
        {"vendor_id": vendor_id, "assessment_id": assessment_id},
    )
    return db.fetchone("SELECT * FROM vendor_assessment WHERE id = %s", (_parse_uuid(assessment_id),))


# ---------------------------------------------------------------------------
# Phase 3 - Auditor portal / information requests
# ---------------------------------------------------------------------------


@app.get("/api/v1/audits")
def list_audits(ctx: TenantContext = Depends(get_tenant_context)):
    ctx.require_role("admin", "compliance_manager", "auditor")
    return db.execute(
        """SELECT a.*, f.code as framework_code
           FROM audit a
           JOIN framework f ON f.id = a.framework_id
           WHERE a.tenant_id = %s""",
        (ctx.tenant_id,),
    )


@app.post("/api/v1/audits")
def create_audit(
    framework_code: str = Query(...),
    auditor_email: str | None = Query(default=None),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    ctx: TenantContext = Depends(get_tenant_context),
):
    ctx.require_role("admin", "compliance_manager")
    framework = db.fetchone(
        "SELECT id FROM framework WHERE tenant_id = %s AND code = %s",
        (ctx.tenant_id, framework_code),
    )
    if not framework:
        raise HTTPException(status_code=404, detail="Framework not found")
    auditor_id = None
    if auditor_email:
        user = db.fetchone(
            'SELECT id FROM "user" WHERE tenant_id = %s AND email = %s',
            (ctx.tenant_id, auditor_email),
        )
        if user:
            auditor_id = user["id"]
    audit_id = str(uuid.uuid4())
    db.execute(
        """INSERT INTO audit (id, tenant_id, framework_id, auditor_id, start_date, end_date)
           VALUES (%s, %s, %s, %s, %s, %s)""",
        (audit_id, ctx.tenant_id, framework["id"], auditor_id, start_date, end_date),
    )
    _emit_webhook(ctx.tenant_id, "audit.created", {"id": audit_id, "framework_code": framework_code})
    return db.fetchone("SELECT * FROM audit WHERE id = %s", (audit_id,))


@app.get("/api/v1/audits/{audit_id}/requests")
def list_audit_requests(
    audit_id: str,
    ctx: TenantContext = Depends(get_tenant_context),
):
    ctx.require_role("admin", "compliance_manager", "auditor")
    return db.execute(
        """SELECT ar.*, cc.code as control_code
           FROM audit_request ar
           LEFT JOIN common_control cc ON cc.id = ar.control_id
           WHERE ar.audit_id = %s AND ar.tenant_id = %s""",
        (_parse_uuid(audit_id), ctx.tenant_id),
    )


@app.post("/api/v1/audits/{audit_id}/requests")
def create_audit_request(
    audit_id: str,
    request_text: str = Query(...),
    control_id: str | None = Query(default=None),
    ctx: TenantContext = Depends(get_tenant_context),
):
    ctx.require_role("admin", "compliance_manager", "auditor")
    req_id = str(uuid.uuid4())
    db.execute(
        """INSERT INTO audit_request
               (id, tenant_id, audit_id, control_id, request_text)
           VALUES (%s, %s, %s, %s, %s)""",
        (req_id, ctx.tenant_id, _parse_uuid(audit_id), _opt_uuid(control_id), request_text),
    )
    _emit_webhook(
        ctx.tenant_id,
        "audit_request.created",
        {"audit_id": audit_id, "request_id": req_id},
    )
    return db.fetchone("SELECT * FROM audit_request WHERE id = %s", (req_id,))


@app.post("/api/v1/audits/{audit_id}/requests/{request_id}/respond")
def respond_audit_request(
    audit_id: str,
    request_id: str,
    response_text: str = Query(...),
    evidence_id: str | None = Query(default=None),
    ctx: TenantContext = Depends(get_tenant_context),
):
    ctx.require_role("admin", "compliance_manager", "control_owner")
    db.execute(
        """UPDATE audit_request
           SET status = 'responded', response_text = %s, evidence_id = %s, responded_at = %s
           WHERE id = %s AND audit_id = %s AND tenant_id = %s""",
        (
            response_text,
            _opt_uuid(evidence_id),
            _now(),
            _parse_uuid(request_id),
            _parse_uuid(audit_id),
            ctx.tenant_id,
        ),
    )
    _emit_webhook(
        ctx.tenant_id,
        "audit_request.responded",
        {"audit_id": audit_id, "request_id": request_id},
    )
    return db.fetchone("SELECT * FROM audit_request WHERE id = %s", (_parse_uuid(request_id),))


@app.post("/api/v1/audits/{audit_id}/requests/{request_id}/status")
def update_audit_request_status(
    audit_id: str,
    request_id: str,
    status: str = Query(...),
    ctx: TenantContext = Depends(get_tenant_context),
):
    ctx.require_role("admin", "compliance_manager", "auditor")
    if status not in ("open", "responded", "accepted", "flagged"):
        raise HTTPException(status_code=400, detail="Invalid status")
    db.execute(
        """UPDATE audit_request
           SET status = %s
           WHERE id = %s AND audit_id = %s AND tenant_id = %s""",
        (status, _parse_uuid(request_id), _parse_uuid(audit_id), ctx.tenant_id),
    )
    _emit_webhook(
        ctx.tenant_id,
        "audit_request.status_changed",
        {"audit_id": audit_id, "request_id": request_id, "status": status},
    )
    return db.fetchone("SELECT * FROM audit_request WHERE id = %s", (_parse_uuid(request_id),))


# ---------------------------------------------------------------------------
# Phase 3 - Webhooks / public API surface
# ---------------------------------------------------------------------------


@app.get("/api/v1/webhooks")
def list_webhooks(ctx: TenantContext = Depends(get_tenant_context)):
    ctx.require_role("admin")
    return db.execute(
        "SELECT * FROM webhook_subscription WHERE tenant_id = %s",
        (ctx.tenant_id,),
    )


@app.post("/api/v1/webhooks")
def create_webhook(
    url: str = Query(...),
    events: str = Query(default=""),
    secret: str = Query(default=""),
    ctx: TenantContext = Depends(get_tenant_context),
):
    ctx.require_role("admin")
    sub_id = str(uuid.uuid4())
    event_list = [e.strip() for e in events.split(",") if e.strip()]
    db.execute(
        """INSERT INTO webhook_subscription (id, tenant_id, url, events, secret)
           VALUES (%s, %s, %s, %s, %s)""",
        (sub_id, ctx.tenant_id, url, event_list, secret),
    )
    return db.fetchone("SELECT * FROM webhook_subscription WHERE id = %s", (sub_id,))


@app.delete("/api/v1/webhooks/{subscription_id}")
def delete_webhook(
    subscription_id: str,
    ctx: TenantContext = Depends(get_tenant_context),
):
    ctx.require_role("admin")
    db.execute(
        "DELETE FROM webhook_subscription WHERE id = %s AND tenant_id = %s",
        (_parse_uuid(subscription_id), ctx.tenant_id),
    )
    return {"deleted": True}


@app.get("/api/v1/webhooks/{subscription_id}/deliveries")
def list_webhook_deliveries(
    subscription_id: str,
    ctx: TenantContext = Depends(get_tenant_context),
):
    ctx.require_role("admin")
    return db.execute(
        """SELECT * FROM webhook_delivery
           WHERE subscription_id = %s AND tenant_id = %s
           ORDER BY created_at DESC""",
        (_parse_uuid(subscription_id), ctx.tenant_id),
    )


def _emit_webhook(tenant_id: str, event: str, payload: dict[str, Any]) -> None:
    """Deliver a webhook event to active subscriptions. Failures are logged only."""
    subs = db.execute(
        """SELECT * FROM webhook_subscription
           WHERE tenant_id = %s AND active = true
             AND (cardinality(events) = 0 OR %s = ANY(events))""",
        (tenant_id, event),
    )
    for sub in subs:
        delivery_id = str(uuid.uuid4())
        db.execute(
            """INSERT INTO webhook_delivery
                   (id, tenant_id, subscription_id, event, payload, status)
               VALUES (%s, %s, %s, %s, %s, 'pending')""",
            (delivery_id, tenant_id, sub["id"], event, json.dumps(payload)),
        )
        try:
            import requests

            body = {"event": event, "payload": payload}
            headers = {"Content-Type": "application/json"}
            if sub.get("secret"):
                headers["X-Webhook-Secret"] = sub["secret"]
            resp = requests.post(sub["url"], json=body, headers=headers, timeout=5)
            status = "delivered" if resp.status_code < 400 else "failed"
            db.execute(
                """UPDATE webhook_delivery
                   SET status = %s, response_status = %s, delivered_at = %s
                   WHERE id = %s""",
                (status, resp.status_code, _now(), delivery_id),
            )
        except Exception:
            db.execute(
                "UPDATE webhook_delivery SET status = 'failed' WHERE id = %s",
                (delivery_id,),
            )


# ---------------------------------------------------------------------------
# Phase 4 - Scale & Intelligence
# ---------------------------------------------------------------------------


@app.get("/api/v1/drift")
def list_drift_detections(
    acknowledged: bool | None = Query(default=None),
    ctx: TenantContext = Depends(get_tenant_context),
):
    ctx.require_role("admin", "compliance_manager", "control_owner", "auditor")
    return list_drift(db, ctx.tenant_id, acknowledged)


@app.post("/api/v1/drift/detect")
def trigger_drift_detection(
    integration_id: str = Query(...),
    ctx: TenantContext = Depends(get_tenant_context),
):
    ctx.require_role("admin", "compliance_manager", "control_owner")
    _get_integration(integration_id, ctx.tenant_id)
    records = detect_drift_for_integration(db, integration_id, ctx.tenant_id)
    return {"integration_id": integration_id, "drifts": len(records)}


@app.post("/api/v1/drift/{drift_id}/acknowledge")
def ack_drift(
    drift_id: str,
    ctx: TenantContext = Depends(get_tenant_context),
):
    ctx.require_role("admin", "compliance_manager", "control_owner", "auditor")
    acknowledge_drift(db, drift_id, ctx.tenant_id)
    return {"id": drift_id, "acknowledged": True}


@app.get("/api/v1/evidence/stale/list")
def list_stale_evidence(
    hours: int = Query(default=48),
    ctx: TenantContext = Depends(get_tenant_context),
):
    ctx.require_role("admin", "compliance_manager", "control_owner", "auditor", "read_only")
    threshold = _now() - timedelta(hours=hours)
    return db.execute(
        """SELECT e.*, t.name as test_name
           FROM evidence e
           LEFT JOIN test_result tr ON tr.id = e.test_result_id
           LEFT JOIN test_run trun ON trun.id = tr.test_run_id
           LEFT JOIN test t ON t.id = trun.test_id
           WHERE e.tenant_id = %s
             AND (e.expires_at IS NULL OR e.expires_at <= %s OR e.collected_at <= %s)
           ORDER BY e.collected_at ASC""",
        (ctx.tenant_id, _now(), threshold),
    )


@app.post("/api/v1/evidence/recollect")
def recollect_evidence(
    test_id: str | None = Query(default=None),
    integration_id: str | None = Query(default=None),
    ctx: TenantContext = Depends(get_tenant_context),
):
    ctx.require_role("admin", "compliance_manager", "control_owner")
    if test_id:
        test = db.fetchone(
            "SELECT * FROM test WHERE id = %s AND tenant_id = %s",
            (_parse_uuid(test_id), ctx.tenant_id),
        )
        if not test:
            raise HTTPException(status_code=404, detail="Test not found")
        run_test(db, dict(test))
        return {"test_id": test_id, "recollected": True}
    if integration_id:
        integration = _get_integration(integration_id, ctx.tenant_id)
        worker.sync_integration(integration, triggered_by=ctx.user_id)
        return {"integration_id": integration_id, "recollected": True}
    raise HTTPException(status_code=400, detail="Provide test_id or integration_id")


@app.get("/api/v1/analytics/posture")
def posture_history(
    days: int = Query(default=30),
    ctx: TenantContext = Depends(get_tenant_context),
):
    ctx.require_role("admin", "compliance_manager", "auditor", "read_only")
    return db.execute(
        """SELECT *
           FROM posture_history
           WHERE tenant_id = %s AND recorded_at >= %s
           ORDER BY recorded_at DESC""",
        (ctx.tenant_id, _now() - timedelta(days=days)),
    )


@app.post("/api/v1/analytics/posture")
def snapshot_posture(ctx: TenantContext = Depends(get_tenant_context)):
    ctx.require_role("admin", "compliance_manager", "auditor")
    posture = compute_posture(ctx.tenant_id)
    db.execute(
        """INSERT INTO posture_history
               (tenant_id, recorded_at, total_controls, ok_controls,
                needs_attention_controls, readiness_pct)
           VALUES (%s, %s, %s, %s, %s, %s)""",
        (
            ctx.tenant_id,
            _now(),
            posture.overall_controls,
            posture.overall_ok,
            posture.overall_needs_attention,
            posture.overall_readiness_pct,
        ),
    )
    return posture


@app.get("/api/v1/analytics/trend")
def control_trend(ctx: TenantContext = Depends(get_tenant_context)):
    ctx.require_role("admin", "compliance_manager", "auditor", "read_only")
    rows = db.execute(
        """SELECT date_trunc('day', tr.evaluated_at) AS day,
                  tr.status,
                  COUNT(*) AS count
           FROM test_result tr
           WHERE tr.tenant_id = %s
           GROUP BY date_trunc('day', tr.evaluated_at), tr.status
           ORDER BY day DESC, tr.status""",
        (ctx.tenant_id,),
    )
    return {"tenant_id": ctx.tenant_id, "trend": rows}


@app.get("/api/v1/scheduler/jobs")
def list_scheduler_jobs(ctx: TenantContext = Depends(get_tenant_context)):
    ctx.require_role("admin", "compliance_manager", "control_owner", "auditor", "read_only")
    integrations = db.execute(
        """SELECT id, name, connector, schedule, last_run_at, next_run_at,
                  'integration' AS job_type
           FROM integration
           WHERE tenant_id = %s
           ORDER BY next_run_at NULLS LAST""",
        (ctx.tenant_id,),
    )
    tests = db.execute(
        """SELECT id, name, resource_type, schedule, last_run_at, next_run_at,
                  'test' AS job_type
           FROM test
           WHERE tenant_id = %s AND active = true
           ORDER BY next_run_at NULLS LAST""",
        (ctx.tenant_id,),
    )
    return {"tenant_id": ctx.tenant_id, "integrations": integrations, "tests": tests}


@app.post("/api/v1/scheduler/trigger/{job_type}/{job_id}")
def trigger_scheduler_job(
    job_type: str,
    job_id: str,
    ctx: TenantContext = Depends(get_tenant_context),
):
    ctx.require_role("admin", "compliance_manager", "control_owner")
    result = trigger_job_now(db, job_type, job_id)
    return result


@app.post("/api/v1/scheduler/tick")
def scheduler_tick(ctx: TenantContext = Depends(get_tenant_context)):
    ctx.require_role("admin", "compliance_manager", "control_owner")
    return run_due_jobs(db)


@app.post("/api/v1/ai/suggest-remediation")
def ai_suggest_remediation(
    test_result_id: str | None = Query(default=None),
    control_id: str | None = Query(default=None),
    finding: str | None = Query(default=None),
    ctx: TenantContext = Depends(get_tenant_context),
):
    ctx.require_role("admin", "compliance_manager", "control_owner", "auditor", "read_only")
    suggestions = [
        "Review the affected resource configuration and align it with the control requirement.",
        "Enable the missing setting or permission and verify with a follow-up test run.",
        "Rotate any exposed credentials and update evidence records.",
        "Add a compensating control or policy exception if remediation is not immediate.",
    ]
    return {
        "model": "mock-llm",
        "suggestions": suggestions,
        "test_result_id": test_result_id,
        "control_id": control_id,
        "finding": finding,
    }
