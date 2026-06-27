import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, func, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[str] = mapped_column(
        String(36),
        default=lambda: str(uuid.uuid4()),
        primary_key=True,
    )
    subject: Mapped[str] = mapped_column(String(100))
    category: Mapped[str] = mapped_column(String(20))
    priority: Mapped[str] = mapped_column(String(10))
    # customer_email: Mapped[str] = mapped_column(String(255))
    # message: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String(20), default="new")
    cited_policy_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    draft_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(
        String(64), nullable=True, unique=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
