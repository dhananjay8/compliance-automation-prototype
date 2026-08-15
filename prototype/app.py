import json
import os
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, status

from auth import TenantContext, get_tenant_context, require_admin_role
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

app = FastAPI(title="Compliance Automation Prototype", version="0.1.0")
worker = SyncWorker(db)


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
         json.dumps(payload.config), json.dumps({}), "connected"),
    )
    return _integration_row(integration_id)


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


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


@app.get("/api/v1/dashboards/posture", response_model=PostureSummary)
def dashboard_posture(
    ctx: TenantContext = Depends(get_tenant_context),
):
    ctx.require_role("admin", "compliance_manager", "control_owner", "auditor", "read_only")
    return _compute_posture(ctx.tenant_id)


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


def _integration_row(integration_id: str) -> IntegrationOut:
    row = db.fetchone("SELECT * FROM integration WHERE id = %s", (integration_id,))
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
