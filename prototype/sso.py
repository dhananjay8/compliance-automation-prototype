"""OIDC-based SSO login and SCIM user provisioning (Phase 0 production-auth item).

Implements a real OIDC authorization-code flow against any standards-compliant
identity provider (Okta, Azure AD, Google, Auth0, etc.):

1. ``build_authorize_url`` fetches the provider's discovery document and
   builds the ``/authorize`` redirect URL.
2. ``exchange_code_for_token`` exchanges the returned ``code`` for tokens,
   verifies the ``id_token`` signature against the provider's live JWKS
   (via ``PyJWKClient``), and provisions/updates the local user record before
   issuing this platform's own JWT (reusing ``auth.issue_token``).

SCIM (``/scim/v2/Users``) provides minimal user provisioning (create, list,
deactivate) authenticated with a per-tenant bearer token, matching the SCIM
2.0 core user model closely enough for basic IdP-driven provisioning.

Per-tenant configuration (issuer, client id/secret, redirect uri, SCIM token)
is stored encrypted in ``tenant.sso_config`` (see ``crypto.py``).
"""

from __future__ import annotations

import json
import uuid
from typing import Any
from urllib.parse import urlencode

import jwt
import requests
from pydantic import BaseModel

from auth import issue_token
from crypto import decrypt_json, encrypt_json
from db import db


class OIDCLoginRequest(BaseModel):
    return_to: str | None = None


class OIDCCallbackRequest(BaseModel):
    code: str
    state: str | None = None


class ScimUserCreate(BaseModel):
    userName: str
    displayName: str | None = None
    active: bool = True
    role: str = "read_only"


class SSOConfigRequest(BaseModel):
    issuer: str
    client_id: str
    client_secret: str
    redirect_uri: str
    scim_token: str | None = None


def _discovery(issuer: str) -> dict[str, Any]:
    resp = requests.get(f"{issuer.rstrip('/')}/.well-known/openid-configuration", timeout=10)
    resp.raise_for_status()
    return resp.json()


def get_sso_config(tenant_id: str) -> dict[str, Any]:
    row = db.fetchone("SELECT sso_config FROM tenant WHERE id = %s", (tenant_id,))
    cfg = (row or {}).get("sso_config") or {}
    if not cfg:
        return {}
    resolved = dict(cfg)
    if "client_secret_enc" in cfg:
        resolved["client_secret"] = decrypt_json(cfg["client_secret_enc"]).get("value")
    if "scim_token_enc" in cfg:
        resolved["scim_token"] = decrypt_json(cfg["scim_token_enc"]).get("value")
    return resolved


def save_sso_config(tenant_id: str, payload: SSOConfigRequest) -> None:
    cfg: dict[str, Any] = {
        "issuer": payload.issuer.rstrip("/"),
        "client_id": payload.client_id,
        "redirect_uri": payload.redirect_uri,
        "client_secret_enc": encrypt_json({"value": payload.client_secret}),
    }
    if payload.scim_token:
        cfg["scim_token_enc"] = encrypt_json({"value": payload.scim_token})
    db.execute(
        "UPDATE tenant SET sso_config = %s WHERE id = %s",
        (json.dumps(cfg), tenant_id),
    )


def build_authorize_url(tenant_id: str, state: str) -> str:
    cfg = get_sso_config(tenant_id)
    if not cfg.get("issuer") or not cfg.get("client_id"):
        raise ValueError("SSO is not configured for this tenant")
    discovery = _discovery(cfg["issuer"])
    params = {
        "response_type": "code",
        "client_id": cfg["client_id"],
        "redirect_uri": cfg["redirect_uri"],
        "scope": "openid email profile",
        "state": state,
    }
    return f"{discovery['authorization_endpoint']}?{urlencode(params)}"


def _verify_id_token(id_token: str, jwks_uri: str, audience: str, issuer: str) -> dict[str, Any]:
    jwk_client = jwt.PyJWKClient(jwks_uri)
    signing_key = jwk_client.get_signing_key_from_jwt(id_token)
    return jwt.decode(
        id_token,
        signing_key.key,
        algorithms=["RS256", "ES256"],
        audience=audience,
        issuer=issuer,
    )


def exchange_code_for_token(tenant_id: str, code: str) -> dict[str, Any]:
    cfg = get_sso_config(tenant_id)
    if not cfg.get("issuer"):
        raise ValueError("SSO is not configured for this tenant")
    discovery = _discovery(cfg["issuer"])
    resp = requests.post(
        discovery["token_endpoint"],
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": cfg["redirect_uri"],
            "client_id": cfg["client_id"],
            "client_secret": cfg.get("client_secret"),
        },
        timeout=10,
    )
    resp.raise_for_status()
    tokens = resp.json()
    id_token = tokens.get("id_token")
    if not id_token:
        raise ValueError("Provider did not return an id_token")
    claims = _verify_id_token(id_token, discovery["jwks_uri"], cfg["client_id"], cfg["issuer"])
    email = claims.get("email")
    if not email:
        raise ValueError("id_token is missing an email claim")

    user = db.fetchone(
        'SELECT * FROM "user" WHERE tenant_id = %s AND email = %s',
        (tenant_id, email),
    )
    if user:
        user_id, role = user["id"], user["role"]
        db.execute('UPDATE "user" SET sso_id = %s WHERE id = %s', (claims.get("sub"), user_id))
    else:
        user_id = str(uuid.uuid4())
        role = "read_only"
        db.execute(
            """INSERT INTO "user" (id, tenant_id, email, full_name, role, active, sso_id)
               VALUES (%s, %s, %s, %s, %s, true, %s)""",
            (user_id, tenant_id, email, claims.get("name"), role, claims.get("sub")),
        )

    jwt_token = issue_token(tenant_id, str(user_id), role)
    return {"token": jwt_token, "email": email, "role": role, "user_id": str(user_id)}


def scim_authenticate(tenant_id: str, authorization_header: str | None) -> None:
    cfg = get_sso_config(tenant_id)
    expected = cfg.get("scim_token")
    if not expected:
        raise PermissionError("SCIM provisioning is not configured for this tenant")
    provided = (authorization_header or "").removeprefix("Bearer ").strip()
    if provided != expected:
        raise PermissionError("Invalid SCIM bearer token")


def scim_create_user(tenant_id: str, payload: ScimUserCreate) -> dict[str, Any]:
    existing = db.fetchone(
        'SELECT * FROM "user" WHERE tenant_id = %s AND email = %s',
        (tenant_id, payload.userName),
    )
    if existing:
        return _scim_user_view(existing)
    user_id = str(uuid.uuid4())
    db.execute(
        """INSERT INTO "user" (id, tenant_id, email, full_name, role, active)
           VALUES (%s, %s, %s, %s, %s, %s)""",
        (user_id, tenant_id, payload.userName, payload.displayName, payload.role, payload.active),
    )
    return _scim_user_view(db.fetchone('SELECT * FROM "user" WHERE id = %s', (user_id,)))


def scim_list_users(tenant_id: str) -> list[dict[str, Any]]:
    rows = db.execute('SELECT * FROM "user" WHERE tenant_id = %s', (tenant_id,))
    return [_scim_user_view(r) for r in rows]


def scim_deactivate_user(tenant_id: str, user_id: str, active: bool) -> dict[str, Any]:
    db.execute(
        'UPDATE "user" SET active = %s WHERE id = %s AND tenant_id = %s',
        (active, user_id, tenant_id),
    )
    return _scim_user_view(db.fetchone('SELECT * FROM "user" WHERE id = %s', (user_id,)))


def _scim_user_view(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
        "id": str(row["id"]),
        "userName": row["email"],
        "displayName": row.get("full_name"),
        "active": row.get("active", True),
        "role": row.get("role"),
    }
