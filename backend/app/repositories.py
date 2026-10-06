from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import DecisionRecord, RecommendationRecord
from .schemas import (
    Decision,
    DecisionAuditEntry,
    DecisionHistory,
    DecisionRequest,
    DecisionType,
    LatestDecision,
    Priority,
    Recommendation,
    RecommendationCreate,
)


def ensure_utc_isoformat(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.isoformat()


def recommendation_from_record(record: RecommendationRecord) -> Recommendation:
    return Recommendation(
        id=record.id,
        case_id=record.case_id,
        recommendation=Priority(record.recommendation),
        rationale=record.rationale,
        evidence=list(record.evidence),
        model=record.model,
        latency_ms=record.latency_ms,
        created_at=ensure_utc_isoformat(record.created_at),
    )


def decision_from_record(record: DecisionRecord) -> Decision:
    return Decision(
        case_id=record.case_id,
        recommendation_id=record.recommendation_id,
        decision_type=DecisionType(record.decision_type),
        outcome=Priority(record.outcome),
        reason=record.reason,
        reviewer=record.reviewer,
        recorded_at=ensure_utc_isoformat(record.recorded_at),
    )


class DecisionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_recommendation(
        self,
        recommendation: RecommendationCreate,
    ) -> Recommendation:
        record = RecommendationRecord(
            case_id=recommendation.case_id,
            recommendation=recommendation.recommendation.value,
            rationale=recommendation.rationale,
            evidence=recommendation.evidence,
            model=recommendation.model,
            model_confidence=recommendation.model_confidence,
            latency_ms=recommendation.latency_ms,
        )
        self._session.add(record)
        await self._session.commit()
        await self._session.refresh(record)
        return recommendation_from_record(record)

    async def get_recommendation(
        self,
        recommendation_id: UUID,
    ) -> Recommendation | None:
        record = await self._session.get(
            RecommendationRecord,
            recommendation_id,
        )
        if record is None:
            return None
        return recommendation_from_record(record)

    async def latest_recommendation_id(self, case_id: str) -> UUID | None:
        statement = (
            select(RecommendationRecord.id)
            .where(RecommendationRecord.case_id == case_id)
            .order_by(
                RecommendationRecord.created_at.desc(),
                RecommendationRecord.id.desc(),
            )
            .limit(1)
        )
        return await self._session.scalar(statement)

    async def decision_for_recommendation(
        self,
        recommendation_id: UUID,
    ) -> Decision | None:
        statement = select(DecisionRecord).where(
            DecisionRecord.recommendation_id == recommendation_id
        )
        record = await self._session.scalar(statement)
        if record is None:
            return None
        return decision_from_record(record)

    async def decision_history(self) -> DecisionHistory:
        statement = (
            select(DecisionRecord, RecommendationRecord)
            .outerjoin(
                RecommendationRecord,
                DecisionRecord.recommendation_id == RecommendationRecord.id,
            )
            .order_by(
                DecisionRecord.recorded_at.desc(),
                DecisionRecord.id.desc(),
            )
        )
        rows = (await self._session.execute(statement)).all()

        return [
            DecisionAuditEntry(
                case_id=decision.case_id,
                recommendation_id=decision.recommendation_id,
                decision_type=DecisionType(decision.decision_type),
                outcome=Priority(decision.outcome),
                reason=decision.reason,
                reviewer=decision.reviewer,
                recorded_at=ensure_utc_isoformat(decision.recorded_at),
                advisory_priority=(
                    Priority(recommendation.recommendation) if recommendation is not None else None
                ),
                advisory_rationale=(
                    recommendation.rationale if recommendation is not None else None
                ),
                advisory_evidence=(
                    list(recommendation.evidence) if recommendation is not None else []
                ),
                model=(recommendation.model if recommendation is not None else None),
                recommendation_created_at=(
                    ensure_utc_isoformat(recommendation.created_at)
                    if recommendation is not None
                    else None
                ),
            )
            for decision, recommendation in rows
        ]

    async def latest_by_case_id(self) -> dict[str, LatestDecision]:
        statement = select(DecisionRecord).order_by(
            DecisionRecord.case_id,
            DecisionRecord.recorded_at.desc(),
        )
        records = (await self._session.scalars(statement)).all()
        latest: dict[str, LatestDecision] = {}

        for record in records:
            if record.case_id in latest:
                continue

            latest[record.case_id] = LatestDecision(
                outcome=Priority(record.outcome),
                reason=record.reason,
                reviewer=record.reviewer,
                recorded_at=ensure_utc_isoformat(record.recorded_at),
            )

        return latest

    async def add(
        self,
        request: DecisionRequest,
        *,
        reviewer: str,
        recommendation: Recommendation,
    ) -> Decision:
        decision_type = (
            DecisionType.accepted
            if request.outcome == recommendation.recommendation
            else DecisionType.overridden
        )
        record = DecisionRecord(
            case_id=request.case_id,
            recommendation_id=recommendation.id,
            decision_type=decision_type.value,
            outcome=request.outcome.value,
            reason=request.reason,
            reviewer=reviewer,
        )
        self._session.add(record)
        await self._session.commit()
        await self._session.refresh(record)

        return decision_from_record(record)
