from datetime import date, datetime, timezone

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
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


class LocalMarketBenchmark(Base):
    """Published KSH annual local benchmark.

    These are aggregate statistics, not individual transactions. `area_code` is stable inside
    Real Estate Watch even when KSH's own `ter` query identifier changes.
    """

    __tablename__ = "local_market_benchmarks"
    __table_args__ = (
        UniqueConstraint(
            "source_key", "year", "area_code", "property_type",
            name="uq_local_market_year_area_type",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    country_code: Mapped[str] = mapped_column(String(2), default="HU", index=True)
    parent_area_code: Mapped[str | None] = mapped_column(String(96), nullable=True, index=True)
    area_code: Mapped[str] = mapped_column(String(180), index=True)
    level: Mapped[str] = mapped_column(String(24), index=True)
    area_name: Mapped[str] = mapped_column(String(180), index=True)
    year: Mapped[int] = mapped_column(Integer, index=True)
    property_type: Mapped[str] = mapped_column(String(32), index=True)
    price_huf_m2: Mapped[float] = mapped_column(Float)
    transactions: Mapped[int | None] = mapped_column(Integer, nullable=True)
    relative_std_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_key: Mapped[str] = mapped_column(String(64), default="ksh_local_market", index=True)
    source_url: Mapped[str] = mapped_column(Text)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ObservedListing(Base):
    """Minimal factual state retained from a permitted observed listing source.

    Descriptions, photographs and agent/contact information are intentionally absent.
    """

    __tablename__ = "observed_listings"
    __table_args__ = (
        UniqueConstraint("provider_key", "external_id", name="uq_listing_provider_external"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider_key: Mapped[str] = mapped_column(String(64), index=True)
    external_id: Mapped[str] = mapped_column(String(120), index=True)
    source_url: Mapped[str] = mapped_column(Text)
    country_code: Mapped[str] = mapped_column(String(2), default="HU", index=True)
    area_code: Mapped[str] = mapped_column(String(96), index=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    district: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    postal_code: Mapped[str | None] = mapped_column(String(12), nullable=True, index=True)
    property_type: Mapped[str] = mapped_column(String(24), index=True)
    market_class: Mapped[str] = mapped_column(String(32), index=True)
    market_segment: Mapped[str] = mapped_column(String(24), index=True)
    status_label: Mapped[str | None] = mapped_column(String(80), nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    inactive_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    sitemap_miss_count: Mapped[int] = mapped_column(Integer, default=0)
    sitemap_lastmod: Mapped[str | None] = mapped_column(String(40), nullable=True)
    first_price_huf: Mapped[float] = mapped_column(Float)
    price_huf: Mapped[float] = mapped_column(Float)
    area_m2: Mapped[float] = mapped_column(Float)
    rooms: Mapped[float | None] = mapped_column(Float, nullable=True)
    price_huf_m2: Mapped[float] = mapped_column(Float, index=True)
    building_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    condition: Mapped[str | None] = mapped_column(String(120), nullable=True)
    construction_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    floor: Mapped[str | None] = mapped_column(String(80), nullable=True)
    lift: Mapped[str | None] = mapped_column(String(80), nullable=True)
    balcony: Mapped[str | None] = mapped_column(String(80), nullable=True)
    view: Mapped[str | None] = mapped_column(String(80), nullable=True)
    orientation: Mapped[str | None] = mapped_column(String(80), nullable=True)
    heating: Mapped[str | None] = mapped_column(String(180), nullable=True)
    energy_rating: Mapped[str | None] = mapped_column(String(80), nullable=True)
    quality_state: Mapped[str] = mapped_column(String(24), default="usable", index=True)
    quality_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_signature: Mapped[str] = mapped_column(String(64))


class ListingSnapshot(Base):
    __tablename__ = "listing_snapshots"
    __table_args__ = (
        UniqueConstraint("listing_id", "observation_date", name="uq_listing_daily_snapshot"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    listing_id: Mapped[int] = mapped_column(
        ForeignKey("observed_listings.id", ondelete="CASCADE"), index=True
    )
    observation_date: Mapped[date] = mapped_column(Date, index=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    price_huf: Mapped[float] = mapped_column(Float)
    area_m2: Mapped[float] = mapped_column(Float)
    rooms: Mapped[float | None] = mapped_column(Float, nullable=True)
    price_huf_m2: Mapped[float] = mapped_column(Float)
    status_label: Mapped[str | None] = mapped_column(String(80), nullable=True)
    content_signature: Mapped[str] = mapped_column(String(64))


class ObservedMarketSnapshot(Base):
    __tablename__ = "observed_market_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "provider_key",
            "snapshot_date",
            "area_code",
            "market_class",
            "market_segment",
            name="uq_observed_market_daily_group",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider_key: Mapped[str] = mapped_column(String(64), index=True)
    snapshot_date: Mapped[date] = mapped_column(Date, index=True)
    area_code: Mapped[str] = mapped_column(String(96), index=True)
    market_class: Mapped[str] = mapped_column(String(32), index=True)
    market_segment: Mapped[str] = mapped_column(String(24), index=True)
    active_count: Mapped[int] = mapped_column(Integer)
    excluded_count: Mapped[int] = mapped_column(Integer, default=0)
    median_huf_m2: Mapped[float] = mapped_column(Float)
    mean_huf_m2: Mapped[float] = mapped_column(Float)
    p25_huf_m2: Mapped[float] = mapped_column(Float)
    p75_huf_m2: Mapped[float] = mapped_column(Float)
    median_price_huf: Mapped[float] = mapped_column(Float)
    new_7d_count: Mapped[int] = mapped_column(Integer, default=0)
    price_cut_count: Mapped[int] = mapped_column(Integer, default=0)
    price_cut_share: Mapped[float] = mapped_column(Float, default=0.0)
    median_observed_days: Mapped[float] = mapped_column(Float, default=0.0)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ProviderPolicyState(Base):
    __tablename__ = "provider_policy_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    state: Mapped[str] = mapped_column(String(32), default="unknown", index=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    robots_signature: Mapped[str | None] = mapped_column(String(64), nullable=True)
    legal_signature: Mapped[str | None] = mapped_column(String(64), nullable=True)
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
