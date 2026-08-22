"""Drift detection engine.

Compares the current resource snapshot for an integration against the previously
stored baseline and records added/removed/changed events. The baseline is updated
after each comparison so only true changes generate drift records.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from db import Database


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _severity(resource_type: str, drift_type: str, data: dict[str, Any] | None) -> str:
    rt = (resource_type or "").lower()
    if drift_type == "removed":
        return "medium"
    if drift_type == "added":
        return "low"
    if any(k in rt for k in ("user", "account", "identity")):
        return "high"
    if "bucket" in rt or "storage" in rt or "compute" in rt:
        # surface public/unencrypted storage or disabled encryption
        if data:
            if data.get("public_access") is True:
                return "critical"
            if data.get("encrypted_at_rest") is False:
                return "high"
            if data.get("mfa_enabled") is False:
                return "high"
        return "high"
    return "medium"


def _summary(drift_type: str, resource_type: str, external_id: str) -> str:
    return f"{drift_type.capitalize()} {resource_type} resource {external_id}"


def detect_drift_for_integration(
    db: Database,
    integration_id: str,
    tenant_id: str,
) -> list[dict[str, Any]]:
    """Detect drift for all resources belonging to an integration.

    On the first run for the integration the baseline is seeded and no drift
    records are emitted. Subsequent runs compare hashes and emit drift records.
    """
    current_rows = db.execute(
        """SELECT r.id as resource_id, r.resource_type_id, r.external_id, r.data, r.hash,
                  rt.name as resource_type
           FROM resource r
           JOIN resource_type rt ON rt.id = r.resource_type_id
           WHERE r.tenant_id = %s AND r.integration_id = %s""",
        (tenant_id, integration_id),
    )
    current_rows = [dict(r) for r in current_rows]

    baseline_rows = db.execute(
        """SELECT id, resource_type_id, external_id, data, hash
           FROM resource_baseline
           WHERE tenant_id = %s AND integration_id = %s""",
        (tenant_id, integration_id),
    )
    baseline_rows = [dict(r) for r in baseline_rows]
    baseline_by_ext = {r["external_id"]: r for r in baseline_rows}

    drift_records: list[dict[str, Any]] = []

    # First time we see this integration: seed baseline silently.
    if not baseline_by_ext:
        for row in current_rows:
            db.execute(
                """INSERT INTO resource_baseline
                       (tenant_id, integration_id, resource_type_id, external_id, data, hash)
                   VALUES (%s, %s, %s, %s, %s, %s)
                   ON CONFLICT (tenant_id, integration_id, external_id)
                   DO UPDATE SET data = EXCLUDED.data,
                                 hash = EXCLUDED.hash,
                                 updated_at = %s""",
                (
                    tenant_id,
                    integration_id,
                    row["resource_type_id"],
                    row["external_id"],
                    json.dumps(row["data"]),
                    row["hash"],
                    _now(),
                ),
            )
        return drift_records

    current_external_ids = set()
    for row in current_rows:
        external_id = row["external_id"]
        current_external_ids.add(external_id)
        baseline = baseline_by_ext.get(external_id)
        if not baseline:
            # Added resource
            db.execute(
                """INSERT INTO resource_baseline
                       (tenant_id, integration_id, resource_type_id, external_id, data, hash)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (
                    tenant_id,
                    integration_id,
                    row["resource_type_id"],
                    external_id,
                    json.dumps(row["data"]),
                    row["hash"],
                ),
            )
            drift_id = str(__import__("uuid").uuid4())
            db.execute(
                """INSERT INTO drift_detection
                       (id, tenant_id, integration_id, resource_id, resource_type,
                        external_id, drift_type, severity, summary, previous_hash, current_hash)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    drift_id,
                    tenant_id,
                    integration_id,
                    row["resource_id"],
                    row["resource_type"],
                    external_id,
                    "added",
                    _severity(row["resource_type"], "added", row["data"]),
                    _summary("added", row["resource_type"], external_id),
                    None,
                    row["hash"],
                ),
            )
            drift_records.append({"id": drift_id, "drift_type": "added"})
        elif baseline["hash"] != row["hash"]:
            # Changed resource
            db.execute(
                """UPDATE resource_baseline
                   SET data = %s, hash = %s, updated_at = %s
                   WHERE id = %s""",
                (json.dumps(row["data"]), row["hash"], _now(), baseline["id"]),
            )
            drift_id = str(__import__("uuid").uuid4())
            db.execute(
                """INSERT INTO drift_detection
                       (id, tenant_id, integration_id, resource_id, resource_type,
                        external_id, drift_type, severity, summary, previous_hash, current_hash)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    drift_id,
                    tenant_id,
                    integration_id,
                    row["resource_id"],
                    row["resource_type"],
                    external_id,
                    "changed",
                    _severity(row["resource_type"], "changed", row["data"]),
                    _summary("changed", row["resource_type"], external_id),
                    baseline["hash"],
                    row["hash"],
                ),
            )
            drift_records.append({"id": drift_id, "drift_type": "changed"})

    # Removed resources
    for external_id, baseline in baseline_by_ext.items():
        if external_id not in current_external_ids:
            db.execute(
                "DELETE FROM resource_baseline WHERE id = %s",
                (baseline["id"],),
            )
            drift_id = str(__import__("uuid").uuid4())
            db.execute(
                """INSERT INTO drift_detection
                       (id, tenant_id, integration_id, resource_id, resource_type,
                        external_id, drift_type, severity, summary, previous_hash, current_hash)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    drift_id,
                    tenant_id,
                    integration_id,
                    None,
                    "unknown",
                    external_id,
                    "removed",
                    _severity("unknown", "removed", None),
                    _summary("removed", "unknown", external_id),
                    baseline["hash"],
                    None,
                ),
            )
            drift_records.append({"id": drift_id, "drift_type": "removed"})

    return drift_records


def list_drift(
    db: Database,
    tenant_id: str,
    acknowledged: bool | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    params: list[Any] = [tenant_id]
    sql = """SELECT d.*, i.name as integration_name
             FROM drift_detection d
             JOIN integration i ON i.id = d.integration_id
             WHERE d.tenant_id = %s"""
    if acknowledged is not None:
        sql += " AND d.acknowledged = %s"
        params.append(acknowledged)
    sql += " ORDER BY d.created_at DESC LIMIT %s"
    params.append(limit)
    return [dict(r) for r in db.execute(sql, params)]


def acknowledge_drift(db: Database, drift_id: str, tenant_id: str) -> bool:
    db.execute(
        "UPDATE drift_detection SET acknowledged = true WHERE id = %s AND tenant_id = %s",
        (drift_id, tenant_id),
    )
    return True
