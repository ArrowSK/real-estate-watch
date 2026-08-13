from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
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


class LocalBenchmark(Base):
    """Annual, geographically granular completed-transaction benchmark.

    This table is intentionally separate from the quarterly market series because KSH
    Ingatlanadattár has a different frequency, geography and property-type breakdown.
    """

    __tablename__ = "local_benchmarks"
    __table_args__ = (
        UniqueConstraint(
            "source_key", "year", "area_code", "street_key", "property_type",
            name="uq_local_benchmark",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_key: Mapped[str] = mapped_column(String(64), default="ksh_ingatlanadattar", index=True)
    country_code: Mapped[str] = mapped_column(String(2), default="HU", index=True)
    year: Mapped[int] = mapped_column(Integer, index=True)
    area_code: Mapped[str] = mapped_column(String(64), index=True)
    area_name: Mapped[str] = mapped_column(String(160))
    street_name: Mapped[str | None] = mapped_column(String(180), nullable=True)
    street_key: Mapped[str] = mapped_column(String(180), default="", index=True)
    property_type: Mapped[str] = mapped_column(String(32), default="all", index=True)
    mean_huf_m2: Mapped[float] = mapped_column(Float)
    transaction_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    relative_std_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_url: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default="verified", index=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ObservedListing(Base):
    """Minimal factual listing identity; no description, photos or contact data are stored."""

    __tablename__ = "observed_listings"
    __table_args__ = (
        UniqueConstraint("source_key", "external_id", name="uq_observed_listing_source_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_key: Mapped[str] = mapped_column(String(64), index=True)
    external_id: Mapped[str] = mapped_column(String(80), index=True)
    listing_url: Mapped[str] = mapped_column(Text)
    country_code: Mapped[str] = mapped_column(String(2), default="HU", index=True)
    area_code: Mapped[str] = mapped_column(String(64), index=True)
    locality: Mapped[str | None] = mapped_column(String(160), nullable=True)
    postcode: Mapped[str | None] = mapped_column(String(12), nullable=True)
    property_type: Mapped[str] = mapped_column(String(32), default="unknown", index=True)
    market_segment: Mapped[str] = mapped_column(String(32), default="second_hand", index=True)
    rooms: Mapped[float | None] = mapped_column(Float, nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    source_lastmod_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    quality_state: Mapped[str] = mapped_column(String(24), default="usable", index=True)


class ListingSnapshot(Base):
    __tablename__ = "listing_snapshots"
    __table_args__ = (
        UniqueConstraint("listing_id", "snapshot_date", name="uq_listing_snapshot_day"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("observed_listings.id"), index=True)
    snapshot_date: Mapped[date] = mapped_column(Date, index=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    asking_price_huf: Mapped[float] = mapped_column(Float)
    floor_area_m2: Mapped[float] = mapped_column(Float)
    price_huf_m2: Mapped[float] = mapped_column(Float)
    rooms: Mapped[float | None] = mapped_column(Float, nullable=True)


class AskingMarketSnapshot(Base):
    __tablename__ = "asking_market_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "source_key", "snapshot_date", "area_code", "property_type", "market_segment",
            name="uq_asking_market_daily",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_key: Mapped[str] = mapped_column(String(64), index=True)
    snapshot_date: Mapped[date] = mapped_column(Date, index=True)
    country_code: Mapped[str] = mapped_column(String(2), default="HU", index=True)
    area_code: Mapped[str] = mapped_column(String(64), index=True)
    property_type: Mapped[str] = mapped_column(String(32), default="all", index=True)
    market_segment: Mapped[str] = mapped_column(String(32), default="second_hand", index=True)
    sample_size: Mapped[int] = mapped_column(Integer)
    median_huf_m2: Mapped[float] = mapped_column(Float)
    mean_huf_m2: Mapped[float] = mapped_column(Float)
    p25_huf_m2: Mapped[float] = mapped_column(Float)
    p75_huf_m2: Mapped[float] = mapped_column(Float)
    new_listing_count: Mapped[int] = mapped_column(Integer, default=0)
    price_cut_count: Mapped[int] = mapped_column(Integer, default=0)
    median_price_cut_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    observed_active_count: Mapped[int] = mapped_column(Integer, default=0)
    discovery_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    coverage_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence: Mapped[str] = mapped_column(String(24), default="low")
    status: Mapped[str] = mapped_column(String(24), default="observed_subset")
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ProviderPolicyState(Base):
    __tablename__ = "provider_policy_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(32), default="review_required", index=True)
    reviewed_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    robots_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    legal_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)


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
