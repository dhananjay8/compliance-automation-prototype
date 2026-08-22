import os
from typing import Any

from .base import Connector, ConnectorCredentials, ResourceRecord


class OktaCredentials(ConnectorCredentials):
    def __init__(
        self,
        api_token: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self.api_token = api_token or os.getenv("OKTA_API_TOKEN")
        self.base_url = base_url or os.getenv("OKTA_BASE_URL")

    def is_configured(self) -> bool:
        return bool(self.api_token and self.base_url)


class OktaConnector(Connector):
    def __init__(self, credentials: OktaCredentials | None = None) -> None:
        super().__init__(credentials or OktaCredentials())

    def health_check(self) -> dict[str, Any]:
        if not self.is_ready():
            return {"configured": False, "base_url": None}
        creds = self.credentials
        assert isinstance(creds, OktaCredentials)
        try:
            import requests

            url = f"{creds.base_url.rstrip('/')}/api/v1/users?limit=1"
            headers = {"Authorization": f"SSWS {creds.api_token}"}
            resp = requests.get(url, headers=headers, timeout=10)
            resp.raise_for_status()
            return {
                "configured": True,
                "reachable": True,
                "base_url": creds.base_url,
            }
        except Exception as exc:
            return {
                "configured": True,
                "reachable": False,
                "base_url": creds.base_url,
                "error": str(exc),
            }

    def list_resources(self) -> list[ResourceRecord]:
        if not self.is_ready():
            return _okta_mock_resources()
        creds = self.credentials
        assert isinstance(creds, OktaCredentials)
        try:
            import requests

            records: list[ResourceRecord] = []
            url = f"{creds.base_url.rstrip('/')}/api/v1/users?limit=200"
            auth_headers = {"Authorization": f"SSWS {creds.api_token}"}
            while url:
                resp = requests.get(url, headers=auth_headers, timeout=30)
                resp.raise_for_status()
                users = resp.json()
                for user in users:
                    factors_resp = requests.get(
                        f"{creds.base_url.rstrip('/')}/api/v1/users/{user['id']}/factors",
                        headers=auth_headers,
                        timeout=10,
                    )
                    factors = factors_resp.json() if factors_resp.status_code == 200 else []
                    records.append(
                        ResourceRecord(
                            external_id=user["id"],
                            resource_type="UserAccount",
                            data={
                                "email": user.get("profile", {}).get("email"),
                                "login": user.get("profile", {}).get("login"),
                                "status": user.get("status"),
                                "mfa_enabled": len(factors) > 0,
                            },
                        )
                    )
                next_url = _parse_next_link(resp.headers.get("link", ""))
                url = next_url
            return records
        except Exception:
            return _okta_mock_resources()


def _okta_mock_resources() -> list[ResourceRecord]:
    return [
        ResourceRecord(
            external_id="okta-user-alice",
            resource_type="UserAccount",
            data={
                "email": "alice@example.com",
                "mfa_enabled": True,
                "status": "ACTIVE",
            },
        ),
        ResourceRecord(
            external_id="okta-user-bob",
            resource_type="UserAccount",
            data={
                "email": "bob@example.com",
                "mfa_enabled": False,
                "status": "ACTIVE",
            },
        ),
    ]


def _parse_next_link(link_header: str) -> str | None:
    if not link_header:
        return None
    for part in link_header.split(","):
        sections = part.split(";")
        if len(sections) == 2 and sections[1].strip().lower() == 'rel="next"':
            return sections[0].strip().strip("<>")
    return None
