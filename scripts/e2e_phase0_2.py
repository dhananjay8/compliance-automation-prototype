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

    # Bulk multi-framework mapping
    mappings_res = client.post(
        f"/api/v1/controls/{control_id}/mappings",
        headers=_headers(user_id),
        json=[
            {"framework_code": "ISO27001", "requirement_text": "Access control policy"},
            {"framework_code": "GDPR", "requirement_text": "Data protection by design"},
        ],
    )
    _expect_ok(mappings_res, "bulk create mappings")
    mapping_ids = mappings_res.json().get("created_mapping_ids", [])
    assert len(mapping_ids) == 2, "expected 2 mappings"

    list_mappings_res = client.get(
        f"/api/v1/controls/{control_id}/mappings",
        headers=_headers(user_id),
    )
    _expect_ok(list_mappings_res, "list control mappings")
    mapped_codes = {m["framework_code"] for m in list_mappings_res.json()}
    assert mapped_codes.issuperset({"ISO27001", "GDPR"}), "expected new mappings"

    # Cross-framework control lookup
    fw_controls_res = client.get(
        "/api/v1/frameworks/SOC2/controls",
        headers=_headers(user_id),
    )
    _expect_ok(fw_controls_res, "framework controls")
    assert any(c["code"] == "CC-PHASE2-001" for c in fw_controls_res.json())

    # Custom test for the control
    test_res = client.post(
        f"/api/v1/controls/{control_id}/tests",
        headers=_headers(user_id),
        json={
            "name": "Phase 2 MFA test",
            "resource_type": "UserAccount",
            "rule": {"op": "eq", "path": ["mfa_enabled"], "value": True},
            "schedule": "0 * * * *",
            "common_control_ids": [control_id],
        },
    )
    _expect_ok(test_res, "create control test")
    created_test_id = test_res.json()["id"]

    control_tests_res = client.get(
        f"/api/v1/controls/{control_id}/tests",
        headers=_headers(user_id),
    )
    _expect_ok(control_tests_res, "list control tests")
    assert any(t["id"] == created_test_id for t in control_tests_res.json())

    # File upload for manual evidence
    upload_res = client.post(
        "/api/v1/evidence/upload",
        headers=_headers(user_id),
        files={"uploaded": ("phase2-evidence.txt", b"manual evidence file", "text/plain")},
    )
    _expect_ok(upload_res, "upload evidence file")
    storage_path = upload_res.json().get("storage_path")

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
            "storage_path": storage_path,
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

    # Phase 3: remediation workflow
    rem_res = client.post(
        "/api/v1/remediations",
        headers=_headers(user_id),
        params={
            "title": "Fix missing MFA",
            "description": "Ensure all users have MFA enabled",
            "assignee_email": "alice@example.com",
        },
    )
    _expect_ok(rem_res, "create remediation")
    rem_id = rem_res.json()["id"]

    status_res = client.post(
        f"/api/v1/remediations/{rem_id}/status",
        headers=_headers(user_id),
        params={"status": "in_progress"},
    )
    _expect_ok(status_res, "update remediation status")

    ticket_res = client.post(
        f"/api/v1/remediations/{rem_id}/ticket",
        headers=_headers(user_id),
        params={"ticket_id": "TICKET-123"},
    )
    _expect_ok(ticket_res, "attach remediation ticket")

    # Phase 3: access review campaign
    ar_res = client.post(
        "/api/v1/access-reviews",
        headers=_headers(user_id),
        params={"name": "Q3 Access Review", "due_date": "2025-12-31T00:00:00Z"},
    )
    _expect_ok(ar_res, "create access review")
    ar_id = ar_res.json()["id"]

    item_res = client.post(
        f"/api/v1/access-reviews/{ar_id}/items",
        headers=_headers(user_id),
        params={"user_email": "alice@example.com", "system": "AWS"},
    )
    _expect_ok(item_res, "add access review item")
    item_id = item_res.json()["id"]

    decide_res = client.post(
        f"/api/v1/access-reviews/{ar_id}/items/{item_id}/decide",
        headers=_headers(user_id),
        params={"decision": "approved", "notes": "access still needed"},
    )
    _expect_ok(decide_res, "decide access review item")

    # Phase 3: vendor risk questionnaire
    vendor_res = client.post(
        "/api/v1/vendors",
        headers=_headers(user_id),
        params={"name": "Cloud Vendor", "category": "cloud", "risk_level": "medium"},
    )
    _expect_ok(vendor_res, "create vendor")
    vendor_id = vendor_res.json()["id"]

    assessment_res = client.post(
        f"/api/v1/vendors/{vendor_id}/assessments",
        headers=_headers(user_id),
        params={"questionnaire": '{"q1": "Do you encrypt data at rest?"}'},
    )
    _expect_ok(assessment_res, "create vendor assessment")
    assessment_id = assessment_res.json()["id"]

    respond_res = client.post(
        f"/api/v1/vendors/{vendor_id}/assessments/{assessment_id}/respond",
        headers=_headers(user_id),
        params={"responses": '{"q1": "yes"}'},
    )
    _expect_ok(respond_res, "respond vendor assessment")

    # Phase 3: auditor portal / information requests
    audit_res = client.post(
        "/api/v1/audits",
        headers=_headers(user_id),
        params={"framework_code": "SOC2", "start_date": "2025-01-01", "end_date": "2025-12-31"},
    )
    _expect_ok(audit_res, "create audit")
    audit_id = audit_res.json()["id"]

    req_res = client.post(
        f"/api/v1/audits/{audit_id}/requests",
        headers=_headers(user_id),
        params={"request_text": "Provide MFA evidence"},
    )
    _expect_ok(req_res, "create audit request")
    req_id = req_res.json()["id"]

    resp_res = client.post(
        f"/api/v1/audits/{audit_id}/requests/{req_id}/respond",
        headers=_headers(user_id),
        params={"response_text": "Evidence attached"},
    )
    _expect_ok(resp_res, "respond audit request")

    accept_res = client.post(
        f"/api/v1/audits/{audit_id}/requests/{req_id}/status",
        headers=_headers(user_id),
        params={"status": "accepted"},
    )
    _expect_ok(accept_res, "accept audit request")

    # Phase 3: webhooks
    hook_res = client.post(
        "/api/v1/webhooks",
        headers=_headers(user_id),
        params={"url": "https://example.com/webhook", "events": "remediation.created,audit.created"},
    )
    _expect_ok(hook_res, "create webhook subscription")
    hook_id = hook_res.json()["id"]

    client.post(
        "/api/v1/audits",
        headers=_headers(user_id),
        params={"framework_code": "SOC2", "start_date": "2025-01-01", "end_date": "2025-12-31"},
    )

    deliveries_res = client.get(
        f"/api/v1/webhooks/{hook_id}/deliveries",
        headers=_headers(user_id),
    )
    _expect_ok(deliveries_res, "list webhook deliveries")
    assert len(deliveries_res.json()) >= 1, "expected webhook delivery records"

    print("Phase 0-3 E2E: all assertions passed")


if __name__ == "__main__":
    main()
