import os
import sys
from types import SimpleNamespace

os.environ["MOCK_AUTH"] = "1"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import auth


def _request(tenant_id: str | None = None):
    return SimpleNamespace(
        path_params={"tenant_id": tenant_id} if tenant_id else {},
        headers={},
    )


def test_tenant_context_role_enforcement():
    ctx = auth.TenantContext("t1", "u1", "read_only")
    ctx.require_role("read_only")
    try:
        ctx.require_role("admin")
    except Exception:
        return
    raise AssertionError("Expected role check to fail")


def test_get_tenant_context_mock_uses_header():
    ctx = auth.get_tenant_context(
        _request(),
        x_tenant_id="t1",
        x_user_id="u1",
        x_user_role="admin",
    )
    assert ctx.tenant_id == "t1"
    assert ctx.user_id == "u1"
    assert ctx.user_role == "admin"


def test_get_tenant_context_no_tenant_raises():
    try:
        auth.get_tenant_context(_request(), x_tenant_id=None)
    except Exception:
        return
    raise AssertionError("Expected missing tenant to raise")


def test_require_admin_role_mock():
    auth.require_admin_role(request=_request(), x_user_id="u1", x_user_role="admin")


def test_require_admin_role_rejects_non_admin():
    try:
        auth.require_admin_role(request=_request(), x_user_id="u1", x_user_role="read_only")
    except Exception:
        return
    raise AssertionError("Expected non-admin to be rejected")
