from datetime import UTC, datetime
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from app.auth import Identity, Role
from app.main import app, get_decision_repository, get_identity
from app.repositories import DecisionRepository
from app.schemas import Decision, Priority

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


def test_cases_returns_synthetic_queue_for_caseworker() -> None:
    app.dependency_overrides[get_identity] = identity_override(CASEWORKER)
    try:
        response = client.get("/api/cases")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    cases = response.json()
    assert len(cases) == 4
    assert cases[0]["reference"] == "JF-2026-1042"


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
    repository.add.return_value = Decision(
        case_id="case-1027",
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
                "outcome": "standard",
                "reason": "Source evidence reviewed and recommendation accepted.",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    body = response.json()
    assert body["case_id"] == "case-1027"
    assert body["reviewer"] == CASEWORKER.display_name
    assert body["recorded_at"].endswith("+00:00")
    repository.add.assert_awaited_once()
    request = repository.add.await_args.args[0]
    assert request.case_id == "case-1027"
    assert repository.add.await_args.kwargs == {
        "reviewer": CASEWORKER.display_name,
    }


def test_unknown_case_decision_is_rejected() -> None:
    app.dependency_overrides[get_identity] = identity_override(CASEWORKER)
    try:
        response = client.post(
            "/api/decisions",
            json={
                "case_id": "missing",
                "outcome": "standard",
                "reason": "Source evidence reviewed and recommendation accepted.",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json() == {"detail": "Case not found"}


def test_identity_endpoint_returns_validated_identity() -> None:
    app.dependency_overrides[get_identity] = identity_override(CASEWORKER)
    try:
        response = client.get("/api/identity")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == CASEWORKER.model_dump(mode="json")


def test_auditor_can_read_cases_but_cannot_triage_or_decide() -> None:
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
