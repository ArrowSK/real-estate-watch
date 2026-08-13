from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from app.models import AskingMarketSnapshot, LocalBenchmark, MarketSnapshot
from app.services.duna_house import asking_market_series, latest_asking_market
from app.services.ksh_local import latest_local_benchmark
from app.services.market import latest_market, market_series

LOCAL_PROPERTY_MAP = {
    "all": "all",
    "apartment": "condominium",
    "house": "house",
    "panel": "panel",
}
ASKING_PROPERTY_MAP = {
    "all": "all",
    "apartment": "apartment",
    "house": "house",
    # The current factual Duna House parser cannot safely distinguish panel construction from
    # other apartments. Panel keeps its KSH local benchmark but uses the broader apartment
    # asking subset when one exists, and the UI labels that scope explicitly.
    "panel": "apartment",
}


@dataclass(frozen=True)
class TransactionNowcast:
    value_huf_m2: float
    local_base_huf_m2: float
    local_year: int | None
    trend_factor: float
    geography: str
    property_type: str
    street_name: str | None
    sample_size: int | None
    relative_std_pct: float | None
    source_url: str
    method: str


@dataclass(frozen=True)
class MarketComparison:
    official: TransactionNowcast | None
    asking: AskingMarketSnapshot | None
    asking_scope: str
    asking_gap_pct: float | None
    official_6m_change_pct: float | None
    asking_30d_change_pct: float | None


def _change(current: float | None, previous: float | None) -> float | None:
    if current is None or previous is None or previous == 0:
        return None
    return (current / previous - 1) * 100


def _quarter_row_at_or_before(rows: list[MarketSnapshot], cutoff: date) -> MarketSnapshot | None:
    candidates = [row for row in rows if row.observation_date <= cutoff]
    return candidates[-1] if candidates else None


def transaction_nowcast(
    db: Session,
    area_code: str,
    market_segment: str,
    property_type: str = "all",
    street: str | None = None,
) -> TransactionNowcast | None:
    """Build a transparent transaction-value nowcast from official KSH observations.

    Budapest district/street values use the latest annual Ingatlanadattár benchmark, then move
    it forward by the change in the Budapest quarterly transaction series since the last
    quarter of that local benchmark year. No asking price is folded into this value.
    """
    local_type = LOCAL_PROPERTY_MAP.get(property_type, "all")
    local: LocalBenchmark | None = None
    if area_code.startswith("BUDAPEST_"):
        local = latest_local_benchmark(db, area_code, local_type, street=street)
        if local is None and local_type != "all":
            local = latest_local_benchmark(db, area_code, "all", street=street)
        if local is None and street:
            local = latest_local_benchmark(db, area_code, local_type, street=None)
        if local is None and local_type != "all":
            local = latest_local_benchmark(db, area_code, "all", street=None)

    if local is not None:
        city_rows = market_series(db, "BUDAPEST", market_segment)
        latest_city = city_rows[-1] if city_rows else None
        base_city = _quarter_row_at_or_before(city_rows, date(local.year, 12, 31))
        factor = (
            latest_city.price_huf_m2 / base_city.price_huf_m2
            if latest_city and base_city and base_city.price_huf_m2
            else 1.0
        )
        return TransactionNowcast(
            value_huf_m2=local.mean_huf_m2 * factor,
            local_base_huf_m2=local.mean_huf_m2,
            local_year=local.year,
            trend_factor=factor,
            geography=local.area_name,
            property_type=local.property_type,
            street_name=local.street_name,
            sample_size=local.transaction_count,
            relative_std_pct=local.relative_std_pct,
            source_url=local.source_url,
            method="annual local KSH benchmark × subsequent Budapest quarterly transaction movement",
        )

    direct = latest_market(db, area_code, market_segment)
    if direct is None and area_code.startswith("BUDAPEST_"):
        direct = latest_market(db, "BUDAPEST", market_segment)
    if direct is None:
        return None
    return TransactionNowcast(
        value_huf_m2=direct.price_huf_m2,
        local_base_huf_m2=direct.price_huf_m2,
        local_year=None,
        trend_factor=1.0,
        geography=direct.area_name_en,
        property_type="all",
        street_name=None,
        sample_size=direct.sample_size,
        relative_std_pct=None,
        source_url=direct.source_url,
        method="latest KSH quarterly completed-transaction mean",
    )


def _official_6m_change(db: Session, area_code: str, market_segment: str) -> float | None:
    source_area = "BUDAPEST" if area_code.startswith("BUDAPEST_") else area_code
    rows = market_series(db, source_area, market_segment)
    if len(rows) < 3:
        return None
    return _change(rows[-1].price_huf_m2, rows[-3].price_huf_m2)


def _asking_30d_change(
    db: Session,
    area_code: str,
    property_type: str,
    market_segment: str,
) -> float | None:
    rows = asking_market_series(db, area_code, property_type, market_segment)
    if len(rows) < 2:
        return None
    latest = rows[-1]
    target = latest.snapshot_date.toordinal() - 30
    older = min(rows[:-1], key=lambda row: abs(row.snapshot_date.toordinal() - target))
    if latest.snapshot_date.toordinal() - older.snapshot_date.toordinal() < 7:
        return None
    return _change(latest.median_huf_m2, older.median_huf_m2)


def market_comparison(
    db: Session,
    area_code: str,
    market_segment: str,
    property_type: str = "all",
    street: str | None = None,
) -> MarketComparison:
    official = transaction_nowcast(db, area_code, market_segment, property_type, street)
    asking_type = ASKING_PROPERTY_MAP.get(property_type, "all")
    asking = latest_asking_market(db, area_code, asking_type, market_segment)
    asking_scope = asking_type
    if asking is None and asking_type != "all":
        asking = latest_asking_market(db, area_code, "all", market_segment)
        asking_scope = "all"
    gap = (
        _change(asking.median_huf_m2, official.value_huf_m2)
        if asking is not None and official is not None
        else None
    )
    return MarketComparison(
        official=official,
        asking=asking,
        asking_scope=asking_scope,
        asking_gap_pct=gap,
        official_6m_change_pct=_official_6m_change(db, area_code, market_segment),
        asking_30d_change_pct=(
            _asking_30d_change(db, area_code, asking_scope, market_segment)
            if asking is not None
            else None
        ),
    )
