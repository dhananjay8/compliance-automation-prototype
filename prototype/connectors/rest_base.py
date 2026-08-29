"""Shared helpers for lightweight REST-based connectors.

Each concrete connector in ``extra.py`` follows the same pattern already used
by ``aws.py`` / ``okta.py``: make a real HTTP call when credentials are
configured, and fall back to a small deterministic mock dataset when
credentials are missing or the live call fails for any reason. This keeps the
demo/dev experience working even without real third-party accounts while
still exercising genuine API integration code paths when credentials are
supplied.
"""

from __future__ import annotations

from typing import Any

from .base import ResourceRecord


def mock_user_accounts(source: str, users: list[dict[str, Any]]) -> list[ResourceRecord]:
    """Build a small deterministic set of UserAccount mock resources."""
    records: list[ResourceRecord] = []
    for u in users:
        records.append(
            ResourceRecord(
                external_id=f"{source}-{u['id']}",
                resource_type="UserAccount",
                data={**u, "source": source},
            )
        )
    return records


def first_present(data: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in data and data[key] is not None:
            return data[key]
    return None
