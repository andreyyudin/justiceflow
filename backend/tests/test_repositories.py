from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DecisionRecord, RecommendationRecord
from app.repositories import DecisionRepository
from app.schemas import (
    DecisionRequest,
    DecisionType,
    Priority,
    Recommendation,
    RecommendationCreate,
)


def recommendation(
    *,
    recommendation_id: UUID | None = None,
    priority: Priority = Priority.high,
) -> Recommendation:
    return Recommendation(
        id=recommendation_id or uuid4(),
        case_id="case-1042",
        recommendation=priority,
        rationale="The recorded source information requires prompt review.",
        evidence=["Source summary: Synthetic source summary."],
        model="qwen3:4b",
        latency_ms=1234,
        created_at=datetime(2026, 10, 6, 12, 0, tzinfo=UTC).isoformat(),
    )


@pytest.mark.asyncio
async def test_recommendation_repository_persists_immutable_snapshot() -> None:
    session = Mock(spec=AsyncSession)
    session.commit = AsyncMock()
    session.refresh = AsyncMock()

    recommendation_id = uuid4()

    async def populate_server_fields(record: RecommendationRecord) -> None:
        record.id = recommendation_id
        record.created_at = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)

    session.refresh.side_effect = populate_server_fields
    repository = DecisionRepository(session)
    create = RecommendationCreate(
        case_id="case-1042",
        recommendation=Priority.high,
        rationale="The recorded source information requires prompt review.",
        evidence=["Source summary: Synthetic source summary."],
        model="qwen3:4b",
        model_confidence=0.83,
        latency_ms=1234,
    )

    result = await repository.add_recommendation(create)

    session.add.assert_called_once()
    persisted = session.add.call_args.args[0]
    assert isinstance(persisted, RecommendationRecord)
    assert persisted.case_id == "case-1042"
    assert persisted.model_confidence == 0.83
    session.commit.assert_awaited_once()
    session.refresh.assert_awaited_once_with(persisted)
    assert result.id == recommendation_id
    assert result.recommendation == Priority.high
    assert result.evidence == ["Source summary: Synthetic source summary."]
    assert result.created_at == "2026-10-06T12:00:00+00:00"
    assert not hasattr(result, "model_confidence")


@pytest.mark.asyncio
async def test_recommendation_repository_returns_snapshot_by_id() -> None:
    session = Mock(spec=AsyncSession)
    session.get = AsyncMock()
    recommendation_id = uuid4()
    session.get.return_value = SimpleNamespace(
        id=recommendation_id,
        case_id="case-1042",
        recommendation="urgent",
        rationale="The recorded hearing deadline requires urgent review.",
        evidence=["Recorded operational flags: hearing deadline"],
        model="qwen3:4b",
        model_confidence=0.91,
        latency_ms=987,
        created_at=datetime(2026, 10, 6, 12, 5, tzinfo=UTC),
    )

    result = await DecisionRepository(session).get_recommendation(
        recommendation_id,
    )

    session.get.assert_awaited_once_with(
        RecommendationRecord,
        recommendation_id,
    )
    assert result is not None
    assert result.id == recommendation_id
    assert result.recommendation == Priority.urgent


@pytest.mark.asyncio
async def test_recommendation_repository_returns_none_for_unknown_id() -> None:
    session = Mock(spec=AsyncSession)
    session.get = AsyncMock(return_value=None)

    result = await DecisionRepository(session).get_recommendation(uuid4())

    assert result is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("final_priority", "expected_type"),
    [
        (Priority.high, DecisionType.accepted),
        (Priority.urgent, DecisionType.overridden),
    ],
)
async def test_decision_repository_links_recommendation_and_derives_type(
    final_priority: Priority,
    expected_type: DecisionType,
) -> None:
    session = Mock(spec=AsyncSession)
    session.commit = AsyncMock()
    session.refresh = AsyncMock()

    async def populate_server_fields(record: DecisionRecord) -> None:
        record.recorded_at = datetime(2026, 10, 6, 12, 10, tzinfo=UTC)

    session.refresh.side_effect = populate_server_fields
    persisted_recommendation = recommendation(priority=Priority.high)
    request = DecisionRequest(
        case_id="case-1042",
        recommendation_id=persisted_recommendation.id,
        outcome=final_priority,
        reason="The source evidence was reviewed by the caseworker.",
    )

    decision = await DecisionRepository(session).add(
        request,
        reviewer="Test reviewer",
        recommendation=persisted_recommendation,
    )

    persisted = session.add.call_args.args[0]
    assert isinstance(persisted, DecisionRecord)
    assert persisted.recommendation_id == persisted_recommendation.id
    assert persisted.decision_type == expected_type.value
    assert decision.recommendation_id == persisted_recommendation.id
    assert decision.decision_type == expected_type
    assert decision.outcome == final_priority
    assert decision.recorded_at == "2026-10-06T12:10:00+00:00"


@pytest.mark.asyncio
async def test_latest_decision_per_case_builds_read_model() -> None:
    session = Mock(spec=AsyncSession)
    scalar_result = Mock()
    session.scalars = AsyncMock(return_value=scalar_result)
    scalar_result.all.return_value = [
        SimpleNamespace(
            case_id="case-1042",
            outcome="urgent",
            reason="Latest reviewed decision.",
            reviewer="Casey Worker",
            recorded_at=datetime(2026, 10, 6, 11, 30, tzinfo=UTC),
        ),
        SimpleNamespace(
            case_id="case-1042",
            outcome="high",
            reason="Older reviewed decision.",
            reviewer="Casey Worker",
            recorded_at=datetime(2026, 10, 6, 11, 20, tzinfo=UTC),
        ),
        SimpleNamespace(
            case_id="case-1027",
            outcome="standard",
            reason="Routine evidence reviewed.",
            reviewer="Casey Worker",
            recorded_at=datetime(2026, 10, 6, 11, 10, tzinfo=UTC),
        ),
    ]

    latest = await DecisionRepository(session).latest_by_case_id()

    assert latest["case-1042"].outcome == Priority.urgent
    assert latest["case-1042"].reason == "Latest reviewed decision."
    assert latest["case-1027"].outcome == Priority.standard
    assert len(latest) == 2


@pytest.mark.asyncio
async def test_latest_recommendation_id_is_scoped_to_case() -> None:
    session = Mock(spec=AsyncSession)
    recommendation_id = uuid4()
    session.scalar = AsyncMock(return_value=recommendation_id)

    result = await DecisionRepository(session).latest_recommendation_id("case-1042")

    assert result == recommendation_id
    statement = session.scalar.await_args.args[0]
    compiled = str(statement)
    assert "recommendations.case_id" in compiled
    assert "recommendations.created_at DESC" in compiled
    assert "recommendations.id DESC" in compiled


@pytest.mark.asyncio
async def test_decision_for_recommendation_returns_existing_decision() -> None:
    session = Mock(spec=AsyncSession)
    session.scalar = AsyncMock()
    recommendation_id = uuid4()
    session.scalar.return_value = SimpleNamespace(
        case_id="case-1042",
        recommendation_id=recommendation_id,
        decision_type="accepted",
        outcome="high",
        reason="The recorded source evidence was reviewed.",
        reviewer="Casey Worker",
        recorded_at=datetime(2026, 10, 6, 12, 20, tzinfo=UTC),
    )

    result = await DecisionRepository(session).decision_for_recommendation(recommendation_id)

    assert result is not None
    assert result.recommendation_id == recommendation_id
    assert result.decision_type == DecisionType.accepted
    assert result.outcome == Priority.high


@pytest.mark.asyncio
async def test_decision_for_recommendation_returns_none_when_unconsumed() -> None:
    session = Mock(spec=AsyncSession)
    session.scalar = AsyncMock(return_value=None)

    result = await DecisionRepository(session).decision_for_recommendation(uuid4())

    assert result is None


@pytest.mark.asyncio
async def test_decision_history_includes_linked_and_legacy_entries() -> None:
    session = Mock(spec=AsyncSession)
    result = Mock()
    session.execute = AsyncMock(return_value=result)
    recommendation_id = uuid4()

    linked_decision = SimpleNamespace(
        id=uuid4(),
        case_id="case-1027",
        recommendation_id=recommendation_id,
        decision_type="accepted",
        outcome="standard",
        reason="The grounded source evidence was reviewed.",
        reviewer="Casey Worker",
        recorded_at=datetime(2026, 10, 6, 12, 30, tzinfo=UTC),
    )
    linked_recommendation = SimpleNamespace(
        id=recommendation_id,
        recommendation="standard",
        rationale="The complete routine request can remain standard.",
        evidence=[
            "Source summary: Routine request.",
            "Service: Prisons",
        ],
        model="qwen3:4b",
        created_at=datetime(2026, 10, 6, 12, 25, tzinfo=UTC),
    )
    legacy_decision = SimpleNamespace(
        id=uuid4(),
        case_id="case-1042",
        recommendation_id=None,
        decision_type="legacy",
        outcome="urgent",
        reason="Historical decision recorded before recommendation provenance.",
        reviewer="Casey Worker",
        recorded_at=datetime(2026, 10, 6, 11, 30, tzinfo=UTC),
    )
    result.all.return_value = [
        (linked_decision, linked_recommendation),
        (legacy_decision, None),
    ]

    history = await DecisionRepository(session).decision_history()

    session.execute.assert_awaited_once()
    statement = session.execute.await_args.args[0]
    compiled = str(statement)
    assert "LEFT OUTER JOIN recommendations" in compiled
    assert "decisions.recorded_at DESC" in compiled
    assert "decisions.id DESC" in compiled

    assert len(history) == 2

    linked = history[0]
    assert linked.case_id == "case-1027"
    assert linked.recommendation_id == recommendation_id
    assert linked.decision_type == DecisionType.accepted
    assert linked.outcome == Priority.standard
    assert linked.advisory_priority == Priority.standard
    assert linked.advisory_rationale == ("The complete routine request can remain standard.")
    assert linked.advisory_evidence == [
        "Source summary: Routine request.",
        "Service: Prisons",
    ]
    assert linked.model == "qwen3:4b"
    assert linked.recommendation_created_at == "2026-10-06T12:25:00+00:00"
    assert not hasattr(linked, "model_confidence")

    legacy = history[1]
    assert legacy.case_id == "case-1042"
    assert legacy.recommendation_id is None
    assert legacy.decision_type == DecisionType.legacy
    assert legacy.outcome == Priority.urgent
    assert legacy.advisory_priority is None
    assert legacy.advisory_rationale is None
    assert legacy.advisory_evidence == []
    assert legacy.model is None
    assert legacy.recommendation_created_at is None
