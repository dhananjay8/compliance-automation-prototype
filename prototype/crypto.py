"""Credential encryption at rest.

Integration credentials (API keys, tokens, secrets) are encrypted with Fernet
(symmetric AES) before being persisted to the `integration.credentials` jsonb
column, and decrypted only in-memory when a connector needs to make a live API
call. If ``ENCRYPTION_KEY`` is not set, a stable development key is derived so
local/test environments keep working without extra setup -- production
deployments MUST set ``ENCRYPTION_KEY`` to a securely generated Fernet key.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
from functools import lru_cache
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

_ENC_MARKER = "_enc"
_DEV_KEY_SEED = b"compliance-automation-prototype-dev-key-do-not-use-in-prod"


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    raw_key = os.getenv("ENCRYPTION_KEY")
    if raw_key:
        key = raw_key.encode() if isinstance(raw_key, str) else raw_key
    else:
        key = base64.urlsafe_b64encode(hashlib.sha256(_DEV_KEY_SEED).digest())
    return Fernet(key)


def encrypt_json(payload: dict[str, Any] | None) -> str:
    """Encrypt a JSON-serializable dict into an opaque Fernet token string."""
    data = json.dumps(payload or {}).encode("utf-8")
    return _fernet().encrypt(data).decode("utf-8")


def decrypt_json(token: str) -> dict[str, Any]:
    """Decrypt a Fernet token string produced by :func:`encrypt_json`."""
    try:
        raw = _fernet().decrypt(token.encode("utf-8"))
        return json.loads(raw)
    except (InvalidToken, ValueError, TypeError, json.JSONDecodeError):
        return {}


def encrypt_credentials(credentials: dict[str, Any] | None) -> dict[str, Any]:
    """Wrap plaintext credentials into an encrypted envelope for storage."""
    return {_ENC_MARKER: encrypt_json(credentials or {})}


def resolve_credentials(stored: dict[str, Any] | None) -> dict[str, Any]:
    """Return plaintext credentials from a stored (possibly encrypted) value.

    Supports legacy rows that were written before encryption was introduced
    (plain dict, no ``_enc`` marker) so no data migration is required.
    """
    if not stored:
        return {}
    if _ENC_MARKER in stored:
        return decrypt_json(stored[_ENC_MARKER])
    return dict(stored)
