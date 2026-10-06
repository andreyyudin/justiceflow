from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class Priority(StrEnum):
    urgent = "urgent"
    high = "high"
    standard = "standard"


class CaseStatus(StrEnum):
    needs_review = "needs_review"
    approved = "approved"
    escalated = "escalated"


class LatestDecision(BaseModel):
    outcome: Priority
    reason: str
    reviewer: str
    recorded_at: str


class Case(BaseModel):
    id: str
    reference: str
    service: str
    region: str
    summary: str
    received_at: str
    priority: Priority
    status: CaseStatus
    risk_flags: list[str]
    days_waiting: int
    latest_decision: LatestDecision | None = None


class TriageRequest(BaseModel):
    case_id: str


class EvidenceSource(StrEnum):
    summary = "summary"
    service = "service"
    days_waiting = "days_waiting"
    risk_flags = "risk_flags"


class ModelTriageOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recommendation: Priority
    rationale: str = Field(min_length=20, max_length=500)
    evidence: list[EvidenceSource] = Field(min_length=1, max_length=4)
    confidence: float = Field(ge=0, le=1)


class RecommendationCreate(BaseModel):
    case_id: str
    recommendation: Priority
    rationale: str = Field(min_length=20, max_length=500)
    evidence: list[str] = Field(min_length=1, max_length=4)
    model: str = Field(min_length=1, max_length=100)
    model_confidence: float = Field(ge=0, le=1)
    latency_ms: int = Field(ge=0)


class Recommendation(BaseModel):
    id: UUID
    case_id: str
    recommendation: Priority
    rationale: str
    evidence: list[str]
    model: str
    latency_ms: int
    created_at: str


class TriageResult(BaseModel):
    recommendation_id: UUID
    case_id: str
    recommendation: Priority
    rationale: str
    evidence: list[str] = Field(min_length=1, max_length=4)
    requires_human_review: bool = True
    model: str
    latency_ms: int


class DecisionType(StrEnum):
    accepted = "accepted"
    overridden = "overridden"
    legacy = "legacy"


class DecisionRequest(BaseModel):
    case_id: str
    recommendation_id: UUID
    outcome: Priority
    reason: str = Field(min_length=10, max_length=500)


class ObservabilityStatus(BaseModel):
    structured_logs: bool = True
    langfuse_enabled: bool
    environment: str
    release: str


class Decision(BaseModel):
    case_id: str
    recommendation_id: UUID | None
    decision_type: DecisionType
    outcome: Priority
    reason: str
    reviewer: str
    recorded_at: str


class DecisionAuditEntry(BaseModel):
    case_id: str
    recommendation_id: UUID | None
    decision_type: DecisionType
    outcome: Priority
    reason: str
    reviewer: str
    recorded_at: str
    advisory_priority: Priority | None
    advisory_rationale: str | None
    advisory_evidence: list[str]
    model: str | None
    recommendation_created_at: str | None


DecisionHistory = list[DecisionAuditEntry]
