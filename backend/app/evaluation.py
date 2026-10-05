from dataclasses import dataclass

from .schemas import Case, Priority
from .triage import apply_safety_floor


@dataclass(frozen=True)
class EvaluationScenario:
    name: str
    case: Case
    model_recommendation: Priority
    expected_recommendation: Priority


@dataclass(frozen=True)
class EvaluationResult:
    scenario: str
    actual: Priority
    expected: Priority
    passed: bool


@dataclass(frozen=True)
class EvaluationReport:
    results: tuple[EvaluationResult, ...]
    passed: int
    total: int
    pass_rate: float


def evaluate_scenario(scenario: EvaluationScenario) -> EvaluationResult:
    actual = apply_safety_floor(
        scenario.case,
        scenario.model_recommendation,
    )
    return EvaluationResult(
        scenario=scenario.name,
        actual=actual,
        expected=scenario.expected_recommendation,
        passed=actual == scenario.expected_recommendation,
    )


def evaluate_scenarios(
    scenarios: tuple[EvaluationScenario, ...],
) -> EvaluationReport:
    results = tuple(evaluate_scenario(scenario) for scenario in scenarios)
    passed = sum(result.passed for result in results)
    total = len(results)
    pass_rate = passed / total if total else 0.0
    return EvaluationReport(
        results=results,
        passed=passed,
        total=total,
        pass_rate=pass_rate,
    )
