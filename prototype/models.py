from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class Tenant(BaseModel):
    id: str
    name: str
    region: str = "us"


class IntegrationCreate(BaseModel):
    connector: str
    name: str
    config: dict[str, Any] = Field(default_factory=dict)
    credentials: dict[str, Any] = Field(default_factory=dict)


class IntegrationOut(BaseModel):
    id: str
    connector: str
    name: str
    config: dict[str, Any] = Field(default_factory=dict)
    status: str
    last_sync_at: datetime | None


class TestCreate(BaseModel):
    name: str
    resource_type: str
    rule: dict[str, Any]
    schedule: str = "0 * * * *"
    common_control_ids: list[str] = Field(default_factory=list)


class TestRunSummary(BaseModel):
    test_run_id: str
    test_id: str
    status: str
    total: int
    ok: int
    needs_attention: int
    invalid: int


class ControlStatus(BaseModel):
    control_id: str
    code: str
    statement: str
    owner: str | None
    status: str
    evidence_count: int
    last_evaluated_at: datetime | None


class FrameworkReadiness(BaseModel):
    framework_id: str
    code: str
    name: str
    total_controls: int
    ok_controls: int
    needs_attention_controls: int
    readiness_pct: float


class PostureSummary(BaseModel):
    tenant_id: str
    frameworks: list[FrameworkReadiness]
    overall_controls: int
    overall_ok: int
    overall_needs_attention: int
    overall_readiness_pct: float


class EvidenceOut(BaseModel):
    id: str
    test_name: str
    resource_external_id: str
    status: str
    evidence_type: str
    description: str | None
    collected_at: datetime
    expires_at: datetime | None


class AuditRequestCreate(BaseModel):
    control_id: str | None = None
    request_text: str


class AuditRequestOut(BaseModel):
    id: str
    audit_id: str
    control_id: str | None
    request_text: str
    status: str
    created_at: datetime
