from datetime import UTC, datetime
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from app.main import app, get_decision_repository
from app.repositories import DecisionRepository
from app.schemas import Decision, Priority

client = TestClient(app)


def repository_override(repository: AsyncMock):
    async def override() -> AsyncMock:
        return repository

    return override


def test_health_reports_configured_local_model() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "model": "qwen3:4b"}


def test_cases_returns_synthetic_queue() -> None:
    response = client.get("/api/cases")

    assert response.status_code == 200
    cases = response.json()
    assert len(cases) == 4
    assert cases[0]["reference"] == "JF-2026-1042"


def test_unknown_case_cannot_be_triaged() -> None:
    response = client.post("/api/triage", json={"case_id": "missing"})

    assert response.status_code == 404
    assert response.json() == {"detail": "Case not found"}


def test_human_decision_is_recorded() -> None:
    repository = AsyncMock(spec=DecisionRepository)
    repository.add.return_value = Decision(
        case_id="case-1027",
        outcome=Priority.standard,
        reason="Source evidence reviewed and recommendation accepted.",
        reviewer="Test reviewer",
        recorded_at=datetime(2026, 10, 5, 18, 30, tzinfo=UTC).isoformat(),
    )
    app.dependency_overrides[get_decision_repository] = repository_override(repository)
    try:
        response = client.post(
            "/api/decisions",
            json={
                "case_id": "case-1027",
                "outcome": "standard",
                "reason": "Source evidence reviewed and recommendation accepted.",
                "reviewer": "Test reviewer",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    body = response.json()
    assert body["case_id"] == "case-1027"
    assert body["reviewer"] == "Test reviewer"
    assert body["recorded_at"].endswith("+00:00")
    repository.add.assert_awaited_once()


def test_unknown_case_decision_is_rejected() -> None:
    response = client.post(
        "/api/decisions",
        json={
            "case_id": "missing",
            "outcome": "standard",
            "reason": "Source evidence reviewed and recommendation accepted.",
            "reviewer": "Test reviewer",
        },
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Case not found"}
