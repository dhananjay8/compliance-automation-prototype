"""Distributed job queue for integration syncs and test runs (Phase 4).

Uses Redis + RQ when ``REDIS_URL`` (or ``ENABLE_QUEUE=1`` with default
``redis://localhost:6379/0``) is configured, so multiple worker processes can
consume sync/test jobs concurrently instead of running them in the FastAPI
request thread. When Redis/RQ is not available the caller should fall back to
running the job in-process -- every ``enqueue_*`` function returns
``{"queued": False}`` in that case so callers can degrade gracefully.
"""

from __future__ import annotations

import os
from typing import Any

QUEUE_NAME = "compliance-jobs"
ENABLE_QUEUE = os.getenv("ENABLE_QUEUE", "").lower() in ("1", "true", "yes")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")


def _get_queue():
    if not ENABLE_QUEUE:
        return None
    try:
        import redis
        from rq import Queue

        conn = redis.from_url(REDIS_URL, socket_connect_timeout=2)
        conn.ping()
        return Queue(QUEUE_NAME, connection=conn)
    except Exception:
        return None


def run_sync_job(integration_id: str, tenant_id: str, triggered_by: str | None = None) -> str:
    """RQ job target: configure a fresh DB connection and run the sync in-process.

    This runs inside the worker process (see ``queue_worker.py``), not the
    FastAPI request thread.
    """
    from db import Database
    from worker import SyncWorker

    worker_db = Database()
    worker_db.configure()
    integration = worker_db.fetchone(
        "SELECT * FROM integration WHERE id = %s AND tenant_id = %s",
        (integration_id, tenant_id),
    )
    if not integration:
        return "integration-not-found"
    return SyncWorker(worker_db).sync_integration(dict(integration), triggered_by=triggered_by)


def run_test_job(test_id: str, tenant_id: str) -> str:
    from db import Database
    from worker import run_test

    worker_db = Database()
    worker_db.configure()
    test = worker_db.fetchone(
        "SELECT * FROM test WHERE id = %s AND tenant_id = %s",
        (test_id, tenant_id),
    )
    if not test:
        return "test-not-found"
    summary = run_test(worker_db, dict(test))
    return summary.test_run_id


def enqueue_sync(integration_id: str, tenant_id: str, triggered_by: str | None = None) -> dict[str, Any]:
    queue = _get_queue()
    if queue is None:
        return {"queued": False}
    job = queue.enqueue(run_sync_job, integration_id, tenant_id, triggered_by)
    return {"queued": True, "job_id": job.id}


def enqueue_test_run(test_id: str, tenant_id: str) -> dict[str, Any]:
    queue = _get_queue()
    if queue is None:
        return {"queued": False}
    job = queue.enqueue(run_test_job, test_id, tenant_id)
    return {"queued": True, "job_id": job.id}


def queue_status() -> dict[str, Any]:
    queue = _get_queue()
    if queue is None:
        return {"enabled": ENABLE_QUEUE, "connected": False, "pending_jobs": 0}
    try:
        return {
            "enabled": True,
            "connected": True,
            "pending_jobs": len(queue),
            "redis_url": REDIS_URL,
        }
    except Exception as exc:
        return {"enabled": True, "connected": False, "error": str(exc)}
