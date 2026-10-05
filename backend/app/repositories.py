from datetime import UTC

from sqlalchemy.ext.asyncio import AsyncSession

from .models import DecisionRecord
from .schemas import Decision, DecisionRequest, Priority


class DecisionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, request: DecisionRequest) -> Decision:
        record = DecisionRecord(
            case_id=request.case_id,
            outcome=request.outcome.value,
            reason=request.reason,
            reviewer=request.reviewer,
        )
        self._session.add(record)
        await self._session.commit()
        await self._session.refresh(record)

        recorded_at = record.recorded_at
        if recorded_at.tzinfo is None:
            recorded_at = recorded_at.replace(tzinfo=UTC)

        return Decision(
            case_id=record.case_id,
            outcome=Priority(record.outcome),
            reason=record.reason,
            reviewer=record.reviewer,
            recorded_at=recorded_at.isoformat(),
        )
