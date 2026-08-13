from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from statistics import mean, median

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import (
    LocalMarketBenchmark,
    MarketSnapshot,
    ObservedListing,
    ObservedMarketSnapshot,
)


@dataclass(frozen=True)
class LocalNowcast:
    area_code: str
    area_name: str
    property_type: str
    source_year: int
    official_huf_m2: float
    official_transactions: int | None
    relative_std_pct: float | None
    budapest_source_huf_m2: float
    budapest_latest_huf_m2: float
    trend_factor: float
    nowcast_huf_m2: float
    confidence: str
    latest_period: str


def _quantile(values: list[float], q: float) -> float:
    if not values:
        raise ValueError("quantile requires values")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    pos = (len(ordered) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(ordered) - 1)
    fraction = pos - lo
    return ordered[lo] * (1 - fraction) + ordered[hi] * fraction


def _area_keys(row: ObservedListing) -> list[str]:
    keys = ["HU"]
    if row.city and row.city.lower() == "budapest":
        keys.append("BUDAPEST")
        if row.district:
            keys.append(f"BUDAPEST-{row.district:02d}")
    elif row.area_code and row.area_code != "HU-UNKNOWN":
        keys.append(row.area_code)
    if row.postal_code:
        keys.append(f"POSTCODE-{row.postal_code}")
    return list(dict.fromkeys(keys))


def refresh_observed_market_aggregates(db: Session, *, provider_key: str = "duna_house") -> dict:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=settings.duna_house_fresh_days)
    rows = list(
        db.scalars(
            select(ObservedListing).where(
                ObservedListing.provider_key == provider_key,
                ObservedListing.active.is_(True),
                ObservedListing.last_seen_at >= cutoff,
            )
        )
    )
    grouped: dict[tuple[str, str, str], list[ObservedListing]] = defaultdict(list)
    excluded: dict[tuple[str, str, str], int] = defaultdict(int)
    for row in rows:
        for area_code in _area_keys(row):
            key = (area_code, row.market_class, row.market_segment)
            if row.quality_state == "usable":
                grouped[key].append(row)
            else:
                excluded[key] += 1

    written = 0
    skipped_small = 0
    for (area_code, market_class, market_segment), items in grouped.items():
        if len(items) < settings.duna_house_min_aggregate_sample:
            skipped_small += 1
            continue
        values = [item.price_huf_m2 for item in items]
        prices = [item.price_huf for item in items]
        days = [
            max((now - (item.first_seen_at if item.first_seen_at.tzinfo else item.first_seen_at.replace(tzinfo=timezone.utc))).total_seconds() / 86400, 0)
            for item in items
        ]
        new_7d = sum(
            1
            for item in items
            if now - (item.first_seen_at if item.first_seen_at.tzinfo else item.first_seen_at.replace(tzinfo=timezone.utc))
            <= timedelta(days=7)
        )
        cuts = sum(1 for item in items if item.price_huf < item.first_price_huf * 0.999)

        snapshot = db.scalar(
            select(ObservedMarketSnapshot).where(
                ObservedMarketSnapshot.provider_key == provider_key,
                ObservedMarketSnapshot.snapshot_date == date.today(),
                ObservedMarketSnapshot.area_code == area_code,
                ObservedMarketSnapshot.market_class == market_class,
                ObservedMarketSnapshot.market_segment == market_segment,
            )
        )
        values_dict = {
            "active_count": len(items),
            "excluded_count": excluded[(area_code, market_class, market_segment)],
            "median_huf_m2": median(values),
            "mean_huf_m2": mean(values),
            "p25_huf_m2": _quantile(values, 0.25),
            "p75_huf_m2": _quantile(values, 0.75),
            "median_price_huf": median(prices),
            "new_7d_count": new_7d,
            "price_cut_count": cuts,
            "price_cut_share": cuts / len(items),
            "median_observed_days": median(days),
            "collected_at": now,
        }
        if snapshot is None:
            snapshot = ObservedMarketSnapshot(
                provider_key=provider_key,
                snapshot_date=date.today(),
                area_code=area_code,
                market_class=market_class,
                market_segment=market_segment,
                **values_dict,
            )
            db.add(snapshot)
        else:
            for key, value in values_dict.items():
                setattr(snapshot, key, value)
        written += 1
    db.commit()
    return {
        "ok": True,
        "fresh_listings": len(rows),
        "aggregates": written,
        "small_groups_suppressed": skipped_small,
        "minimum_sample": settings.duna_house_min_aggregate_sample,
    }


def latest_observed_market(
    db: Session,
    *,
    area_code: str,
    market_class: str = "condominium",
    market_segment: str = "second_hand",
    provider_key: str = "duna_house",
) -> ObservedMarketSnapshot | None:
    return db.scalar(
        select(ObservedMarketSnapshot)
        .where(
            ObservedMarketSnapshot.provider_key == provider_key,
            ObservedMarketSnapshot.area_code == area_code,
            ObservedMarketSnapshot.market_class == market_class,
            ObservedMarketSnapshot.market_segment == market_segment,
        )
        .order_by(ObservedMarketSnapshot.snapshot_date.desc())
        .limit(1)
    )


def observed_market_history(
    db: Session,
    *,
    area_code: str,
    market_class: str = "condominium",
    market_segment: str = "second_hand",
    provider_key: str = "duna_house",
    days: int = 90,
) -> list[ObservedMarketSnapshot]:
    cutoff = date.today() - timedelta(days=days)
    return list(
        db.scalars(
            select(ObservedMarketSnapshot)
            .where(
                ObservedMarketSnapshot.provider_key == provider_key,
                ObservedMarketSnapshot.area_code == area_code,
                ObservedMarketSnapshot.market_class == market_class,
                ObservedMarketSnapshot.market_segment == market_segment,
                ObservedMarketSnapshot.snapshot_date >= cutoff,
            )
            .order_by(ObservedMarketSnapshot.snapshot_date.asc())
        )
    )


def _budapest_annual_quarterly_mean(db: Session, year: int) -> float | None:
    rows = list(
        db.scalars(
            select(MarketSnapshot).where(
                MarketSnapshot.area_code == "BUDAPEST",
                MarketSnapshot.property_market == "second_hand",
                MarketSnapshot.period.like(f"{year}-Q%"),
                MarketSnapshot.status == "verified",
            )
        )
    )
    if not rows:
        return None
    weighted = [row for row in rows if row.sample_size and row.sample_size > 0]
    if weighted:
        total_count = sum(row.sample_size or 0 for row in weighted)
        return sum(row.price_huf_m2 * (row.sample_size or 0) for row in weighted) / total_count
    return mean(row.price_huf_m2 for row in rows)


def local_nowcast(
    db: Session,
    *,
    area_code: str,
    property_type: str = "condominium",
    year: int | None = None,
) -> LocalNowcast | None:
    settings = get_settings()
    year = year or settings.ksh_local_year
    local = db.scalar(
        select(LocalMarketBenchmark).where(
            LocalMarketBenchmark.area_code == area_code,
            LocalMarketBenchmark.year == year,
            LocalMarketBenchmark.property_type == property_type,
        )
    )
    if local is None:
        return None
    source_budapest = _budapest_annual_quarterly_mean(db, year)
    latest = db.scalar(
        select(MarketSnapshot)
        .where(
            MarketSnapshot.area_code == "BUDAPEST",
            MarketSnapshot.property_market == "second_hand",
            MarketSnapshot.status == "verified",
        )
        .order_by(MarketSnapshot.observation_date.desc())
        .limit(1)
    )
    if source_budapest is None or latest is None or source_budapest <= 0:
        return None
    factor = latest.price_huf_m2 / source_budapest
    count = local.transactions or 0
    spread = local.relative_std_pct or 100
    if count >= 100 and spread <= 35:
        confidence = "high"
    elif count >= 30 and spread <= 50:
        confidence = "medium"
    else:
        confidence = "low"
    return LocalNowcast(
        area_code=local.area_code,
        area_name=local.area_name,
        property_type=property_type,
        source_year=year,
        official_huf_m2=local.price_huf_m2,
        official_transactions=local.transactions,
        relative_std_pct=local.relative_std_pct,
        budapest_source_huf_m2=source_budapest,
        budapest_latest_huf_m2=latest.price_huf_m2,
        trend_factor=factor,
        nowcast_huf_m2=local.price_huf_m2 * factor,
        confidence=confidence,
        latest_period=latest.period,
    )
