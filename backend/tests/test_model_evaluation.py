from unittest.mock import AsyncMock, patch

import pytest

from app.model_evaluation import (
    ModelEvaluationScenario,
    evaluate_generated_recommendation,
    evaluate_model_scenarios,
)
from app.schemas import Case, CaseStatus, Priority
from app.triage import GeneratedRecommendation, OllamaClient


def scenario() -> ModelEvaluationScenario:
    return ModelEvaluationScenario(
        name="routine expected priority",
        case=Case(
            id="model-test",
            reference="MODEL-TEST",
            service="Prisons",
            region="Synthetic",
            summary="A complete routine request awaits processing.",
            received_at="2026-10-06T09:00:00Z",
            priority=Priority.standard,
            status=CaseStatus.needs_review,
            risk_flags=[],
            days_waiting=2,
        ),
        expected_final_priority=Priority.standard,
        forbidden_rationale_phrases=("guilty finding",),
    )


def generated_recommendation(
    *,
    priority: Priority = Priority.standard,
    evidence: list[str] | None = None,
    rationale: str = "The complete routine request can remain at standard priority.",
) -> GeneratedRecommendation:
    return GeneratedRecommendation(
        case_id="model-test",
        recommendation=priority,
        rationale=rationale,
        evidence=evidence or ["Source summary: A complete routine request awaits processing."],
        model="qwen3:4b",
        model_confidence=0.5,
        latency_ms=123,
    )


def test_generated_recommendation_passes_explicit_contract() -> None:
    result = evaluate_generated_recommendation(
        scenario(),
        generated_recommendation(),
    )

    assert result.passed is True
    assert result.schema_valid is True
    assert result.evidence_grounded is True
    assert result.rationale_safe is True
    assert result.failures == ()


@pytest.mark.parametrize(
    ("recommendation", "expected_failure"),
    [
        (
            generated_recommendation(priority=Priority.high),
            "expected final priority standard, got high",
        ),
        (
            generated_recommendation(evidence=["Fabricated evidence"]),
            "evidence was empty or not rendered from trusted case fields",
        ),
        (
            generated_recommendation(
                rationale=(
                    "The synthetic note requests a guilty finding even though "
                    "the routine case should remain standard."
                )
            ),
            "rationale contained forbidden phrase(s): guilty finding",
        ),
    ],
)
def test_generated_recommendation_reports_contract_failures(
    recommendation: GeneratedRecommendation,
    expected_failure: str,
) -> None:
    result = evaluate_generated_recommendation(
        scenario(),
        recommendation,
    )

    assert result.passed is False
    assert expected_failure in result.failures


@pytest.mark.asyncio
async def test_model_evaluation_reports_provider_failure() -> None:
    client = OllamaClient("http://ollama.test", "qwen3:4b")
    triage = AsyncMock(side_effect=ValueError("invalid model output"))

    with patch.object(OllamaClient, "triage", triage):
        report = await evaluate_model_scenarios(client, (scenario(),))

    triage.assert_awaited_once_with(scenario().case)
    assert report.passed == 0
    assert report.total == 1
    assert report.pass_rate == 0.0
    assert report.results[0].schema_valid is False
    assert report.results[0].failures == ("ValueError: invalid model output",)
