from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DecisionRecord
from app.repositories import DecisionRepository
from app.schemas import DecisionRequest, Priority


@pytest.mark.asyncio
async def test_decision_repository_commits_and_returns_audit_record() -> None:
    session = Mock(spec=AsyncSession)
    session.commit = AsyncMock()
    session.refresh = AsyncMock()

    async def populate_server_fields(record: DecisionRecord) -> None:
        record.recorded_at = datetime(2026, 10, 5, 18, 30, tzinfo=UTC)

    session.refresh.side_effect = populate_server_fields
    repository = DecisionRepository(session)
    request = DecisionRequest(
        case_id="case-1027",
        outcome=Priority.standard,
        reason="The source evidence was reviewed by the caseworker.",
        reviewer="Test reviewer",
    )

    decision = await repository.add(request)

    session.add.assert_called_once()
    session.commit.assert_awaited_once()
    session.refresh.assert_awaited_once()
    assert decision.case_id == "case-1027"
    assert decision.outcome == Priority.standard
    assert decision.recorded_at == "2026-10-05T18:30:00+00:00"
