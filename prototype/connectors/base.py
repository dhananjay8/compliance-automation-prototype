import hashlib
import json
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any


class ConnectorCredentials(ABC):
    @abstractmethod
    def is_configured(self) -> bool:
        raise NotImplementedError


class ResourceRecord:
    def __init__(
        self,
        external_id: str,
        resource_type: str,
        data: dict[str, Any],
        collected_at: datetime | None = None,
    ) -> None:
        self.external_id = external_id
        self.resource_type = resource_type
        self.data = data
        self.collected_at = collected_at or datetime.now(timezone.utc)

    def hash(self) -> str:
        return hashlib.sha256(
            json.dumps(self.data, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()


class Connector(ABC):
    def __init__(self, credentials: ConnectorCredentials) -> None:
        self.credentials = credentials

    @abstractmethod
    def list_resources(self) -> list[ResourceRecord]:
        """Fetch and normalize resources from the external system."""
        raise NotImplementedError

    @abstractmethod
    def health_check(self) -> dict[str, Any]:
        """Return a lightweight status check for the integration."""
        raise NotImplementedError

    def is_ready(self) -> bool:
        return self.credentials.is_configured()
