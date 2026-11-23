from datetime import datetime

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core import clock
from app.core.db import PK, Base, UTCDateTime


class CompanyKnowledge(Base):
    """Company-scoped knowledge and entity definitions (e.g., custom products like 'Elala', internal systems, client projects)
    learned by the AI to recommend accurate descriptions and special notes."""

    __tablename__ = "company_knowledge"
    __table_args__ = (
        UniqueConstraint("company_id", "entity_key", name="uq_company_entity"),
    )

    id: Mapped[int] = mapped_column(PK, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    entity_key: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_name: Mapped[str] = mapped_column(String(150), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(50), default="product", nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    tech_stack: Mapped[str | None] = mapped_column(String(255), nullable=True)
    default_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=clock.utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=clock.utcnow, onupdate=clock.utcnow)
