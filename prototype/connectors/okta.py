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
        return {
            "configured": self.is_ready(),
            "base_url": self.credentials.base_url if isinstance(self.credentials, OktaCredentials) else None,
        }

    def list_resources(self) -> list[ResourceRecord]:
        if not self.is_ready():
            return []
        # Real adapter skeleton: call Okta /api/v1/users here when credentials are present.
        # For the MVP, return a deterministic mock sample.
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
