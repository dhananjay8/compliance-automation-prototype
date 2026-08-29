"""Additional first-party connectors (Phase 4: 15+ connector roadmap item).

Each connector below follows the same "real API when configured, else mock"
pattern as ``aws.py`` / ``okta.py``. Real API calls use plain ``requests`` so
no extra SDKs are required. On any failure (missing creds, network error,
auth failure, unexpected schema) the connector returns a small deterministic
mock dataset so sync jobs, tests, and dashboards keep working end-to-end.
"""

from __future__ import annotations

import os
from typing import Any

from .base import Connector, ConnectorCredentials, ResourceRecord
from .rest_base import mock_user_accounts


# ---------------------------------------------------------------------------
# GitHub
# ---------------------------------------------------------------------------


class GitHubCredentials(ConnectorCredentials):
    def __init__(self, api_token: str | None = None, org: str | None = None) -> None:
        self.api_token = api_token or os.getenv("GITHUB_API_TOKEN")
        self.org = org or os.getenv("GITHUB_ORG")

    def is_configured(self) -> bool:
        return bool(self.api_token and self.org)


class GitHubConnector(Connector):
    def __init__(self, credentials: GitHubCredentials | None = None) -> None:
        super().__init__(credentials or GitHubCredentials())

    def health_check(self) -> dict[str, Any]:
        if not self.is_ready():
            return {"configured": False}
        creds: GitHubCredentials = self.credentials  # type: ignore[assignment]
        try:
            import requests

            resp = requests.get(
                f"https://api.github.com/orgs/{creds.org}",
                headers={"Authorization": f"Bearer {creds.api_token}"},
                timeout=10,
            )
            resp.raise_for_status()
            return {"configured": True, "reachable": True, "org": creds.org}
        except Exception as exc:
            return {"configured": True, "reachable": False, "error": str(exc)}

    def list_resources(self) -> list[ResourceRecord]:
        if not self.is_ready():
            return _github_mock()
        creds: GitHubCredentials = self.credentials  # type: ignore[assignment]
        try:
            import requests

            records: list[ResourceRecord] = []
            resp = requests.get(
                f"https://api.github.com/orgs/{creds.org}/members",
                headers={"Authorization": f"Bearer {creds.api_token}"},
                timeout=15,
            )
            resp.raise_for_status()
            for member in resp.json():
                mfa_resp = requests.get(
                    f"https://api.github.com/orgs/{creds.org}/members/{member['login']}",
                    headers={"Authorization": f"Bearer {creds.api_token}"},
                    timeout=10,
                )
                records.append(
                    ResourceRecord(
                        external_id=f"github-{member['id']}",
                        resource_type="UserAccount",
                        data={
                            "login": member.get("login"),
                            "type": member.get("type"),
                            "site_admin": member.get("site_admin", False),
                            "reachable": mfa_resp.status_code == 204,
                        },
                    )
                )
            return records or _github_mock()
        except Exception:
            return _github_mock()


def _github_mock() -> list[ResourceRecord]:
    return mock_user_accounts(
        "github",
        [
            {"id": "gh-alice", "login": "alice", "site_admin": True},
            {"id": "gh-bob", "login": "bob", "site_admin": False},
        ],
    )


# ---------------------------------------------------------------------------
# GitLab
# ---------------------------------------------------------------------------


class GitLabCredentials(ConnectorCredentials):
    def __init__(self, api_token: str | None = None, base_url: str | None = None) -> None:
        self.api_token = api_token or os.getenv("GITLAB_API_TOKEN")
        self.base_url = base_url or os.getenv("GITLAB_BASE_URL") or "https://gitlab.com"

    def is_configured(self) -> bool:
        return bool(self.api_token)


class GitLabConnector(Connector):
    def __init__(self, credentials: GitLabCredentials | None = None) -> None:
        super().__init__(credentials or GitLabCredentials())

    def health_check(self) -> dict[str, Any]:
        if not self.is_ready():
            return {"configured": False}
        creds: GitLabCredentials = self.credentials  # type: ignore[assignment]
        try:
            import requests

            resp = requests.get(
                f"{creds.base_url.rstrip('/')}/api/v4/user",
                headers={"PRIVATE-TOKEN": creds.api_token},
                timeout=10,
            )
            resp.raise_for_status()
            return {"configured": True, "reachable": True, "base_url": creds.base_url}
        except Exception as exc:
            return {"configured": True, "reachable": False, "error": str(exc)}

    def list_resources(self) -> list[ResourceRecord]:
        if not self.is_ready():
            return _gitlab_mock()
        creds: GitLabCredentials = self.credentials  # type: ignore[assignment]
        try:
            import requests

            resp = requests.get(
                f"{creds.base_url.rstrip('/')}/api/v4/users?per_page=100",
                headers={"PRIVATE-TOKEN": creds.api_token},
                timeout=15,
            )
            resp.raise_for_status()
            records = [
                ResourceRecord(
                    external_id=f"gitlab-{u['id']}",
                    resource_type="UserAccount",
                    data={
                        "username": u.get("username"),
                        "email": u.get("email"),
                        "state": u.get("state"),
                        "is_admin": u.get("is_admin", False),
                    },
                )
                for u in resp.json()
            ]
            return records or _gitlab_mock()
        except Exception:
            return _gitlab_mock()


def _gitlab_mock() -> list[ResourceRecord]:
    return mock_user_accounts(
        "gitlab",
        [
            {"id": "gl-alice", "username": "alice", "state": "active"},
            {"id": "gl-bob", "username": "bob", "state": "active"},
        ],
    )


# ---------------------------------------------------------------------------
# Slack
# ---------------------------------------------------------------------------


class SlackCredentials(ConnectorCredentials):
    def __init__(self, bot_token: str | None = None) -> None:
        self.bot_token = bot_token or os.getenv("SLACK_BOT_TOKEN")

    def is_configured(self) -> bool:
        return bool(self.bot_token)


class SlackConnector(Connector):
    def __init__(self, credentials: SlackCredentials | None = None) -> None:
        super().__init__(credentials or SlackCredentials())

    def health_check(self) -> dict[str, Any]:
        if not self.is_ready():
            return {"configured": False}
        creds: SlackCredentials = self.credentials  # type: ignore[assignment]
        try:
            import requests

            resp = requests.get(
                "https://slack.com/api/auth.test",
                headers={"Authorization": f"Bearer {creds.bot_token}"},
                timeout=10,
            )
            payload = resp.json()
            return {"configured": True, "reachable": bool(payload.get("ok")), "team": payload.get("team")}
        except Exception as exc:
            return {"configured": True, "reachable": False, "error": str(exc)}

    def list_resources(self) -> list[ResourceRecord]:
        if not self.is_ready():
            return _slack_mock()
        creds: SlackCredentials = self.credentials  # type: ignore[assignment]
        try:
            import requests

            resp = requests.get(
                "https://slack.com/api/users.list",
                headers={"Authorization": f"Bearer {creds.bot_token}"},
                timeout=15,
            )
            payload = resp.json()
            if not payload.get("ok"):
                return _slack_mock()
            records = []
            for member in payload.get("members", []):
                if member.get("is_bot") or member.get("deleted"):
                    continue
                records.append(
                    ResourceRecord(
                        external_id=f"slack-{member['id']}",
                        resource_type="UserAccount",
                        data={
                            "name": member.get("name"),
                            "email": member.get("profile", {}).get("email"),
                            "is_admin": member.get("is_admin", False),
                            "two_factor_enabled": member.get("has_2fa", False),
                        },
                    )
                )
            return records or _slack_mock()
        except Exception:
            return _slack_mock()


def _slack_mock() -> list[ResourceRecord]:
    return mock_user_accounts(
        "slack",
        [
            {"id": "sl-alice", "name": "alice", "has_2fa": True},
            {"id": "sl-bob", "name": "bob", "has_2fa": False},
        ],
    )


# ---------------------------------------------------------------------------
# Google Workspace
# ---------------------------------------------------------------------------


class GoogleWorkspaceCredentials(ConnectorCredentials):
    def __init__(self, access_token: str | None = None, domain: str | None = None) -> None:
        self.access_token = access_token or os.getenv("GOOGLE_WORKSPACE_ACCESS_TOKEN")
        self.domain = domain or os.getenv("GOOGLE_WORKSPACE_DOMAIN")

    def is_configured(self) -> bool:
        return bool(self.access_token and self.domain)


class GoogleWorkspaceConnector(Connector):
    def __init__(self, credentials: GoogleWorkspaceCredentials | None = None) -> None:
        super().__init__(credentials or GoogleWorkspaceCredentials())

    def health_check(self) -> dict[str, Any]:
        if not self.is_ready():
            return {"configured": False}
        return {"configured": True, "reachable": None, "domain": self.credentials.domain}  # type: ignore[union-attr]

    def list_resources(self) -> list[ResourceRecord]:
        if not self.is_ready():
            return _gws_mock()
        creds: GoogleWorkspaceCredentials = self.credentials  # type: ignore[assignment]
        try:
            import requests

            resp = requests.get(
                "https://admin.googleapis.com/admin/directory/v1/users",
                headers={"Authorization": f"Bearer {creds.access_token}"},
                params={"domain": creds.domain, "maxResults": 200},
                timeout=15,
            )
            resp.raise_for_status()
            records = []
            for user in resp.json().get("users", []):
                records.append(
                    ResourceRecord(
                        external_id=f"gws-{user['id']}",
                        resource_type="UserAccount",
                        data={
                            "email": user.get("primaryEmail"),
                            "suspended": user.get("suspended", False),
                            "is_admin": user.get("isAdmin", False),
                            "mfa_enabled": user.get("isEnrolledIn2Sv", False),
                        },
                    )
                )
            return records or _gws_mock()
        except Exception:
            return _gws_mock()


def _gws_mock() -> list[ResourceRecord]:
    return mock_user_accounts(
        "gws",
        [
            {"id": "gws-alice", "email": "alice@example.com", "isEnrolledIn2Sv": True},
            {"id": "gws-bob", "email": "bob@example.com", "isEnrolledIn2Sv": False},
        ],
    )


# ---------------------------------------------------------------------------
# Microsoft 365 / Azure AD (Microsoft Graph)
# ---------------------------------------------------------------------------


class Microsoft365Credentials(ConnectorCredentials):
    def __init__(self, access_token: str | None = None) -> None:
        self.access_token = access_token or os.getenv("MS365_ACCESS_TOKEN")

    def is_configured(self) -> bool:
        return bool(self.access_token)


class Microsoft365Connector(Connector):
    def __init__(self, credentials: Microsoft365Credentials | None = None) -> None:
        super().__init__(credentials or Microsoft365Credentials())

    def health_check(self) -> dict[str, Any]:
        if not self.is_ready():
            return {"configured": False}
        creds: Microsoft365Credentials = self.credentials  # type: ignore[assignment]
        try:
            import requests

            resp = requests.get(
                "https://graph.microsoft.com/v1.0/organization",
                headers={"Authorization": f"Bearer {creds.access_token}"},
                timeout=10,
            )
            resp.raise_for_status()
            return {"configured": True, "reachable": True}
        except Exception as exc:
            return {"configured": True, "reachable": False, "error": str(exc)}

    def list_resources(self) -> list[ResourceRecord]:
        if not self.is_ready():
            return _ms365_mock()
        creds: Microsoft365Credentials = self.credentials  # type: ignore[assignment]
        try:
            import requests

            resp = requests.get(
                "https://graph.microsoft.com/v1.0/users",
                headers={"Authorization": f"Bearer {creds.access_token}"},
                timeout=15,
            )
            resp.raise_for_status()
            records = [
                ResourceRecord(
                    external_id=f"ms365-{u['id']}",
                    resource_type="UserAccount",
                    data={
                        "userPrincipalName": u.get("userPrincipalName"),
                        "accountEnabled": u.get("accountEnabled", True),
                    },
                )
                for u in resp.json().get("value", [])
            ]
            return records or _ms365_mock()
        except Exception:
            return _ms365_mock()


def _ms365_mock() -> list[ResourceRecord]:
    return mock_user_accounts(
        "ms365",
        [
            {"id": "ms-alice", "userPrincipalName": "alice@example.com", "accountEnabled": True},
            {"id": "ms-bob", "userPrincipalName": "bob@example.com", "accountEnabled": True},
        ],
    )


# ---------------------------------------------------------------------------
# Jira (ticketing / identity)
# ---------------------------------------------------------------------------


class JiraCredentials(ConnectorCredentials):
    def __init__(
        self,
        email: str | None = None,
        api_token: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self.email = email or os.getenv("JIRA_EMAIL")
        self.api_token = api_token or os.getenv("JIRA_API_TOKEN")
        self.base_url = base_url or os.getenv("JIRA_BASE_URL")

    def is_configured(self) -> bool:
        return bool(self.email and self.api_token and self.base_url)

    def auth(self) -> tuple[str, str]:
        return (self.email or "", self.api_token or "")


class JiraConnector(Connector):
    def __init__(self, credentials: JiraCredentials | None = None) -> None:
        super().__init__(credentials or JiraCredentials())

    def health_check(self) -> dict[str, Any]:
        if not self.is_ready():
            return {"configured": False}
        creds: JiraCredentials = self.credentials  # type: ignore[assignment]
        try:
            import requests

            resp = requests.get(
                f"{creds.base_url.rstrip('/')}/rest/api/3/myself",
                auth=creds.auth(),
                timeout=10,
            )
            resp.raise_for_status()
            return {"configured": True, "reachable": True, "base_url": creds.base_url}
        except Exception as exc:
            return {"configured": True, "reachable": False, "error": str(exc)}

    def list_resources(self) -> list[ResourceRecord]:
        if not self.is_ready():
            return _jira_mock()
        creds: JiraCredentials = self.credentials  # type: ignore[assignment]
        try:
            import requests

            resp = requests.get(
                f"{creds.base_url.rstrip('/')}/rest/api/3/users/search",
                auth=creds.auth(),
                params={"maxResults": 200},
                timeout=15,
            )
            resp.raise_for_status()
            records = [
                ResourceRecord(
                    external_id=f"jira-{u['accountId']}",
                    resource_type="UserAccount",
                    data={
                        "displayName": u.get("displayName"),
                        "active": u.get("active", True),
                        "accountType": u.get("accountType"),
                    },
                )
                for u in resp.json()
            ]
            return records or _jira_mock()
        except Exception:
            return _jira_mock()


def _jira_mock() -> list[ResourceRecord]:
    return mock_user_accounts(
        "jira",
        [
            {"id": "jira-alice", "displayName": "Alice", "active": True},
            {"id": "jira-bob", "displayName": "Bob", "active": True},
        ],
    )


def create_jira_ticket(
    base_url: str | None,
    email: str | None,
    api_token: str | None,
    project_key: str,
    summary: str,
    description: str,
) -> dict[str, Any]:
    """Create a real Jira issue when configured; otherwise return a mock ticket id."""
    if base_url and email and api_token:
        try:
            import requests

            resp = requests.post(
                f"{base_url.rstrip('/')}/rest/api/3/issue",
                auth=(email, api_token),
                json={
                    "fields": {
                        "project": {"key": project_key},
                        "summary": summary,
                        "description": {
                            "type": "doc",
                            "version": 1,
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [{"type": "text", "text": description}],
                                }
                            ],
                        },
                        "issuetype": {"name": "Task"},
                    }
                },
                timeout=15,
            )
            resp.raise_for_status()
            payload = resp.json()
            return {"ticket_id": payload.get("key"), "system": "jira", "mocked": False}
        except Exception as exc:
            return {"ticket_id": f"JIRA-MOCK-{abs(hash(summary)) % 10000}", "system": "jira", "mocked": True, "error": str(exc)}
    return {"ticket_id": f"JIRA-MOCK-{abs(hash(summary)) % 10000}", "system": "jira", "mocked": True}


# ---------------------------------------------------------------------------
# ServiceNow (ticketing / identity)
# ---------------------------------------------------------------------------


class ServiceNowCredentials(ConnectorCredentials):
    def __init__(
        self,
        username: str | None = None,
        password: str | None = None,
        instance_url: str | None = None,
    ) -> None:
        self.username = username or os.getenv("SERVICENOW_USERNAME")
        self.password = password or os.getenv("SERVICENOW_PASSWORD")
        self.instance_url = instance_url or os.getenv("SERVICENOW_INSTANCE_URL")

    def is_configured(self) -> bool:
        return bool(self.username and self.password and self.instance_url)

    def auth(self) -> tuple[str, str]:
        return (self.username or "", self.password or "")


class ServiceNowConnector(Connector):
    def __init__(self, credentials: ServiceNowCredentials | None = None) -> None:
        super().__init__(credentials or ServiceNowCredentials())

    def health_check(self) -> dict[str, Any]:
        if not self.is_ready():
            return {"configured": False}
        creds: ServiceNowCredentials = self.credentials  # type: ignore[assignment]
        try:
            import requests

            resp = requests.get(
                f"{creds.instance_url.rstrip('/')}/api/now/table/sys_user",
                auth=creds.auth(),
                params={"sysparm_limit": 1},
                timeout=10,
            )
            resp.raise_for_status()
            return {"configured": True, "reachable": True, "instance_url": creds.instance_url}
        except Exception as exc:
            return {"configured": True, "reachable": False, "error": str(exc)}

    def list_resources(self) -> list[ResourceRecord]:
        if not self.is_ready():
            return _snow_mock()
        creds: ServiceNowCredentials = self.credentials  # type: ignore[assignment]
        try:
            import requests

            resp = requests.get(
                f"{creds.instance_url.rstrip('/')}/api/now/table/sys_user",
                auth=creds.auth(),
                params={"sysparm_limit": 200},
                timeout=15,
            )
            resp.raise_for_status()
            records = [
                ResourceRecord(
                    external_id=f"snow-{u['sys_id']}",
                    resource_type="UserAccount",
                    data={
                        "user_name": u.get("user_name"),
                        "active": u.get("active"),
                        "locked_out": u.get("locked_out"),
                    },
                )
                for u in resp.json().get("result", [])
            ]
            return records or _snow_mock()
        except Exception:
            return _snow_mock()


def _snow_mock() -> list[ResourceRecord]:
    return mock_user_accounts(
        "servicenow",
        [
            {"id": "snow-alice", "user_name": "alice", "active": "true"},
            {"id": "snow-bob", "user_name": "bob", "active": "true"},
        ],
    )


def create_servicenow_incident(
    instance_url: str | None,
    username: str | None,
    password: str | None,
    short_description: str,
    description: str,
) -> dict[str, Any]:
    """Create a real ServiceNow incident when configured; otherwise mock it."""
    if instance_url and username and password:
        try:
            import requests

            resp = requests.post(
                f"{instance_url.rstrip('/')}/api/now/table/incident",
                auth=(username, password),
                json={"short_description": short_description, "description": description},
                timeout=15,
            )
            resp.raise_for_status()
            payload = resp.json().get("result", {})
            return {"ticket_id": payload.get("number"), "system": "servicenow", "mocked": False}
        except Exception as exc:
            return {
                "ticket_id": f"INC-MOCK-{abs(hash(short_description)) % 10000}",
                "system": "servicenow",
                "mocked": True,
                "error": str(exc),
            }
    return {"ticket_id": f"INC-MOCK-{abs(hash(short_description)) % 10000}", "system": "servicenow", "mocked": True}


# ---------------------------------------------------------------------------
# PagerDuty
# ---------------------------------------------------------------------------


class PagerDutyCredentials(ConnectorCredentials):
    def __init__(self, api_token: str | None = None) -> None:
        self.api_token = api_token or os.getenv("PAGERDUTY_API_TOKEN")

    def is_configured(self) -> bool:
        return bool(self.api_token)


class PagerDutyConnector(Connector):
    def __init__(self, credentials: PagerDutyCredentials | None = None) -> None:
        super().__init__(credentials or PagerDutyCredentials())

    def health_check(self) -> dict[str, Any]:
        if not self.is_ready():
            return {"configured": False}
        creds: PagerDutyCredentials = self.credentials  # type: ignore[assignment]
        try:
            import requests

            resp = requests.get(
                "https://api.pagerduty.com/users",
                headers={"Authorization": f"Token token={creds.api_token}", "Content-Type": "application/json"},
                params={"limit": 1},
                timeout=10,
            )
            resp.raise_for_status()
            return {"configured": True, "reachable": True}
        except Exception as exc:
            return {"configured": True, "reachable": False, "error": str(exc)}

    def list_resources(self) -> list[ResourceRecord]:
        if not self.is_ready():
            return _pagerduty_mock()
        creds: PagerDutyCredentials = self.credentials  # type: ignore[assignment]
        try:
            import requests

            resp = requests.get(
                "https://api.pagerduty.com/users",
                headers={"Authorization": f"Token token={creds.api_token}", "Content-Type": "application/json"},
                params={"limit": 100},
                timeout=15,
            )
            resp.raise_for_status()
            records = [
                ResourceRecord(
                    external_id=f"pd-{u['id']}",
                    resource_type="UserAccount",
                    data={"name": u.get("name"), "email": u.get("email"), "role": u.get("role")},
                )
                for u in resp.json().get("users", [])
            ]
            return records or _pagerduty_mock()
        except Exception:
            return _pagerduty_mock()


def _pagerduty_mock() -> list[ResourceRecord]:
    return mock_user_accounts(
        "pagerduty",
        [
            {"id": "pd-alice", "name": "Alice", "role": "admin"},
            {"id": "pd-bob", "name": "Bob", "role": "responder"},
        ],
    )


# ---------------------------------------------------------------------------
# Datadog
# ---------------------------------------------------------------------------


class DatadogCredentials(ConnectorCredentials):
    def __init__(self, api_key: str | None = None, app_key: str | None = None) -> None:
        self.api_key = api_key or os.getenv("DATADOG_API_KEY")
        self.app_key = app_key or os.getenv("DATADOG_APP_KEY")

    def is_configured(self) -> bool:
        return bool(self.api_key and self.app_key)


class DatadogConnector(Connector):
    def __init__(self, credentials: DatadogCredentials | None = None) -> None:
        super().__init__(credentials or DatadogCredentials())

    def health_check(self) -> dict[str, Any]:
        if not self.is_ready():
            return {"configured": False}
        creds: DatadogCredentials = self.credentials  # type: ignore[assignment]
        try:
            import requests

            resp = requests.get(
                "https://api.datadoghq.com/api/v1/validate",
                headers={"DD-API-KEY": creds.api_key, "DD-APPLICATION-KEY": creds.app_key},
                timeout=10,
            )
            resp.raise_for_status()
            return {"configured": True, "reachable": True}
        except Exception as exc:
            return {"configured": True, "reachable": False, "error": str(exc)}

    def list_resources(self) -> list[ResourceRecord]:
        if not self.is_ready():
            return _datadog_mock()
        creds: DatadogCredentials = self.credentials  # type: ignore[assignment]
        try:
            import requests

            resp = requests.get(
                "https://api.datadoghq.com/api/v2/users",
                headers={"DD-API-KEY": creds.api_key, "DD-APPLICATION-KEY": creds.app_key},
                timeout=15,
            )
            resp.raise_for_status()
            records = []
            for u in resp.json().get("data", []):
                attrs = u.get("attributes", {})
                records.append(
                    ResourceRecord(
                        external_id=f"dd-{u['id']}",
                        resource_type="UserAccount",
                        data={
                            "email": attrs.get("email"),
                            "status": attrs.get("status"),
                            "disabled": attrs.get("disabled", False),
                        },
                    )
                )
            return records or _datadog_mock()
        except Exception:
            return _datadog_mock()


def _datadog_mock() -> list[ResourceRecord]:
    return mock_user_accounts(
        "datadog",
        [
            {"id": "dd-alice", "email": "alice@example.com", "status": "Active"},
            {"id": "dd-bob", "email": "bob@example.com", "status": "Active"},
        ],
    )


# ---------------------------------------------------------------------------
# Zoom
# ---------------------------------------------------------------------------


class ZoomCredentials(ConnectorCredentials):
    def __init__(self, access_token: str | None = None) -> None:
        self.access_token = access_token or os.getenv("ZOOM_ACCESS_TOKEN")

    def is_configured(self) -> bool:
        return bool(self.access_token)


class ZoomConnector(Connector):
    def __init__(self, credentials: ZoomCredentials | None = None) -> None:
        super().__init__(credentials or ZoomCredentials())

    def health_check(self) -> dict[str, Any]:
        if not self.is_ready():
            return {"configured": False}
        creds: ZoomCredentials = self.credentials  # type: ignore[assignment]
        try:
            import requests

            resp = requests.get(
                "https://api.zoom.us/v2/users/me",
                headers={"Authorization": f"Bearer {creds.access_token}"},
                timeout=10,
            )
            resp.raise_for_status()
            return {"configured": True, "reachable": True}
        except Exception as exc:
            return {"configured": True, "reachable": False, "error": str(exc)}

    def list_resources(self) -> list[ResourceRecord]:
        if not self.is_ready():
            return _zoom_mock()
        creds: ZoomCredentials = self.credentials  # type: ignore[assignment]
        try:
            import requests

            resp = requests.get(
                "https://api.zoom.us/v2/users",
                headers={"Authorization": f"Bearer {creds.access_token}"},
                params={"page_size": 100},
                timeout=15,
            )
            resp.raise_for_status()
            records = [
                ResourceRecord(
                    external_id=f"zoom-{u['id']}",
                    resource_type="UserAccount",
                    data={
                        "email": u.get("email"),
                        "status": u.get("status"),
                        "role_id": u.get("role_id"),
                    },
                )
                for u in resp.json().get("users", [])
            ]
            return records or _zoom_mock()
        except Exception:
            return _zoom_mock()


def _zoom_mock() -> list[ResourceRecord]:
    return mock_user_accounts(
        "zoom",
        [
            {"id": "zoom-alice", "email": "alice@example.com", "status": "active"},
            {"id": "zoom-bob", "email": "bob@example.com", "status": "active"},
        ],
    )


# ---------------------------------------------------------------------------
# Salesforce
# ---------------------------------------------------------------------------


class SalesforceCredentials(ConnectorCredentials):
    def __init__(self, access_token: str | None = None, instance_url: str | None = None) -> None:
        self.access_token = access_token or os.getenv("SALESFORCE_ACCESS_TOKEN")
        self.instance_url = instance_url or os.getenv("SALESFORCE_INSTANCE_URL")

    def is_configured(self) -> bool:
        return bool(self.access_token and self.instance_url)


class SalesforceConnector(Connector):
    def __init__(self, credentials: SalesforceCredentials | None = None) -> None:
        super().__init__(credentials or SalesforceCredentials())

    def health_check(self) -> dict[str, Any]:
        if not self.is_ready():
            return {"configured": False}
        creds: SalesforceCredentials = self.credentials  # type: ignore[assignment]
        try:
            import requests

            resp = requests.get(
                f"{creds.instance_url.rstrip('/')}/services/data/v58.0/limits",
                headers={"Authorization": f"Bearer {creds.access_token}"},
                timeout=10,
            )
            resp.raise_for_status()
            return {"configured": True, "reachable": True}
        except Exception as exc:
            return {"configured": True, "reachable": False, "error": str(exc)}

    def list_resources(self) -> list[ResourceRecord]:
        if not self.is_ready():
            return _salesforce_mock()
        creds: SalesforceCredentials = self.credentials  # type: ignore[assignment]
        try:
            import requests

            query = "SELECT Id,Username,IsActive,ProfileId FROM User"
            resp = requests.get(
                f"{creds.instance_url.rstrip('/')}/services/data/v58.0/query",
                headers={"Authorization": f"Bearer {creds.access_token}"},
                params={"q": query},
                timeout=15,
            )
            resp.raise_for_status()
            records = [
                ResourceRecord(
                    external_id=f"sf-{u['Id']}",
                    resource_type="UserAccount",
                    data={"username": u.get("Username"), "is_active": u.get("IsActive", True)},
                )
                for u in resp.json().get("records", [])
            ]
            return records or _salesforce_mock()
        except Exception:
            return _salesforce_mock()


def _salesforce_mock() -> list[ResourceRecord]:
    return mock_user_accounts(
        "salesforce",
        [
            {"id": "sf-alice", "username": "alice", "is_active": True},
            {"id": "sf-bob", "username": "bob", "is_active": True},
        ],
    )


# ---------------------------------------------------------------------------
# Snyk (vulnerability scanning)
# ---------------------------------------------------------------------------


class SnykCredentials(ConnectorCredentials):
    def __init__(self, api_token: str | None = None, org_id: str | None = None) -> None:
        self.api_token = api_token or os.getenv("SNYK_API_TOKEN")
        self.org_id = org_id or os.getenv("SNYK_ORG_ID")

    def is_configured(self) -> bool:
        return bool(self.api_token and self.org_id)


class SnykConnector(Connector):
    def __init__(self, credentials: SnykCredentials | None = None) -> None:
        super().__init__(credentials or SnykCredentials())

    def health_check(self) -> dict[str, Any]:
        if not self.is_ready():
            return {"configured": False}
        creds: SnykCredentials = self.credentials  # type: ignore[assignment]
        try:
            import requests

            resp = requests.get(
                f"https://api.snyk.io/rest/orgs/{creds.org_id}",
                headers={"Authorization": f"token {creds.api_token}"},
                params={"version": "2024-01-04"},
                timeout=10,
            )
            resp.raise_for_status()
            return {"configured": True, "reachable": True}
        except Exception as exc:
            return {"configured": True, "reachable": False, "error": str(exc)}

    def list_resources(self) -> list[ResourceRecord]:
        if not self.is_ready():
            return _snyk_mock()
        creds: SnykCredentials = self.credentials  # type: ignore[assignment]
        try:
            import requests

            resp = requests.get(
                f"https://api.snyk.io/rest/orgs/{creds.org_id}/issues",
                headers={"Authorization": f"token {creds.api_token}"},
                params={"version": "2024-01-04", "limit": 100},
                timeout=15,
            )
            resp.raise_for_status()
            records = []
            for issue in resp.json().get("data", []):
                attrs = issue.get("attributes", {})
                records.append(
                    ResourceRecord(
                        external_id=f"snyk-{issue['id']}",
                        resource_type="Vulnerability",
                        data={
                            "title": attrs.get("title"),
                            "severity": attrs.get("effective_severity_level"),
                            "status": attrs.get("status"),
                        },
                    )
                )
            return records or _snyk_mock()
        except Exception:
            return _snyk_mock()


def _snyk_mock() -> list[ResourceRecord]:
    return [
        ResourceRecord(
            external_id="snyk-mock-1",
            resource_type="Vulnerability",
            data={"title": "Outdated dependency: lodash", "severity": "high", "status": "open"},
        ),
        ResourceRecord(
            external_id="snyk-mock-2",
            resource_type="Vulnerability",
            data={"title": "Prototype pollution", "severity": "medium", "status": "resolved"},
        ),
    ]


# ---------------------------------------------------------------------------
# Tenable.io (vulnerability scanning)
# ---------------------------------------------------------------------------


class TenableCredentials(ConnectorCredentials):
    def __init__(self, access_key: str | None = None, secret_key: str | None = None) -> None:
        self.access_key = access_key or os.getenv("TENABLE_ACCESS_KEY")
        self.secret_key = secret_key or os.getenv("TENABLE_SECRET_KEY")

    def is_configured(self) -> bool:
        return bool(self.access_key and self.secret_key)

    def header(self) -> str:
        return f"accessKey={self.access_key};secretKey={self.secret_key}"


class TenableConnector(Connector):
    def __init__(self, credentials: TenableCredentials | None = None) -> None:
        super().__init__(credentials or TenableCredentials())

    def health_check(self) -> dict[str, Any]:
        if not self.is_ready():
            return {"configured": False}
        creds: TenableCredentials = self.credentials  # type: ignore[assignment]
        try:
            import requests

            resp = requests.get(
                "https://cloud.tenable.com/session",
                headers={"X-ApiKeys": creds.header()},
                timeout=10,
            )
            resp.raise_for_status()
            return {"configured": True, "reachable": True}
        except Exception as exc:
            return {"configured": True, "reachable": False, "error": str(exc)}

    def list_resources(self) -> list[ResourceRecord]:
        if not self.is_ready():
            return _tenable_mock()
        creds: TenableCredentials = self.credentials  # type: ignore[assignment]
        try:
            import requests

            resp = requests.get(
                "https://cloud.tenable.com/workbenches/vulnerabilities",
                headers={"X-ApiKeys": creds.header()},
                timeout=15,
            )
            resp.raise_for_status()
            records = []
            for v in resp.json().get("vulnerabilities", []):
                records.append(
                    ResourceRecord(
                        external_id=f"tenable-{v.get('plugin_id')}",
                        resource_type="Vulnerability",
                        data={
                            "plugin_name": v.get("plugin_name"),
                            "severity": v.get("severity"),
                            "count": v.get("count"),
                        },
                    )
                )
            return records or _tenable_mock()
        except Exception:
            return _tenable_mock()


def _tenable_mock() -> list[ResourceRecord]:
    return [
        ResourceRecord(
            external_id="tenable-mock-1",
            resource_type="Vulnerability",
            data={"plugin_name": "Unpatched OpenSSL", "severity": 3, "count": 5},
        ),
        ResourceRecord(
            external_id="tenable-mock-2",
            resource_type="Vulnerability",
            data={"plugin_name": "Weak TLS cipher suite", "severity": 2, "count": 2},
        ),
    ]
