from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

from app.auth import Identity, Role
from app.main import app, get_decision_repository, get_identity
from app.repositories import DecisionRepository
from app.schemas import (
    Decision,
    DecisionAuditEntry,
    DecisionType,
    LatestDecision,
    Priority,
    Recommendation,
)
from app.triage import GeneratedRecommendation, ModelOutputSafetyError

client = TestClient(app)

CASEWORKER = Identity(
    subject="caseworker-001",
    display_name="Casey Worker",
    role=Role.caseworker,
)
AUDITOR = Identity(
    subject="auditor-001",
    display_name="Avery Auditor",
    role=Role.auditor,
)


def repository_override(repository: AsyncMock):
    async def override() -> AsyncMock:
        return repository

    return override


def identity_override(identity: Identity):
    def override() -> Identity:
        return identity

    return override


def test_health_reports_configured_local_model() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "model": "qwen3:4b"}


def test_cases_returns_decision_projected_queue_for_caseworker() -> None:
    repository = AsyncMock(spec=DecisionRepository)
    repository.latest_by_case_id.return_value = {}
    app.dependency_overrides[get_decision_repository] = repository_override(repository)
    app.dependency_overrides[get_identity] = identity_override(CASEWORKER)
    try:
        response = client.get("/api/cases")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    cases = response.json()
    assert len(cases) == 4
    assert cases[0]["reference"] == "JF-2026-1042"
    assert cases[0]["latest_decision"] is None
    repository.latest_by_case_id.assert_awaited_once()


def test_latest_human_decision_updates_case_projection() -> None:
    repository = AsyncMock(spec=DecisionRepository)
    repository.latest_by_case_id.return_value = {
        "case-1042": LatestDecision(
            outcome=Priority.urgent,
            reason="Housing evidence requires urgent handling.",
            reviewer=CASEWORKER.display_name,
            recorded_at=datetime(2026, 10, 6, 11, 30, tzinfo=UTC).isoformat(),
        )
    }
    app.dependency_overrides[get_decision_repository] = repository_override(repository)
    app.dependency_overrides[get_identity] = identity_override(CASEWORKER)
    try:
        response = client.get("/api/cases")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    projected = response.json()[0]
    assert projected["priority"] == "urgent"
    assert projected["status"] == "approved"
    assert projected["latest_decision"]["reviewer"] == CASEWORKER.display_name
    assert projected["latest_decision"]["reason"] == ("Housing evidence requires urgent handling.")


def test_triage_persists_recommendation_and_returns_identifier() -> None:
    repository = AsyncMock(spec=DecisionRepository)
    recommendation_id = uuid4()
    generated = GeneratedRecommendation(
        case_id="case-1027",
        recommendation=Priority.standard,
        rationale="The complete routine request can remain at standard priority.",
        evidence=["Source summary: Routine request."],
        model="qwen3:4b",
        model_confidence=0.82,
        latency_ms=321,
    )
    repository.add_recommendation.return_value = Recommendation(
        id=recommendation_id,
        case_id=generated.case_id,
        recommendation=generated.recommendation,
        rationale=generated.rationale,
        evidence=generated.evidence,
        model=generated.model,
        latency_ms=generated.latency_ms,
        created_at=datetime(2026, 10, 6, 12, 0, tzinfo=UTC).isoformat(),
    )
    app.dependency_overrides[get_decision_repository] = repository_override(repository)
    app.dependency_overrides[get_identity] = identity_override(CASEWORKER)
    try:
        with patch("app.main.OllamaClient.triage", AsyncMock(return_value=generated)):
            response = client.post("/api/triage", json={"case_id": "case-1027"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["recommendation_id"] == str(recommendation_id)
    assert body["recommendation"] == "standard"
    assert "confidence" not in body
    repository.add_recommendation.assert_awaited_once()
    create = repository.add_recommendation.await_args.args[0]
    assert create.model_confidence == 0.82


def test_unknown_case_cannot_be_triaged() -> None:
    app.dependency_overrides[get_identity] = identity_override(CASEWORKER)
    try:
        response = client.post("/api/triage", json={"case_id": "missing"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json() == {"detail": "Case not found"}


def test_human_decision_uses_authenticated_reviewer() -> None:
    repository = AsyncMock(spec=DecisionRepository)
    recommendation_id = uuid4()
    recommendation = Recommendation(
        id=recommendation_id,
        case_id="case-1027",
        recommendation=Priority.standard,
        rationale="The complete routine request can remain at standard priority.",
        evidence=["Source summary: Routine request."],
        model="qwen3:4b",
        latency_ms=321,
        created_at=datetime(2026, 10, 5, 18, 25, tzinfo=UTC).isoformat(),
    )
    repository.get_recommendation.return_value = recommendation
    repository.decision_for_recommendation.return_value = None
    repository.latest_recommendation_id.return_value = recommendation_id
    repository.add.return_value = Decision(
        case_id="case-1027",
        recommendation_id=recommendation_id,
        decision_type=DecisionType.accepted,
        outcome=Priority.standard,
        reason="Source evidence reviewed and recommendation accepted.",
        reviewer=CASEWORKER.display_name,
        recorded_at=datetime(2026, 10, 5, 18, 30, tzinfo=UTC).isoformat(),
    )
    app.dependency_overrides[get_decision_repository] = repository_override(repository)
    app.dependency_overrides[get_identity] = identity_override(CASEWORKER)
    try:
        response = client.post(
            "/api/decisions",
            json={
                "case_id": "case-1027",
                "recommendation_id": str(recommendation_id),
                "outcome": "standard",
                "reason": "Source evidence reviewed and recommendation accepted.",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    body = response.json()
    assert body["case_id"] == "case-1027"
    assert body["recommendation_id"] == str(recommendation_id)
    assert body["decision_type"] == "accepted"
    assert body["reviewer"] == CASEWORKER.display_name
    assert body["recorded_at"].endswith("+00:00")
    repository.get_recommendation.assert_awaited_once_with(recommendation_id)
    repository.decision_for_recommendation.assert_awaited_once_with(recommendation_id)
    repository.latest_recommendation_id.assert_awaited_once_with("case-1027")
    repository.add.assert_awaited_once()
    request = repository.add.await_args.args[0]
    assert request.case_id == "case-1027"
    assert request.recommendation_id == recommendation_id
    assert repository.add.await_args.kwargs == {
        "reviewer": CASEWORKER.display_name,
        "recommendation": recommendation,
    }


def test_unknown_case_decision_is_rejected() -> None:
    recommendation_id = uuid4()
    app.dependency_overrides[get_identity] = identity_override(CASEWORKER)
    try:
        response = client.post(
            "/api/decisions",
            json={
                "case_id": "missing",
                "recommendation_id": str(recommendation_id),
                "outcome": "standard",
                "reason": "Source evidence reviewed and recommendation accepted.",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json() == {"detail": "Case not found"}


def test_decision_rejects_unknown_or_wrong_case_recommendation() -> None:
    repository = AsyncMock(spec=DecisionRepository)
    recommendation_id = uuid4()
    repository.get_recommendation.side_effect = [
        None,
        Recommendation(
            id=recommendation_id,
            case_id="case-1042",
            recommendation=Priority.high,
            rationale="The recorded source information requires prompt review.",
            evidence=["Source summary: Synthetic source summary."],
            model="qwen3:4b",
            latency_ms=123,
            created_at=datetime(2026, 10, 6, 12, 0, tzinfo=UTC).isoformat(),
        ),
    ]
    app.dependency_overrides[get_decision_repository] = repository_override(repository)
    app.dependency_overrides[get_identity] = identity_override(CASEWORKER)
    payload = {
        "case_id": "case-1027",
        "recommendation_id": str(recommendation_id),
        "outcome": "standard",
        "reason": "The source evidence was reviewed by the caseworker.",
    }
    try:
        missing_response = client.post("/api/decisions", json=payload)
        mismatch_response = client.post("/api/decisions", json=payload)
    finally:
        app.dependency_overrides.clear()

    assert missing_response.status_code == 404
    assert missing_response.json() == {"detail": "Recommendation not found."}
    assert mismatch_response.status_code == 409
    assert mismatch_response.json() == {"detail": "Recommendation does not belong to this case."}
    assert repository.get_recommendation.await_count == 2
    repository.decision_for_recommendation.assert_not_awaited()
    repository.latest_recommendation_id.assert_not_awaited()
    repository.add.assert_not_awaited()


def test_observability_status_is_restricted_to_auditor() -> None:
    app.dependency_overrides[get_identity] = identity_override(AUDITOR)
    try:
        auditor_response = client.get("/api/observability")
    finally:
        app.dependency_overrides.clear()

    assert auditor_response.status_code == 200
    assert auditor_response.json() == {
        "structured_logs": True,
        "langfuse_enabled": True,
        "environment": "local",
        "release": "development",
    }

    app.dependency_overrides[get_identity] = identity_override(CASEWORKER)
    try:
        caseworker_response = client.get("/api/observability")
    finally:
        app.dependency_overrides.clear()

    assert caseworker_response.status_code == 403
    assert caseworker_response.json() == {"detail": "Role is not permitted for this operation."}


def test_identity_endpoint_returns_validated_identity() -> None:
    app.dependency_overrides[get_identity] = identity_override(CASEWORKER)
    try:
        response = client.get("/api/identity")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == CASEWORKER.model_dump(mode="json")


def test_auditor_can_read_cases_but_cannot_triage_or_decide() -> None:
    repository = AsyncMock(spec=DecisionRepository)
    recommendation_id = uuid4()
    repository.latest_by_case_id.return_value = {}
    app.dependency_overrides[get_decision_repository] = repository_override(repository)
    app.dependency_overrides[get_identity] = identity_override(AUDITOR)
    try:
        cases_response = client.get("/api/cases")
        triage_response = client.post(
            "/api/triage",
            json={"case_id": "case-1027"},
        )
        decision_response = client.post(
            "/api/decisions",
            json={
                "case_id": "case-1027",
                "recommendation_id": str(recommendation_id),
                "outcome": "standard",
                "reason": "Auditor must not record a human decision.",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert cases_response.status_code == 200
    assert triage_response.status_code == 403
    assert decision_response.status_code == 403
    expected = {"detail": "Role is not permitted for this operation."}
    assert triage_response.json() == expected
    assert decision_response.json() == expected


def test_missing_bearer_token_is_rejected() -> None:
    response = client.get("/api/cases")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json() == {"detail": "Bearer token is required."}


def test_malformed_authorization_header_is_rejected() -> None:
    response = client.get(
        "/api/cases",
        headers={"Authorization": "Basic credentials"},
    )

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json() == {"detail": "Authorization header must use the Bearer scheme."}


def recommendation_fixture(recommendation_id) -> Recommendation:
    return Recommendation(
        id=recommendation_id,
        case_id="case-1027",
        recommendation=Priority.standard,
        rationale="The complete routine request can remain at standard priority.",
        evidence=["Source summary: Routine request."],
        model="qwen3:4b",
        latency_ms=321,
        created_at=datetime(2026, 10, 6, 12, 25, tzinfo=UTC).isoformat(),
    )


def decision_fixture(
    recommendation_id,
    *,
    outcome: Priority = Priority.standard,
    reason: str = "The source evidence was reviewed by the caseworker.",
) -> Decision:
    return Decision(
        case_id="case-1027",
        recommendation_id=recommendation_id,
        decision_type=DecisionType.accepted,
        outcome=outcome,
        reason=reason,
        reviewer=CASEWORKER.display_name,
        recorded_at=datetime(2026, 10, 6, 12, 30, tzinfo=UTC).isoformat(),
    )


def test_exact_decision_replay_is_idempotent() -> None:
    repository = AsyncMock(spec=DecisionRepository)
    recommendation_id = uuid4()
    reason = "The source evidence was reviewed by the caseworker."
    repository.get_recommendation.return_value = recommendation_fixture(recommendation_id)
    repository.decision_for_recommendation.return_value = decision_fixture(
        recommendation_id,
        reason=reason,
    )
    app.dependency_overrides[get_decision_repository] = repository_override(repository)
    app.dependency_overrides[get_identity] = identity_override(CASEWORKER)
    try:
        response = client.post(
            "/api/decisions",
            json={
                "case_id": "case-1027",
                "recommendation_id": str(recommendation_id),
                "outcome": "standard",
                "reason": reason,
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["recommendation_id"] == str(recommendation_id)
    assert response.json()["decision_type"] == "accepted"
    repository.latest_recommendation_id.assert_not_awaited()
    repository.add.assert_not_awaited()


def test_conflicting_decision_replay_is_rejected() -> None:
    repository = AsyncMock(spec=DecisionRepository)
    recommendation_id = uuid4()
    repository.get_recommendation.return_value = recommendation_fixture(recommendation_id)
    repository.decision_for_recommendation.return_value = decision_fixture(
        recommendation_id,
        outcome=Priority.high,
    )
    app.dependency_overrides[get_decision_repository] = repository_override(repository)
    app.dependency_overrides[get_identity] = identity_override(CASEWORKER)
    try:
        response = client.post(
            "/api/decisions",
            json={
                "case_id": "case-1027",
                "recommendation_id": str(recommendation_id),
                "outcome": "standard",
                "reason": "The source evidence was reviewed by the caseworker.",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409
    assert response.json() == {"detail": "Recommendation already has a different human decision."}
    repository.latest_recommendation_id.assert_not_awaited()
    repository.add.assert_not_awaited()


def test_stale_recommendation_is_rejected() -> None:
    repository = AsyncMock(spec=DecisionRepository)
    recommendation_id = uuid4()
    repository.get_recommendation.return_value = recommendation_fixture(recommendation_id)
    repository.decision_for_recommendation.return_value = None
    repository.latest_recommendation_id.return_value = uuid4()
    app.dependency_overrides[get_decision_repository] = repository_override(repository)
    app.dependency_overrides[get_identity] = identity_override(CASEWORKER)
    try:
        response = client.post(
            "/api/decisions",
            json={
                "case_id": "case-1027",
                "recommendation_id": str(recommendation_id),
                "outcome": "standard",
                "reason": "The source evidence was reviewed by the caseworker.",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409
    assert response.json() == {"detail": "Recommendation is stale. Generate a new recommendation."}
    repository.latest_recommendation_id.assert_awaited_once_with("case-1027")
    repository.add.assert_not_awaited()


def test_decision_history_is_restricted_to_auditor() -> None:
    repository = AsyncMock(spec=DecisionRepository)
    recommendation_id = uuid4()
    history = [
        DecisionAuditEntry(
            case_id="case-1027",
            recommendation_id=recommendation_id,
            decision_type=DecisionType.accepted,
            outcome=Priority.standard,
            reason="The grounded source evidence was reviewed.",
            reviewer=CASEWORKER.display_name,
            recorded_at=datetime(2026, 10, 6, 12, 30, tzinfo=UTC).isoformat(),
            advisory_priority=Priority.standard,
            advisory_rationale=("The complete routine request can remain at standard priority."),
            advisory_evidence=[
                "Source summary: Routine request.",
                "Service: Prisons",
            ],
            model="qwen3:4b",
            recommendation_created_at=datetime(
                2026,
                10,
                6,
                12,
                25,
                tzinfo=UTC,
            ).isoformat(),
        ),
        DecisionAuditEntry(
            case_id="case-1042",
            recommendation_id=None,
            decision_type=DecisionType.legacy,
            outcome=Priority.urgent,
            reason="Historical decision recorded before recommendation provenance.",
            reviewer=CASEWORKER.display_name,
            recorded_at=datetime(2026, 10, 6, 11, 30, tzinfo=UTC).isoformat(),
            advisory_priority=None,
            advisory_rationale=None,
            advisory_evidence=[],
            model=None,
            recommendation_created_at=None,
        ),
    ]
    repository.decision_history.return_value = history
    app.dependency_overrides[get_decision_repository] = repository_override(repository)

    app.dependency_overrides[get_identity] = identity_override(AUDITOR)
    try:
        auditor_response = client.get("/api/decisions/history")
    finally:
        app.dependency_overrides.clear()

    assert auditor_response.status_code == 200
    body = auditor_response.json()
    assert len(body) == 2
    assert body[0]["decision_type"] == "accepted"
    assert body[0]["recommendation_id"] == str(recommendation_id)
    assert body[0]["advisory_priority"] == "standard"
    assert body[0]["advisory_evidence"] == [
        "Source summary: Routine request.",
        "Service: Prisons",
    ]
    assert body[0]["model"] == "qwen3:4b"
    assert "model_confidence" not in body[0]
    assert body[1]["decision_type"] == "legacy"
    assert body[1]["recommendation_id"] is None
    assert body[1]["advisory_priority"] is None
    assert body[1]["advisory_evidence"] == []
    repository.decision_history.assert_awaited_once()

    caseworker_repository = AsyncMock(spec=DecisionRepository)
    app.dependency_overrides[get_decision_repository] = repository_override(caseworker_repository)
    app.dependency_overrides[get_identity] = identity_override(CASEWORKER)
    try:
        caseworker_response = client.get("/api/decisions/history")
    finally:
        app.dependency_overrides.clear()

    assert caseworker_response.status_code == 403
    assert caseworker_response.json() == {"detail": "Role is not permitted for this operation."}
    caseworker_repository.decision_history.assert_not_awaited()


def test_decision_history_requires_authentication() -> None:
    response = client.get("/api/decisions/history")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json() == {"detail": "Bearer token is required."}


def test_prohibited_model_output_is_rejected_without_persistence() -> None:
    repository = AsyncMock(spec=DecisionRepository)
    app.dependency_overrides[get_decision_repository] = repository_override(repository)
    app.dependency_overrides[get_identity] = identity_override(CASEWORKER)

    try:
        with patch(
            "app.main.OllamaClient.triage",
            AsyncMock(
                side_effect=ModelOutputSafetyError("Model rationale contained prohibited content.")
            ),
        ):
            response = client.post(
                "/api/triage",
                json={"case_id": "case-1027"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json() == {
        "detail": ("Local AI returned an invalid response. No recommendation was recorded.")
    }
    repository.add_recommendation.assert_not_awaited()
