from typing import Any

from .base import Connector, ConnectorCredentials, ResourceRecord
from .aws import AWSConnector, AWSCredentials
from .okta import OktaConnector, OktaCredentials
from .extra import (
    DatadogConnector,
    DatadogCredentials,
    GitHubConnector,
    GitHubCredentials,
    GitLabConnector,
    GitLabCredentials,
    GoogleWorkspaceConnector,
    GoogleWorkspaceCredentials,
    JiraConnector,
    JiraCredentials,
    Microsoft365Connector,
    Microsoft365Credentials,
    PagerDutyConnector,
    PagerDutyCredentials,
    SalesforceConnector,
    SalesforceCredentials,
    ServiceNowConnector,
    ServiceNowCredentials,
    SlackConnector,
    SlackCredentials,
    SnykConnector,
    SnykCredentials,
    TenableConnector,
    TenableCredentials,
    ZoomConnector,
    ZoomCredentials,
    create_jira_ticket,
    create_servicenow_incident,
)

__all__ = [
    "Connector",
    "ConnectorCredentials",
    "ResourceRecord",
    "AWSConnector",
    "AWSCredentials",
    "OktaConnector",
    "OktaCredentials",
    "GitHubConnector",
    "GitHubCredentials",
    "GitLabConnector",
    "GitLabCredentials",
    "SlackConnector",
    "SlackCredentials",
    "GoogleWorkspaceConnector",
    "GoogleWorkspaceCredentials",
    "Microsoft365Connector",
    "Microsoft365Credentials",
    "JiraConnector",
    "JiraCredentials",
    "ServiceNowConnector",
    "ServiceNowCredentials",
    "PagerDutyConnector",
    "PagerDutyCredentials",
    "DatadogConnector",
    "DatadogCredentials",
    "ZoomConnector",
    "ZoomCredentials",
    "SalesforceConnector",
    "SalesforceCredentials",
    "SnykConnector",
    "SnykCredentials",
    "TenableConnector",
    "TenableCredentials",
    "create_jira_ticket",
    "create_servicenow_incident",
    "CONNECTOR_REGISTRY",
    "build_connector",
    "list_connector_catalog",
]


# Each entry maps a lowercase connector key (as stored in `integration.connector`)
# to its connector/credentials classes and the exact credential field names its
# constructor accepts. This lets app.py and worker.py resolve ANY connector
# generically instead of hardcoded if/elif chains, and lets the frontend render
# a connector marketplace by introspecting `credential_fields`.
CONNECTOR_REGISTRY: dict[str, dict[str, Any]] = {
    "aws": {
        "label": "AWS",
        "category": "cloud",
        "connector_cls": AWSConnector,
        "credentials_cls": AWSCredentials,
        "credential_fields": ["access_key_id", "secret_access_key", "region"],
    },
    "okta": {
        "label": "Okta",
        "category": "identity",
        "connector_cls": OktaConnector,
        "credentials_cls": OktaCredentials,
        "credential_fields": ["api_token", "base_url"],
    },
    "github": {
        "label": "GitHub",
        "category": "devops",
        "connector_cls": GitHubConnector,
        "credentials_cls": GitHubCredentials,
        "credential_fields": ["api_token", "org"],
    },
    "gitlab": {
        "label": "GitLab",
        "category": "devops",
        "connector_cls": GitLabConnector,
        "credentials_cls": GitLabCredentials,
        "credential_fields": ["api_token", "base_url"],
    },
    "slack": {
        "label": "Slack",
        "category": "collaboration",
        "connector_cls": SlackConnector,
        "credentials_cls": SlackCredentials,
        "credential_fields": ["bot_token"],
    },
    "google_workspace": {
        "label": "Google Workspace",
        "category": "identity",
        "connector_cls": GoogleWorkspaceConnector,
        "credentials_cls": GoogleWorkspaceCredentials,
        "credential_fields": ["access_token", "domain"],
    },
    "microsoft365": {
        "label": "Microsoft 365 / Azure AD",
        "category": "identity",
        "connector_cls": Microsoft365Connector,
        "credentials_cls": Microsoft365Credentials,
        "credential_fields": ["access_token"],
    },
    "jira": {
        "label": "Jira",
        "category": "ticketing",
        "connector_cls": JiraConnector,
        "credentials_cls": JiraCredentials,
        "credential_fields": ["email", "api_token", "base_url"],
    },
    "servicenow": {
        "label": "ServiceNow",
        "category": "ticketing",
        "connector_cls": ServiceNowConnector,
        "credentials_cls": ServiceNowCredentials,
        "credential_fields": ["username", "password", "instance_url"],
    },
    "pagerduty": {
        "label": "PagerDuty",
        "category": "incident_management",
        "connector_cls": PagerDutyConnector,
        "credentials_cls": PagerDutyCredentials,
        "credential_fields": ["api_token"],
    },
    "datadog": {
        "label": "Datadog",
        "category": "observability",
        "connector_cls": DatadogConnector,
        "credentials_cls": DatadogCredentials,
        "credential_fields": ["api_key", "app_key"],
    },
    "zoom": {
        "label": "Zoom",
        "category": "collaboration",
        "connector_cls": ZoomConnector,
        "credentials_cls": ZoomCredentials,
        "credential_fields": ["access_token"],
    },
    "salesforce": {
        "label": "Salesforce",
        "category": "crm",
        "connector_cls": SalesforceConnector,
        "credentials_cls": SalesforceCredentials,
        "credential_fields": ["access_token", "instance_url"],
    },
    "snyk": {
        "label": "Snyk",
        "category": "vuln_scanner",
        "connector_cls": SnykConnector,
        "credentials_cls": SnykCredentials,
        "credential_fields": ["api_token", "org_id"],
    },
    "tenable": {
        "label": "Tenable.io",
        "category": "vuln_scanner",
        "connector_cls": TenableConnector,
        "credentials_cls": TenableCredentials,
        "credential_fields": ["access_key", "secret_key"],
    },
}


def build_connector(connector_name: str, credentials: dict[str, Any] | None = None) -> Connector | None:
    """Instantiate the connector registered for ``connector_name``.

    Returns ``None`` if the connector name is not registered.
    """
    entry = CONNECTOR_REGISTRY.get((connector_name or "").lower())
    if not entry:
        return None
    credentials = credentials or {}
    creds_cls = entry["credentials_cls"]
    kwargs = {field: credentials.get(field) for field in entry["credential_fields"]}
    creds = creds_cls(**kwargs)
    return entry["connector_cls"](creds)


def list_connector_catalog() -> list[dict[str, Any]]:
    """Return a frontend-friendly catalog of all registered connectors."""
    return [
        {
            "key": key,
            "label": entry["label"],
            "category": entry["category"],
            "credential_fields": entry["credential_fields"],
        }
        for key, entry in sorted(CONNECTOR_REGISTRY.items())
    ]
