from collections.abc import Sequence
from dataclasses import dataclass

from .schemas import Case, Priority
from .triage import GeneratedRecommendation, OllamaClient

StringSet = set[str]


@dataclass(frozen=True)
class ModelEvaluationScenario:
    name: str
    case: Case
    expected_final_priority: Priority
    forbidden_rationale_phrases: tuple[str, ...] = ()


@dataclass(frozen=True)
class ModelEvaluationResult:
    scenario: str
    passed: bool
    final_priority: Priority | None
    schema_valid: bool
    evidence_grounded: bool
    rationale_safe: bool
    latency_ms: int | None
    failures: tuple[str, ...]


@dataclass(frozen=True)
class ModelEvaluationReport:
    model: str
    results: tuple[ModelEvaluationResult, ...]
    passed: int
    total: int
    pass_rate: float


def evaluate_generated_recommendation(
    scenario: ModelEvaluationScenario,
    recommendation: GeneratedRecommendation,
) -> ModelEvaluationResult:
    failures: list[str] = []

    priority_matches = recommendation.recommendation == scenario.expected_final_priority
    if not priority_matches:
        failures.append(
            "expected final priority "
            f"{scenario.expected_final_priority.value}, got "
            f"{recommendation.recommendation.value}"
        )

    evidence_grounded = bool(recommendation.evidence) and all(
        evidence in expected_evidence_values(scenario.case) for evidence in recommendation.evidence
    )
    if not evidence_grounded:
        failures.append("evidence was empty or not rendered from trusted case fields")

    rationale = recommendation.rationale.casefold()
    forbidden_matches = [
        phrase for phrase in scenario.forbidden_rationale_phrases if phrase.casefold() in rationale
    ]
    rationale_safe = not forbidden_matches
    if forbidden_matches:
        failures.append("rationale contained forbidden phrase(s): " + ", ".join(forbidden_matches))

    return ModelEvaluationResult(
        scenario=scenario.name,
        passed=not failures,
        final_priority=recommendation.recommendation,
        schema_valid=True,
        evidence_grounded=evidence_grounded,
        rationale_safe=rationale_safe,
        latency_ms=recommendation.latency_ms,
        failures=tuple(failures),
    )


def failed_model_evaluation(
    scenario: ModelEvaluationScenario,
    exc: Exception,
) -> ModelEvaluationResult:
    return ModelEvaluationResult(
        scenario=scenario.name,
        passed=False,
        final_priority=None,
        schema_valid=False,
        evidence_grounded=False,
        rationale_safe=False,
        latency_ms=None,
        failures=(f"{type(exc).__name__}: {exc}",),
    )


async def evaluate_model_scenarios(
    client: OllamaClient,
    scenarios: Sequence[ModelEvaluationScenario],
) -> ModelEvaluationReport:
    results: list[ModelEvaluationResult] = []

    for scenario in scenarios:
        try:
            recommendation = await client.triage(scenario.case)
        except Exception as exc:
            results.append(failed_model_evaluation(scenario, exc))
            continue

        results.append(
            evaluate_generated_recommendation(
                scenario,
                recommendation,
            )
        )

    passed = sum(result.passed for result in results)
    total = len(results)

    return ModelEvaluationReport(
        model=client.model,
        results=tuple(results),
        passed=passed,
        total=total,
        pass_rate=passed / total if total else 0.0,
    )


def expected_evidence_values(case: Case) -> StringSet:
    risk_flags = (
        "Recorded operational flags: "
        + ", ".join(flag.replace("_", " ") for flag in case.risk_flags)
        if case.risk_flags
        else "Recorded operational flags: none"
    )
    return {
        f"Source summary: {case.summary}",
        f"Service: {case.service}",
        f"Waiting time: {case.days_waiting} days",
        risk_flags,
    }
