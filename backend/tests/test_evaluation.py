from app.evaluation import EvaluationScenario, evaluate_scenarios
from app.schemas import Case, CaseStatus, Priority


def synthetic_case() -> Case:
    return Case(
        id="eval-test",
        reference="EVAL-TEST",
        service="Courts",
        region="Synthetic",
        summary="Synthetic evaluation case.",
        received_at="2026-10-05T09:00:00Z",
        priority=Priority.urgent,
        status=CaseStatus.needs_review,
        risk_flags=["hearing_deadline"],
        days_waiting=1,
    )


def test_evaluation_report_scores_safety_floor() -> None:
    scenario = EvaluationScenario(
        name="deadline safety floor",
        case=synthetic_case(),
        model_recommendation=Priority.standard,
        expected_recommendation=Priority.urgent,
    )

    report = evaluate_scenarios((scenario,))

    assert report.passed == 1
    assert report.total == 1
    assert report.pass_rate == 1.0
    assert report.results[0].passed is True


def test_empty_evaluation_report_has_zero_pass_rate() -> None:
    report = evaluate_scenarios(())

    assert report.passed == 0
    assert report.total == 0
    assert report.pass_rate == 0.0
    assert report.results == ()
