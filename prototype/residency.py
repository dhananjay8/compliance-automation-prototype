"""Data residency / regional boundary enforcement (Phase 4 multi-tenancy item).

A full physical multi-region database cluster is out of scope for this
prototype's single-Postgres-instance dev/test environment. Instead this
module implements the two things that make data residency *observable and
enforceable* end-to-end:

1. Every resource/evidence row is tagged with the owning tenant's region at
   write time (see ``worker.py``).
2. Requests that explicitly declare a required region via the ``X-Region``
   header are rejected with 403 if the target tenant's home region differs,
   simulating a regional-cell gateway boundary.
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from db import db


async def region_enforcement_middleware(request: Request, call_next):
    region_header = request.headers.get("x-region")
    tenant_id = request.headers.get("x-tenant-id")
    if region_header and tenant_id and db._pool is not None:
        try:
            row = db.fetchone("SELECT region FROM tenant WHERE id = %s", (tenant_id,))
        except Exception:
            row = None
        if row and row.get("region") and row["region"] != region_header:
            return JSONResponse(
                status_code=403,
                content={
                    "detail": (
                        f"Cross-region access denied: tenant home region is "
                        f"'{row['region']}', request required '{region_header}'"
                    )
                },
            )
    return await call_next(request)


def data_residency_report(tenant_id: str) -> dict[str, Any]:
    tenant = db.fetchone("SELECT region FROM tenant WHERE id = %s", (tenant_id,))
    resource_counts = db.execute(
        """SELECT COALESCE(region, 'untagged') as region, COUNT(*) as count
           FROM resource WHERE tenant_id = %s GROUP BY region""",
        (tenant_id,),
    )
    evidence_counts = db.execute(
        """SELECT COALESCE(region, 'untagged') as region, COUNT(*) as count
           FROM evidence WHERE tenant_id = %s GROUP BY region""",
        (tenant_id,),
    )
    return {
        "tenant_id": tenant_id,
        "home_region": (tenant or {}).get("region") or "us",
        "resources_by_region": resource_counts,
        "evidence_by_region": evidence_counts,
    }
