from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from statistics import median

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AskingMarketSnapshot,
    ListingSnapshot,
    LocalBenchmark,
    ObservedListing,
    ObservedListingAttribute,
)
from app.services.analytics import market_comparison
from app.services.duna_house import (
    DH_SOURCE_KEY,
    asking_market_series,
    latest_asking_market,
)
from app.services.ksh_local import KSH_LOCAL_SOURCE_KEY, latest_local_benchmark
from app.services.market import latest_market


@dataclass(frozen=True)
class LiveSignals:
    latest: AskingMarketSnapshot | None
    sample_size: int
    price_cut_count: int
    price_cut_share: float | None
    median_price_cut_pct: float | None
    new_today_count: int
    new_7d_count: int
    median_observed_days: float | None
    attribute_listing_coverage_pct: float | None
    attribute_field_coverage_pct: float | None
    postcodes: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class LocalStreetSignal:
    street_name: str
    year: int
    property_type: str
    mean_huf_m2: float
    transaction_count: int | None
    relative_std_pct: float | None
    local_factor: float | None
    current_huf_m2: float | None
    confidence: str


@dataclass(frozen=True)
class LocalDistrictSignal:
    area_code: str
    area_name: str
    year: int
    property_type: str
    mean_huf_m2: float
    transaction_count: int | None
    relative_std_pct: float | None
    city_reference_huf_m2: float | None
    latest_budapest_huf_m2: float | None
    local_factor: float | None
    current_huf_m2: float | None
    confidence: str


def postcode_area_code(postcode: str) -> str:
    return f"POSTCODE_{postcode}"


def postcode_to_district_area(postcode: str) -> str | None:
    if len(postcode) == 4 and postcode.startswith("1") and postcode.isdigit():
        district = int(postcode[1:3])
        if 1 <= district <= 23:
            return f"BUDAPEST_{district:02d}"
    return None


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _listing_matches_area(row: ObservedListing, area_code: str) -> bool:
    if area_code == "HU":
        return True
    if area_code == "BUDAPEST":
        return row.area_code == "BUDAPEST" or row.area_code.startswith("BUDAPEST_")
    if area_code.startswith("POSTCODE_"):
        return row.postcode == area_code.removeprefix("POSTCODE_")
    return row.area_code == area_code


def _confidence(transaction_count: int | None, relative_std_pct: float | None) -> str:
    count = transaction_count or 0
    spread = relative_std_pct if relative_std_pct is not None else 100.0
    if count >= 100 and spread <= 35:
        return "high"
    if count >= 30 and spread <= 50:
        return "medium"
    return "low"


def _listing_snapshot_edges(
    db: Session,
    listing_ids: list[int],
) -> tuple[dict[int, ListingSnapshot], dict[int, ListingSnapshot]]:
    if not listing_ids:
        return {}, {}
    rows = list(
        db.scalars(
            select(ListingSnapshot)
            .where(ListingSnapshot.listing_id.in_(listing_ids))
            .order_by(ListingSnapshot.listing_id, ListingSnapshot.snapshot_date)
        )
    )
    first: dict[int, ListingSnapshot] = {}
    latest: dict[int, ListingSnapshot] = {}
    for row in rows:
        first.setdefault(row.listing_id, row)
        latest[row.listing_id] = row
    return first, latest


def live_signals(
    db: Session,
    *,
    area_code: str,
    property_type: str = "all",
    market_segment: str = "second_hand",
) -> LiveSignals:
    now = datetime.now(timezone.utc)
    rows = list(
        db.scalars(
            select(ObservedListing).where(
                ObservedListing.source_key == DH_SOURCE_KEY,
                ObservedListing.active.is_(True),
                ObservedListing.quality_state == "usable",
                ObservedListing.market_segment == market_segment,
            )
        )
    )
    if property_type != "all":
        rows = [row for row in rows if row.property_type == property_type]
    rows = [row for row in rows if _listing_matches_area(row, area_code)]

    listing_ids = [row.id for row in rows]
    first_snapshots, latest_snapshots = _listing_snapshot_edges(db, listing_ids)
    usable_rows = [row for row in rows if row.id in latest_snapshots]

    cuts: list[float] = []
    for row in usable_rows:
        first = first_snapshots[row.id]
        latest = latest_snapshots[row.id]
        if latest.asking_price_huf < first.asking_price_huf * 0.999:
            cuts.append((latest.asking_price_huf / first.asking_price_huf - 1) * 100)

    observed_days = [
        max((now - _aware(row.first_seen_at)).total_seconds() / 86400, 0)
        for row in usable_rows
    ]
    new_today = sum(1 for row in usable_rows if _aware(row.first_seen_at).date() == now.date())
    new_7d = sum(
        1 for row in usable_rows if now - _aware(row.first_seen_at) <= timedelta(days=7)
    )

    postcode_counts: dict[str, int] = {}
    for row in usable_rows:
        if row.postcode:
            postcode_counts[row.postcode] = postcode_counts.get(row.postcode, 0) + 1

    attributes = (
        list(
            db.scalars(
                select(ObservedListingAttribute).where(
                    ObservedListingAttribute.listing_id.in_(listing_ids)
                )
            )
        )
        if listing_ids
        else []
    )
    attribute_by_listing = {row.listing_id: row for row in attributes}
    feature_fields = (
        "building_type",
        "condition",
        "construction_year",
        "floor",
        "lift",
        "balcony",
        "view",
        "orientation",
        "heating",
        "energy_rating",
    )
    listings_with_attributes = 0
    populated_fields = 0
    for listing in usable_rows:
        attrs = attribute_by_listing.get(listing.id)
        if attrs is None:
            continue
        values = [getattr(attrs, field) for field in feature_fields]
        count = sum(value not in (None, "") for value in values)
        populated_fields += count
        listings_with_attributes += int(count > 0)

    sample_size = len(usable_rows)
    listing_coverage = listings_with_attributes / sample_size * 100 if sample_size else None
    field_coverage = (
        populated_fields / (sample_size * len(feature_fields)) * 100 if sample_size else None
    )

    latest = latest_asking_market(db, area_code, property_type, market_segment)
    if latest is None and property_type != "all":
        latest = latest_asking_market(db, area_code, "all", market_segment)

    return LiveSignals(
        latest=latest,
        sample_size=sample_size,
        price_cut_count=len(cuts),
        price_cut_share=(len(cuts) / sample_size if sample_size else None),
        median_price_cut_pct=(median(cuts) if cuts else None),
        new_today_count=new_today,
        new_7d_count=new_7d,
        median_observed_days=(median(observed_days) if observed_days else None),
        attribute_listing_coverage_pct=listing_coverage,
        attribute_field_coverage_pct=field_coverage,
        postcodes=tuple(sorted(postcode_counts.items(), key=lambda item: (-item[1], item[0]))),
    )


def live_history(
    db: Session,
    *,
    area_code: str,
    property_type: str,
    market_segment: str,
    days: int = 180,
) -> list[dict[str, object]]:
    rows = asking_market_series(db, area_code, property_type, market_segment)
    if property_type != "all" and not rows:
        rows = asking_market_series(db, area_code, "all", market_segment)
    cutoff = date.today() - timedelta(days=max(days, 1))
    rows = [row for row in rows if row.snapshot_date >= cutoff]
    return [
        {
            "date": row.snapshot_date.isoformat(),
            "period": row.snapshot_date.isoformat(),
            "price": row.median_huf_m2,
        }
        for row in rows
    ]


def live_official_comparison_area(area_code: str) -> str:
    if area_code.startswith("POSTCODE_"):
        postcode = area_code.removeprefix("POSTCODE_")
        return postcode_to_district_area(postcode) or "BUDAPEST"
    return area_code


def live_comparison(
    db: Session,
    *,
    area_code: str,
    property_type: str,
    market_segment: str,
):
    return market_comparison(
        db,
        live_official_comparison_area(area_code),
        market_segment,
        property_type,
    )


def local_years(db: Session, area_code: str) -> list[int]:
    values = db.scalars(
        select(LocalBenchmark.year)
        .where(
            LocalBenchmark.source_key == KSH_LOCAL_SOURCE_KEY,
            LocalBenchmark.area_code == area_code,
            LocalBenchmark.status == "verified",
        )
        .distinct()
        .order_by(LocalBenchmark.year.desc())
    )
    return list(values)


def _current_local_value(
    db: Session,
    *,
    mean_huf_m2: float,
    year: int,
) -> tuple[float | None, float | None, float | None]:
    city = latest_local_benchmark(db, "BUDAPEST", "all", year=year)
    latest = latest_market(db, "BUDAPEST", "second_hand")
    if city is None or latest is None or city.mean_huf_m2 <= 0:
        return None, None, None
    factor = mean_huf_m2 / city.mean_huf_m2
    return city.mean_huf_m2, factor, latest.price_huf_m2 * factor


def local_district_signal(
    db: Session,
    *,
    area_code: str,
    property_type: str,
    year: int,
) -> LocalDistrictSignal | None:
    row = db.scalar(
        select(LocalBenchmark).where(
            LocalBenchmark.source_key == KSH_LOCAL_SOURCE_KEY,
            LocalBenchmark.area_code == area_code,
            LocalBenchmark.property_type == property_type,
            LocalBenchmark.year == year,
            LocalBenchmark.street_key == "",
            LocalBenchmark.status == "verified",
        )
    )
    if row is None:
        return None
    city_reference, factor, current = _current_local_value(
        db,
        mean_huf_m2=row.mean_huf_m2,
        year=year,
    )
    latest = latest_market(db, "BUDAPEST", "second_hand")
    return LocalDistrictSignal(
        area_code=row.area_code,
        area_name=row.area_name,
        year=row.year,
        property_type=row.property_type,
        mean_huf_m2=row.mean_huf_m2,
        transaction_count=row.transaction_count,
        relative_std_pct=row.relative_std_pct,
        city_reference_huf_m2=city_reference,
        latest_budapest_huf_m2=(latest.price_huf_m2 if latest else None),
        local_factor=factor,
        current_huf_m2=current,
        confidence=_confidence(row.transaction_count, row.relative_std_pct),
    )


def local_street_signals(
    db: Session,
    *,
    area_code: str,
    property_type: str,
    year: int,
    search: str = "",
    limit: int = 160,
) -> list[LocalStreetSignal]:
    rows = list(
        db.scalars(
            select(LocalBenchmark).where(
                LocalBenchmark.source_key == KSH_LOCAL_SOURCE_KEY,
                LocalBenchmark.area_code == area_code,
                LocalBenchmark.property_type == property_type,
                LocalBenchmark.year == year,
                LocalBenchmark.street_key != "",
                LocalBenchmark.status == "verified",
            )
        )
    )
    needle = search.casefold().strip()
    if needle:
        rows = [row for row in rows if needle in (row.street_name or "").casefold()]
    rows.sort(
        key=lambda row: (
            -(row.transaction_count or 0),
            (row.street_name or "").casefold(),
        )
    )

    output: list[LocalStreetSignal] = []
    for row in rows[:limit]:
        _, factor, current = _current_local_value(
            db,
            mean_huf_m2=row.mean_huf_m2,
            year=year,
        )
        output.append(
            LocalStreetSignal(
                street_name=row.street_name or "—",
                year=row.year,
                property_type=row.property_type,
                mean_huf_m2=row.mean_huf_m2,
                transaction_count=row.transaction_count,
                relative_std_pct=row.relative_std_pct,
                local_factor=factor,
                current_huf_m2=current,
                confidence=_confidence(row.transaction_count, row.relative_std_pct),
            )
        )
    return output
