"""Posture and readiness analytics shared by the API and scheduler."""

from __future__ import annotations

from typing import Any

from db import db
from models import FrameworkReadiness, PostureSummary


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


def compute_posture(tenant_id: str) -> PostureSummary:
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
