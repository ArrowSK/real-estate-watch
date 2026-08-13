from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MarketSnapshot(Base):
    __tablename__ = "market_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "source_key", "area_code", "property_market", "period", "metric",
            name="uq_market_series_period",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    country_code: Mapped[str] = mapped_column(String(2), default="HU", index=True)
    area_code: Mapped[str] = mapped_column(String(64), index=True)
    area_name_en: Mapped[str] = mapped_column(String(120))
    area_name_hu: Mapped[str] = mapped_column(String(120))
    property_market: Mapped[str] = mapped_column(String(32), index=True)
    period: Mapped[str] = mapped_column(String(16), index=True)
    observation_date: Mapped[date] = mapped_column(Date)
    metric: Mapped[str] = mapped_column(String(24), default="mean")
    price_huf_m2: Mapped[float] = mapped_column(Float)
    sample_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_key: Mapped[str] = mapped_column(String(64), index=True)
    source_url: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default="verified", index=True)
    note_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    note_hu: Mapped[str | None] = mapped_column(Text, nullable=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class FxSnapshot(Base):
    __tablename__ = "fx_snapshots"
    __table_args__ = (UniqueConstraint("rate_date", "currency", name="uq_fx_date_currency"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    rate_date: Mapped[date] = mapped_column(Date, index=True)
    currency: Mapped[str] = mapped_column(String(3), index=True)
    huf_per_unit: Mapped[float] = mapped_column(Float)
    source_key: Mapped[str] = mapped_column(String(64), default="mnb_fx")
    status: Mapped[str] = mapped_column(String(24), default="verified")
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SourceHealth(Base):
    __tablename__ = "source_health"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    state: Mapped[str] = mapped_column(String(24), default="unknown")
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    last_value_summary: Mapped[str | None] = mapped_column(Text, nullable=True)


class JobRun(Base):
    __tablename__ = "job_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_name: Mapped[str] = mapped_column(String(64), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    state: Mapped[str] = mapped_column(String(24), default="running")
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)


class NotificationEvent(Base):
    __tablename__ = "notification_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    channel: Mapped[str] = mapped_column(String(32))
    subject_key: Mapped[str] = mapped_column(String(120), index=True)
    payload: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(String(24), default="pending")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
