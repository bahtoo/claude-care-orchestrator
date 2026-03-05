"""
SQLAlchemy ORM models for persistent storage.

Tables:
  - pa_records:    stores every completed Prior Authorization result
  - payer_configs: multi-tenant payer policy configurations
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from care_orchestrator.database import Base


class PARecord(Base):
    """Persistent record of a completed Prior Authorization workflow."""

    __tablename__ = "pa_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    pa_number: Mapped[str] = mapped_column(String(30), unique=True, index=True, nullable=False)
    patient_id: Mapped[str] = mapped_column(String(60), index=True, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    cpt_codes: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    icd10_codes: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    turnaround_minutes: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(tz=UTC)
    )
    result_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # Human-readable summary for quick dashboard queries
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")

    def __repr__(self) -> str:
        return f"<PARecord pa_number={self.pa_number!r} status={self.status!r}>"


class PayerConfig(Base):
    """
    Multi-tenant payer policy configuration.

    Replaces / augments static JSON files in config/policies/.
    Each row holds the full policy rules for one payer, identified by payer_id.
    The `rules_json` field mirrors the existing JSON policy file schema so
    PolicyEngine can read from DB or file without changing its interface.
    """

    __tablename__ = "payer_configs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    payer_id: Mapped[str] = mapped_column(String(60), unique=True, index=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    rules_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(tz=UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(tz=UTC),
        onupdate=lambda: datetime.now(tz=UTC),
    )

    def __repr__(self) -> str:
        return f"<PayerConfig payer_id={self.payer_id!r} active={self.active!r}>"
