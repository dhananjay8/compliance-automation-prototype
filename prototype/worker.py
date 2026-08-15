import hashlib
import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from db import Database
from engine import evaluate_rule
from models import TestRunSummary


class SyncWorker:
    def __init__(self, database: Database) -> None:
        self.db = database

    def sync_integration(self, integration: dict[str, Any], triggered_by: str | None = None) -> str:
        tenant_id = integration["tenant_id"]
        integration_id = integration["id"]
        connector = integration["connector"]
        job_id = str(uuid.uuid4())

        self.db.execute(
            """INSERT INTO sync_job (id, tenant_id, integration_id, triggered_by, mode, status, started_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (job_id, tenant_id, integration_id, triggered_by, "manual", "running", _now()),
        )

        resources = self._mock_resources_for_connector(connector)
        resource_type_ids = self._load_resource_type_map(tenant_id)
        synced_types: set[str] = set()

        for r in resources:
            resource_type = r["resource_type"]
            if resource_type not in resource_type_ids:
                continue
            rt_id = resource_type_ids[resource_type]
            synced_types.add(resource_type)

            data = r.get("data", {})
            collected_at = _parse_time(r.get("collected_at")) or _now()
            data_hash = _hash(data)
            external_id = r.get("external_id", r["id"])

            self.db.execute(
                """INSERT INTO resource (id, tenant_id, integration_id, resource_type_id, external_id, data, collected_at, hash)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (tenant_id, integration_id, external_id)
                   DO UPDATE SET data = EXCLUDED.data,
                                 collected_at = EXCLUDED.collected_at,
                                 hash = EXCLUDED.hash""",
                (str(uuid.uuid5(uuid.NAMESPACE_URL, f"{tenant_id}:{integration_id}:{external_id}")),
                 tenant_id, integration_id, rt_id, external_id,
                 json.dumps(data), collected_at, data_hash),
            )

        self.db.execute(
            """UPDATE integration
               SET last_sync_at = %s, status = %s
               WHERE id = %s""",
            (_now(), "connected", integration_id),
        )

        # Run tests for every resource type touched by this sync
        if synced_types:
            tests = self.db.execute(
                "SELECT * FROM test WHERE tenant_id = %s AND resource_type = ANY(%s) AND active = true",
                (tenant_id, list(synced_types)),
            )
            for test in tests:
                run_test(self.db, dict(test))

        self.db.execute(
            """UPDATE sync_job
               SET status = %s, completed_at = %s
               WHERE id = %s""",
            ("completed", _now(), job_id),
        )
        return job_id

    def _mock_resources_for_connector(self, connector: str) -> list[dict[str, Any]]:
        """Return sample resources whose source integration matches the connector name."""
        root = _repo_root()
        sample_path = root / "data" / "sample-resources.json"
        if not sample_path.exists():
            return []
        resources = json.loads(sample_path.read_text())
        matches = [
            r for r in resources
            if connector.lower() in r.get("integration_id", "").lower()
        ]
        if not matches and connector == "aws":
            # synthesize a small AWS sample so the demo still shows a resource
            matches = [{
                "id": "res-aws-s3-001",
                "integration_id": "int-aws-001",
                "resource_type": "StorageBucket",
                "external_id": "acme-public-assets",
                "data": {
                    "name": "acme-public-assets",
                    "public_access": True,
                    "encrypted_at_rest": True,
                    "region": "us-east-1",
                },
                "collected_at": _now().isoformat().replace("+", "Z") if False else "2024-06-20T12:00:00Z",
            }]
        return matches

    def _load_resource_type_map(self, tenant_id: str) -> dict[str, str]:
        rows = self.db.execute(
            "SELECT id, name FROM resource_type WHERE tenant_id = %s",
            (tenant_id,),
        )
        return {r["name"]: r["id"] for r in rows}


def run_test(db: Database, test: dict[str, Any]) -> TestRunSummary:
    tenant_id = test["tenant_id"]
    test_id = test["id"]
    raw_rule = test["rule"]
    rule = json.loads(raw_rule) if isinstance(raw_rule, str) else raw_rule

    run_id = str(uuid.uuid4())
    db.execute(
        """INSERT INTO test_run (id, tenant_id, test_id, status, started_at)
           VALUES (%s, %s, %s, %s, %s)""",
        (run_id, tenant_id, test_id, "running", _now()),
    )

    resource_type = test["resource_type"]
    resources = db.execute(
        """SELECT r.*, rt.name as resource_type_name
           FROM resource r
           JOIN resource_type rt ON rt.id = r.resource_type_id
           WHERE r.tenant_id = %s AND rt.name = %s""",
        (tenant_id, resource_type),
    )

    ok = 0
    needs_attention = 0
    invalid = 0

    for resource in resources:
        status, reason = evaluate_rule(rule, dict(resource.get("data", {})))
        if status == "OK":
            ok += 1
        elif status == "NEEDS_ATTENTION":
            needs_attention += 1
        else:
            invalid += 1

        result_id = str(uuid.uuid4())
        db.execute(
            """INSERT INTO test_result (id, tenant_id, test_run_id, resource_id, status, reason, evaluated_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (result_id, tenant_id, run_id, resource["id"], status, reason, _now()),
        )

        evidence_type = "api_response" if status == "OK" else "snapshot"
        expires_at = _now() + timedelta(days=7)
        db.execute(
            """INSERT INTO evidence (id, tenant_id, test_result_id, evidence_type, description, collected_at, expires_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (str(uuid.uuid4()), tenant_id, result_id, evidence_type, reason, _now(), expires_at),
        )

    db.execute(
        """UPDATE test_run
           SET status = %s, completed_at = %s
           WHERE id = %s""",
        ("completed", _now(), run_id),
    )

    return TestRunSummary(
        test_run_id=run_id,
        test_id=test_id,
        status="completed",
        total=len(resources),
        ok=ok,
        needs_attention=needs_attention,
        invalid=invalid,
    )


def _repo_root() -> Path:
    override = os.getenv("COMPLIANCE_PROTOTYPE_ROOT")
    if override:
        return Path(override)
    return Path(__file__).resolve().parent.parent


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _hash(data: dict[str, Any]) -> str:
    payload = json.dumps(data, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()[:32]
