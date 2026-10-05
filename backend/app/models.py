from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class DecisionRecord(Base):
    __tablename__ = "decisions"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    case_id: Mapped[str] = mapped_column(String(64), index=True)
    outcome: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str] = mapped_column(Text)
    reviewer: Mapped[str] = mapped_column(String(100))
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
