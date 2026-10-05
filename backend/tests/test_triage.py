from app.cases import get_case
from app.schemas import Priority
from app.triage import apply_safety_floor


def test_hearing_deadline_forces_urgent_review() -> None:
    case = get_case("case-1038")
    assert case is not None
    assert apply_safety_floor(case, Priority.standard) == Priority.urgent


def test_accessibility_cannot_be_downgraded_to_standard() -> None:
    case = get_case("case-1038")
    assert case is not None
    assert apply_safety_floor(case, Priority.standard) != Priority.standard


def test_routine_case_keeps_model_recommendation() -> None:
    case = get_case("case-1027")
    assert case is not None
    assert apply_safety_floor(case, Priority.standard) == Priority.standard
