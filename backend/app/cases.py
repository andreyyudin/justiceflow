from .schemas import Case, CaseStatus, Priority

CASES = [
    Case(
        id="case-1042",
        reference="JF-2026-1042",
        service="Probation",
        region="London",
        summary=(
            "Appointment needs rescheduling after emergency accommodation move. "
            "Individual reports no access to prior correspondence."
        ),
        received_at="2026-10-05T08:40:00Z",
        priority=Priority.high,
        status=CaseStatus.needs_review,
        risk_flags=["housing_instability", "missed_contact"],
        days_waiting=1,
    ),
    Case(
        id="case-1038",
        reference="JF-2026-1038",
        service="Courts",
        region="North West",
        summary=(
            "Interpreter requirement was not transferred to the revised hearing record. "
            "Hearing is due within two working days."
        ),
        received_at="2026-10-03T15:12:00Z",
        priority=Priority.urgent,
        status=CaseStatus.needs_review,
        risk_flags=["accessibility", "hearing_deadline"],
        days_waiting=3,
    ),
    Case(
        id="case-1027",
        reference="JF-2026-1027",
        service="Prisons",
        region="West Midlands",
        summary=(
            "Routine request for an update to approved family contact details. "
            "Supporting information is complete."
        ),
        received_at="2026-09-30T10:05:00Z",
        priority=Priority.standard,
        status=CaseStatus.needs_review,
        risk_flags=[],
        days_waiting=6,
    ),
    Case(
        id="case-1019",
        reference="JF-2026-1019",
        service="Probation",
        region="Yorkshire",
        summary=(
            "Conflicting appointment notices are causing uncertainty about reporting "
            "requirements. One date has already passed."
        ),
        received_at="2026-09-28T09:20:00Z",
        priority=Priority.high,
        status=CaseStatus.escalated,
        risk_flags=["conflicting_records", "missed_contact"],
        days_waiting=8,
    ),
]


def get_case(case_id: str) -> Case | None:
    return next((case for case in CASES if case.id == case_id), None)
