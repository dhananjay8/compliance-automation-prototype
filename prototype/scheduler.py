"""Lightweight scheduler for recurring integration syncs and test runs.

Uses APScheduler only for the ticker; actual job definitions and next-run times are
stored in PostgreSQL so they survive process restarts. The scheduler is optional and
only starts when ``ENABLE_SCHEDULER=1`` is set in the environment.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

from croniter import croniter
from db import Database

ENABLE_SCHEDULER = os.getenv("ENABLE_SCHEDULER", "").lower() in ("1", "true", "yes")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _next_run(cron_string: str | None, base: datetime | None = None) -> datetime:
    base = base or _now()
    expr = cron_string or "0 * * * *"
    try:
        return croniter(expr, base).get_next(datetime)
    except Exception:
        return base.replace(second=0, microsecond=0) + timedelta(hours=1)


def _run_due_integrations(db: Database) -> set[str]:
    touched: set[str] = set()
    rows = db.execute(
        """SELECT * FROM integration
           WHERE status != 'disabled'
             AND (next_run_at IS NULL OR next_run_at <= %s)
           ORDER BY next_run_at NULLS FIRST""",
        (_now(),),
    )
    if not rows:
        return touched
    from worker import SyncWorker

    worker = SyncWorker(db)
    for integration in rows:
        integration_id = str(integration["id"])
        tenant_id = str(integration["tenant_id"])
        try:
            worker.sync_integration(dict(integration))
        except Exception:
            # Log failure but keep ticking other jobs
            pass
        db.execute(
            """UPDATE integration
               SET last_run_at = %s, next_run_at = %s
               WHERE id = %s""",
            (_now(), _next_run(integration.get("schedule")), integration_id),
        )
        touched.add(tenant_id)
    return touched


def _run_due_tests(db: Database) -> set[str]:
    touched: set[str] = set()
    rows = db.execute(
        """SELECT * FROM test
           WHERE active = true
             AND (next_run_at IS NULL OR next_run_at <= %s)
           ORDER BY next_run_at NULLS FIRST""",
        (_now(),),
    )
    if not rows:
        return touched
    from worker import run_test

    for test in rows:
        test_id = str(test["id"])
        tenant_id = str(test["tenant_id"])
        try:
            run_test(db, dict(test))
        except Exception:
            pass
        db.execute(
            """UPDATE test
               SET last_run_at = %s, next_run_at = %s
               WHERE id = %s""",
            (_now(), _next_run(test.get("schedule")), test_id),
        )
        touched.add(tenant_id)
    return touched


def _record_posture_for_tenants(db: Database, tenant_ids: set[str]) -> None:
    if not tenant_ids:
        return
    from analytics import compute_posture

    for tenant_id in tenant_ids:
        try:
            posture = compute_posture(tenant_id)
            db.execute(
                """INSERT INTO posture_history
                       (tenant_id, recorded_at, total_controls, ok_controls,
                        needs_attention_controls, readiness_pct)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (
                    tenant_id,
                    _now(),
                    posture["overall_controls"],
                    posture["overall_ok"],
                    posture["overall_needs_attention"],
                    posture["overall_readiness_pct"],
                ),
            )
        except Exception:
            pass


def run_due_jobs(db: Database) -> dict[str, Any]:
    """Execute all due integrations and tests and record posture snapshots."""
    touched: set[str] = set()
    touched |= _run_due_integrations(db)
    touched |= _run_due_tests(db)
    _record_posture_for_tenants(db, touched)
    return {"ran_integrations": len(touched), "timestamp": _now().isoformat()}


def trigger_job_now(db: Database, job_type: str, job_id: str) -> dict[str, Any]:
    """Run a single integration or test immediately, independent of schedule."""
    if job_type == "integration":
        row = db.fetchone("SELECT * FROM integration WHERE id = %s", (job_id,))
        if not row:
            raise ValueError("integration not found")
        from worker import SyncWorker

        SyncWorker(db).sync_integration(dict(row))
        db.execute(
            "UPDATE integration SET last_run_at = %s, next_run_at = %s WHERE id = %s",
            (_now(), _next_run(row.get("schedule")), job_id),
        )
        return {"id": job_id, "type": "integration", "ran_at": _now().isoformat()}
    if job_type == "test":
        row = db.fetchone("SELECT * FROM test WHERE id = %s", (job_id,))
        if not row:
            raise ValueError("test not found")
        from worker import run_test

        run_test(db, dict(row))
        db.execute(
            "UPDATE test SET last_run_at = %s, next_run_at = %s WHERE id = %s",
            (_now(), _next_run(row.get("schedule")), job_id),
        )
        return {"id": job_id, "type": "test", "ran_at": _now().isoformat()}
    raise ValueError("job_type must be 'integration' or 'test'")


class ComplianceScheduler:
    """Thin wrapper around APScheduler that calls run_due_jobs every minute."""

    def __init__(self, db: Database) -> None:
        self.db = db
        self._scheduler: Any | None = None

    def start(self) -> None:
        if not ENABLE_SCHEDULER:
            return
        from apscheduler.schedulers.background import BackgroundScheduler

        self._scheduler = BackgroundScheduler(timezone="UTC")
        self._scheduler.add_job(
            self._tick,
            "interval",
            seconds=int(os.getenv("SCHEDULER_INTERVAL_SECONDS", "60")),
            id="compliance_tick",
            replace_existing=True,
        )
        self._scheduler.start()

    def shutdown(self, wait: bool = True) -> None:
        if self._scheduler:
            self._scheduler.shutdown(wait=wait)
            self._scheduler = None

    def _tick(self) -> None:
        try:
            run_due_jobs(self.db)
        except Exception:
            # Prevent a single DB hiccup from killing the scheduler thread.
            pass
