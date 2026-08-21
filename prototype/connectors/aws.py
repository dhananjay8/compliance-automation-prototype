import os
from typing import Any

from .base import Connector, ConnectorCredentials, ResourceRecord


class AWSCredentials(ConnectorCredentials):
    def __init__(
        self,
        access_key_id: str | None = None,
        secret_access_key: str | None = None,
        region: str | None = None,
    ) -> None:
        self.access_key_id = access_key_id or os.getenv("AWS_ACCESS_KEY_ID")
        self.secret_access_key = secret_access_key or os.getenv("AWS_SECRET_ACCESS_KEY")
        self.region = region or os.getenv("AWS_DEFAULT_REGION") or "us-east-1"

    def is_configured(self) -> bool:
        return bool(self.access_key_id and self.secret_access_key)


class AWSConnector(Connector):
    def __init__(self, credentials: AWSCredentials | None = None) -> None:
        super().__init__(credentials or AWSCredentials())

    def health_check(self) -> dict[str, Any]:
        return {
            "configured": self.is_ready(),
            "region": self.credentials.region if isinstance(self.credentials, AWSCredentials) else None,
        }

    def list_resources(self) -> list[ResourceRecord]:
        if not self.is_ready():
            return []
        # Real adapter skeleton: call AWS APIs here when credentials are present.
        # For the MVP, return a deterministic mock sample.
        return [
            ResourceRecord(
                external_id="arn:aws:iam::123456789012:user/alice",
                resource_type="UserAccount",
                data={
                    "user_name": "alice",
                    "mfa_enabled": True,
                    "arn": "arn:aws:iam::123456789012:user/alice",
                },
            ),
            ResourceRecord(
                external_id="arn:aws:iam::123456789012:user/bob",
                resource_type="UserAccount",
                data={
                    "user_name": "bob",
                    "mfa_enabled": False,
                    "arn": "arn:aws:iam::123456789012:user/bob",
                },
            ),
            ResourceRecord(
                external_id="arn:aws:ec2:us-east-1:123456789012:instance/i-1234567890abcdef0",
                resource_type="Computer",
                data={
                    "instance_id": "i-1234567890abcdef0",
                    "public": False,
                    "encrypted": True,
                },
            ),
        ]
