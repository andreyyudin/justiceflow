from enum import StrEnum

from pydantic import BaseModel, Field


class Priority(StrEnum):
    urgent = "urgent"
    high = "high"
    standard = "standard"


class CaseStatus(StrEnum):
    needs_review = "needs_review"
    approved = "approved"
    escalated = "escalated"


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


class TriageRequest(BaseModel):
    case_id: str


class TriageResult(BaseModel):
    case_id: str
    recommendation: Priority
    rationale: str
    evidence: list[str]
    confidence: float = Field(ge=0, le=1)
    requires_human_review: bool = True
    model: str
    latency_ms: int


class DecisionRequest(BaseModel):
    case_id: str
    outcome: Priority
    reason: str = Field(min_length=10, max_length=500)


class Decision(BaseModel):
    case_id: str
    outcome: Priority
    reason: str
    reviewer: str
    recorded_at: str
