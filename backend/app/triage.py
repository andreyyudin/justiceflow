import json
import time
from dataclasses import dataclass

import httpx

from .llm_observability import LlmTelemetry
from .schemas import (
    Case,
    EvidenceSource,
    ModelTriageOutput,
    Priority,
)

SYSTEM_PROMPT = """You support a human justice caseworker.
Recommend only a queue priority: urgent, high, or standard.
Base the recommendation exclusively on the supplied synthetic case.
Never infer protected characteristics, guilt, risk of offending, or legal outcomes.
Return JSON with recommendation, rationale, evidence, and confidence.
Evidence must contain one or more source-field names chosen only from:
summary, service, days_waiting, risk_flags.
The recommendation is advisory and always requires human review."""

HIGH_RISK_FLAGS = {"accessibility", "hearing_deadline", "housing_instability"}
URGENT_FLAGS = {"hearing_deadline"}


@dataclass(frozen=True)
class GeneratedRecommendation:
    case_id: str
    recommendation: Priority
    rationale: str
    evidence: list[str]
    model: str
    model_confidence: float
    latency_ms: int


@dataclass(frozen=True)
class OllamaClient:
    base_url: str
    model: str
    timeout_seconds: float = 45.0
    telemetry: LlmTelemetry | None = None

    async def triage(self, case: Case) -> GeneratedRecommendation:
        started = time.perf_counter()
        generation = (
            self.telemetry.start_generation(
                model=self.model,
                case_id=case.id,
                service=case.service,
                risk_flag_count=len(case.risk_flags),
            )
            if self.telemetry
            else None
        )
        payload = {
            "model": self.model,
            "stream": False,
            "format": "json",
            "think": False,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "summary": case.summary,
                            "service": case.service,
                            "days_waiting": case.days_waiting,
                            "risk_flags": case.risk_flags,
                        }
                    ),
                },
            ],
            "options": {
                "temperature": 0,
                "num_predict": 256,
            },
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(f"{self.base_url}/api/chat", json=payload)
                response.raise_for_status()
            response_body = response.json()
            content = response_body["message"]["content"]
            parsed = ModelTriageOutput.model_validate_json(content)
            recommendation = apply_safety_floor(case, parsed.recommendation)
            latency_ms = round((time.perf_counter() - started) * 1000)
            result = GeneratedRecommendation(
                case_id=case.id,
                recommendation=recommendation,
                rationale=parsed.rationale,
                evidence=[
                    render_evidence(case, source) for source in dict.fromkeys(parsed.evidence)
                ],
                model=self.model,
                model_confidence=parsed.confidence,
                latency_ms=latency_ms,
            )
        except Exception as exc:
            if generation:
                generation.fail(
                    error_type=type(exc).__name__,
                    latency_ms=round((time.perf_counter() - started) * 1000),
                )
            raise

        if generation:
            generation.succeed(
                recommendation=recommendation.value,
                confidence=parsed.confidence,
                latency_ms=latency_ms,
                prompt_tokens=int(response_body.get("prompt_eval_count", 0)),
                completion_tokens=int(response_body.get("eval_count", 0)),
            )
        return result


def apply_safety_floor(case: Case, recommendation: Priority) -> Priority:
    flags = set(case.risk_flags)
    if flags & URGENT_FLAGS:
        return Priority.urgent
    if flags & HIGH_RISK_FLAGS and recommendation == Priority.standard:
        return Priority.high
    return recommendation


def render_evidence(case: Case, source: EvidenceSource) -> str:
    if source == EvidenceSource.summary:
        return f"Source summary: {case.summary}"
    if source == EvidenceSource.service:
        return f"Service: {case.service}"
    if source == EvidenceSource.days_waiting:
        return f"Waiting time: {case.days_waiting} days"
    if case.risk_flags:
        flags = ", ".join(flag.replace("_", " ") for flag in case.risk_flags)
        return f"Recorded operational flags: {flags}"
    return "Recorded operational flags: none"
