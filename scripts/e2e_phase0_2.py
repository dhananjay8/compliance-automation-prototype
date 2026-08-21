#!/usr/bin/env python3
"""End-to-end smoke test for roadmap Phase 0-2 endpoints.

Assumes a running FastAPI backend (e.g. uvicorn) and a seeded Postgres.
Set BASE_URL, TENANT_ID, PGPORT, etc via env.
"""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "prototype"))

import httpx
from db import db

TENANT_ID = os.getenv("E2E_TENANT_ID", "00000000-0000-0000-0000-000000000001")
BASE_URL = os.getenv("E2E_BASE_URL", "http://localhost:8002")
DEFAULT_ROLE = os.getenv("E2E_ROLE", "admin")


def _headers(user_id: str, role: str = DEFAULT_ROLE) -> dict[str, str]:
    return {
        "X-Tenant-Id": TENANT_ID,
        "X-User-Id": user_id,
        "X-User-Role": role,
    }


def _get_user_id() -> str:
    db.configure()
    row = db.fetchone(
        'SELECT id FROM "user" WHERE tenant_id = %s AND role = %s LIMIT 1',
        (TENANT_ID, DEFAULT_ROLE),
    )
    if not row:
        raise RuntimeError("No admin user found in seeded DB")
    return str(row["id"])


def _expect_ok(res: httpx.Response, step: str) -> None:
    if res.status_code >= 400:
        raise AssertionError(f"{step} failed: {res.status_code} {res.text[:200]}")


def main() -> None:
    user_id = _get_user_id()
    client = httpx.Client(base_url=BASE_URL, timeout=60)

    # Phase 0: JWT token
    token_res = client.post(
        "/api/v1/auth/token",
        params={"tenant_id": TENANT_ID, "user_id": user_id, "role": "admin"},
    )
    _expect_ok(token_res, "auth token")
    token = token_res.json()["token"]
    assert isinstance(token, str) and token.count(".") == 2, "token should be a JWT"

    # Use token for a Phase 1 call
    jwt_headers = {"Authorization": f"Bearer {token}"}
    controls_res = client.get("/api/v1/controls", headers=jwt_headers)
    _expect_ok(controls_res, "list controls with JWT")

    # Phase 1: integration health + sync
    list_res = client.get("/api/v1/integrations", headers=_headers(user_id))
    _expect_ok(list_res, "list integrations")
    integrations = list_res.json()
    assert integrations, "no integrations seeded"
    supported = [i for i in integrations if i.get("connector", "").lower() in ("aws", "okta")]
    assert supported, "no aws/okta integration in seed"
    integration = supported[0]
    integration_id = integration["id"]

    health_res = client.get(
        f"/api/v1/integrations/{integration_id}/health",
        headers=_headers(user_id),
    )
    _expect_ok(health_res, "integration health")
    assert health_res.json().get("configured") in (True, False)

    # Get single integration
    get_res = client.get(
        f"/api/v1/integrations/{integration_id}",
        headers=_headers(user_id),
    )
    _expect_ok(get_res, "get integration")
    assert get_res.json().get("status")

    # Test connector credentials (Phase 1 full-proof)
    test_res = client.post(
        f"/api/v1/integrations/{integration_id}/test",
        headers=_headers(user_id),
    )
    _expect_ok(test_res, "test integration")
    assert test_res.json().get("configured") in (True, False)

    sync_res = client.post(
        f"/api/v1/integrations/{integration_id}/sync",
        headers=_headers(user_id),
    )
    _expect_ok(sync_res, "sync integration")
    sync_job_id = sync_res.json().get("sync_job_id")
    assert sync_job_id

    # Poll sync job status
    job_res = client.get(
        f"/api/v1/sync-jobs/{sync_job_id}",
        headers=_headers(user_id),
    )
    _expect_ok(job_res, "get sync job")
    assert job_res.json().get("status") in ("completed", "running", "pending", "failed")

    jobs_res = client.get(
        f"/api/v1/integrations/{integration_id}/sync-jobs",
        headers=_headers(user_id),
    )
    _expect_ok(jobs_res, "list sync jobs")
    assert any(j["id"] == sync_job_id for j in jobs_res.json())

    resources_res = client.get("/api/v1/resources", headers=_headers(user_id))
    _expect_ok(resources_res, "list resources")
    resources = resources_res.json()
    assert resources, "expected resources after sync"
    assert any(r.get("resource_type_name") == "UserAccount" for r in resources), "expected UserAccount"

    # Phase 1: dashboards
    posture_res = client.get("/api/v1/dashboards/posture", headers=_headers(user_id))
    _expect_ok(posture_res, "dashboard posture")

    failures_res = client.get("/api/v1/dashboards/failures", headers=_headers(user_id))
    _expect_ok(failures_res, "dashboard failures")

    # Phase 2: custom control + framework mapping
    control_res = client.post(
        "/api/v1/controls",
        headers=_headers(user_id),
        params={
            "code": "CC-PHASE2-001",
            "statement": "Phase 2 custom control",
            "owner_email": "alice@example.com",
            "domain": "Access Control",
            "framework_code": "SOC2",
            "section_code": "CC6.1",
            "requirement_text": "MFA is required for all access",
        },
    )
    _expect_ok(control_res, "create control")
    control_id = control_res.json()["id"]

    frameworks_res = client.get(
        f"/api/v1/controls/{control_id}/frameworks",
        headers=_headers(user_id),
    )
    _expect_ok(frameworks_res, "control frameworks")
    assert frameworks_res.json(), "expected at least one framework mapping"

    # Phase 2: policy + ack
    policy_res = client.post(
        "/api/v1/policies",
        headers=_headers(user_id),
        params={"title": "Acceptable Use", "content": "Use systems responsibly", "version": "1.0"},
    )
    _expect_ok(policy_res, "create policy")
    policy_id = policy_res.json()["id"]

    policies_res = client.get("/api/v1/policies", headers=_headers(user_id))
    _expect_ok(policies_res, "list policies")
    assert any(p["id"] == policy_id for p in policies_res.json()), "new policy not found"

    ack_res = client.post(
        f"/api/v1/policies/{policy_id}/acknowledge",
        headers=_headers(user_id),
    )
    _expect_ok(ack_res, "acknowledge policy")

    # Phase 2: manual evidence attached to an existing test result
    evidence_list_res = client.get("/api/v1/evidence", headers=_headers(user_id))
    _expect_ok(evidence_list_res, "list evidence")
    existing = evidence_list_res.json()
    assert existing, "expected existing evidence after sync"
    evidence_id = existing[0]["id"]

    evidence_detail_res = client.get(
        f"/api/v1/evidence/{evidence_id}",
        headers=_headers(user_id),
    )
    _expect_ok(evidence_detail_res, "evidence detail")
    test_result_id = evidence_detail_res.json()["test_result_id"]

    new_evidence_res = client.post(
        "/api/v1/evidence",
        headers=_headers(user_id),
        params={
            "test_result_id": test_result_id,
            "evidence_type": "document",
            "description": "Phase 2 manual evidence upload",
        },
    )
    _expect_ok(new_evidence_res, "create manual evidence")

    # Phase 2: RAG query
    rag_res = client.post(
        "/api/v1/rag/query",
        headers=_headers(user_id),
        json={"query": "Which controls are currently failing?"},
    )
    _expect_ok(rag_res, "rag query")
    assert "answer" in rag_res.json() or "not_found" in rag_res.json()

    print("Phase 0-2 E2E: all assertions passed")


if __name__ == "__main__":
    main()
