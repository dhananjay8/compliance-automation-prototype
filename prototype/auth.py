import os
from functools import lru_cache

from fastapi import Header, HTTPException, Request, status

from db import db


class TenantContext:
    def __init__(self, tenant_id: str, user_id: str | None, user_role: str | None) -> None:
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.user_role = user_role or "read_only"

    def require_role(self, *allowed: str) -> None:
        if self.user_role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role {self.user_role} is not allowed for this operation",
            )


@lru_cache(maxsize=1)
def _mock_auth() -> bool:
    return os.getenv("MOCK_AUTH", "").lower() in ("1", "true", "yes")


def _ensure_db() -> None:
    if db._pool is None:
        db.configure()


def _resolve_user(tenant_id: str, user_id: str | None, header_role: str | None) -> tuple[str | None, str]:
    if _mock_auth():
        return user_id, (header_role or "read_only")

    _ensure_db()

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-User-Id header",
        )

    row = db.fetchone(
        """SELECT id, role, active
           FROM "user"
           WHERE id = %s AND tenant_id = %s""",
        (user_id, tenant_id),
    )
    if not row:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unknown user or user does not belong to this tenant",
        )
    if not row.get("active"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is inactive",
        )
    return str(row["id"]), row["role"]


def get_tenant_context(
    request: Request,
    x_tenant_id: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
    x_user_role: str | None = Header(default=None),
) -> TenantContext:
    tenant_id = x_tenant_id or request.path_params.get("tenant_id")
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Tenant-Id header or tenant_id path parameter",
        )

    user_id, user_role = _resolve_user(tenant_id, x_user_id, x_user_role)
    return TenantContext(
        tenant_id=tenant_id,
        user_id=user_id,
        user_role=user_role,
    )


def require_admin_role(
    x_user_id: str | None = Header(default=None),
    x_user_role: str | None = Header(default=None),
) -> None:
    if _mock_auth():
        if (x_user_role or "") not in ("admin", "compliance_manager"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin or compliance manager role required",
            )
        return

    _ensure_db()
    if not x_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-User-Id header",
        )

    row = db.fetchone(
        """SELECT id FROM "user"
           WHERE id = %s AND active = true AND role = 'admin'""",
        (x_user_id,),
    )
    if not row:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
        )
