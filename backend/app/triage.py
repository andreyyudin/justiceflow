import json
import time
from dataclasses import dataclass
from typing import Any

import httpx

from .llm_observability import LlmTelemetry
from .schemas import Case, Priority, TriageResult

SYSTEM_PROMPT = """You support a human justice caseworker.
Recommend only a queue priority: urgent, high, or standard.
Base the recommendation exclusively on the supplied synthetic case.
Never infer protected characteristics, guilt, risk of offending, or legal outcomes.
Return JSON with recommendation, rationale, evidence, and confidence.
The recommendation is advisory and always requires human review."""

HIGH_RISK_FLAGS = {"accessibility", "hearing_deadline", "housing_instability"}
URGENT_FLAGS = {"hearing_deadline"}


@dataclass(frozen=True)
class OllamaClient:
    base_url: str
    model: str
    timeout_seconds: float = 45.0
    telemetry: LlmTelemetry | None = None

    async def triage(self, case: Case) -> TriageResult:
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
            parsed: dict[str, Any] = json.loads(content)
            recommendation = Priority(parsed["recommendation"])
            recommendation = apply_safety_floor(case, recommendation)
            latency_ms = round((time.perf_counter() - started) * 1000)
            confidence = float(parsed["confidence"])
            result = TriageResult(
                case_id=case.id,
                recommendation=recommendation,
                rationale=str(parsed["rationale"]),
                evidence=[str(item) for item in parsed.get("evidence", [])][:4],
                confidence=confidence,
                requires_human_review=True,
                model=self.model,
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
                confidence=confidence,
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
