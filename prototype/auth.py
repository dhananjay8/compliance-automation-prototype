from fastapi import Header, HTTPException, Request, status


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
    return TenantContext(
        tenant_id=tenant_id,
        user_id=x_user_id,
        user_role=x_user_role,
    )


def require_admin_role(x_user_role: str | None = Header(default=None)) -> None:
    if x_user_role not in ("admin", "compliance_manager"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin or compliance manager role required",
        )
