from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import AskingMarketSnapshot, LocalBenchmark, MarketSnapshot
from app.services.analytics import market_comparison, transaction_nowcast


def _market(area: str, market: str, period: str, value: float) -> MarketSnapshot:
    year = int(period[:4])
    quarter = int(period[-1])
    return MarketSnapshot(
        country_code="HU",
        area_code=area,
        area_name_en="Budapest",
        area_name_hu="Budapest",
        property_market=market,
        period=period,
        observation_date=date(year, quarter * 3, (31, 30, 30, 31)[quarter - 1]),
        price_huf_m2=value,
        source_key="ksh_housing_prices",
        source_url="https://ksh.example/quarterly",
    )


def test_local_transaction_nowcast_is_independent_of_asking_layer():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    with Session() as db:
        db.add_all(
            [
                _market("BUDAPEST", "second_hand", "2025-Q3", 1_100_000),
                _market("BUDAPEST", "second_hand", "2026-Q1", 1_200_000),
                LocalBenchmark(
                    source_key="ksh_ingatlanadattar",
                    country_code="HU",
                    year=2024,
                    area_code="BUDAPEST",
                    area_name="Budapest",
                    street_key="",
                    property_type="all",
                    mean_huf_m2=1_000_000,
                    transaction_count=10_000,
                    source_url="https://ksh.example/local-city",
                ),
                LocalBenchmark(
                    source_key="ksh_ingatlanadattar",
                    country_code="HU",
                    year=2024,
                    area_code="BUDAPEST_06",
                    area_name="Budapest 06. kerület",
                    street_key="",
                    property_type="condominium",
                    mean_huf_m2=1_500_000,
                    transaction_count=300,
                    source_url="https://ksh.example/local",
                ),
                AskingMarketSnapshot(
                    source_key="duna_house_observed",
                    snapshot_date=date(2026, 8, 13),
                    area_code="BUDAPEST_06",
                    property_type="apartment",
                    market_segment="second_hand",
                    sample_size=50,
                    median_huf_m2=2_000_000,
                    mean_huf_m2=2_050_000,
                    p25_huf_m2=1_800_000,
                    p75_huf_m2=2_200_000,
                    observed_active_count=50,
                    confidence="medium",
                    status="observed_subset",
                ),
            ]
        )
        db.commit()

        official = transaction_nowcast(
            db,
            "BUDAPEST_06",
            "second_hand",
            "apartment",
        )
        assert official is not None
        assert official.local_base_huf_m2 == 1_500_000
        assert official.city_reference_huf_m2 == 1_000_000
        assert official.local_factor == 1.5
        assert official.value_huf_m2 == 1_800_000

        comparison = market_comparison(
            db,
            "BUDAPEST_06",
            "second_hand",
            "apartment",
        )
        assert comparison.asking is not None
        assert comparison.asking.median_huf_m2 == 2_000_000
        assert round(comparison.asking_gap_pct or 0, 1) == 11.1
        assert comparison.official is not None
        assert comparison.official.value_huf_m2 == 1_800_000


def test_new_build_does_not_use_unsplit_granular_ksh_factor():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    with Session() as db:
        db.add_all(
            [
                _market("BUDAPEST", "new", "2026-Q1", 1_700_000),
                LocalBenchmark(
                    source_key="ksh_ingatlanadattar",
                    country_code="HU",
                    year=2024,
                    area_code="BUDAPEST",
                    area_name="Budapest",
                    street_key="",
                    property_type="all",
                    mean_huf_m2=1_000_000,
                    source_url="https://ksh.example/local-city",
                ),
                LocalBenchmark(
                    source_key="ksh_ingatlanadattar",
                    country_code="HU",
                    year=2024,
                    area_code="BUDAPEST_06",
                    area_name="Budapest 06. kerület",
                    street_key="",
                    property_type="condominium",
                    mean_huf_m2=1_500_000,
                    source_url="https://ksh.example/local",
                ),
            ]
        )
        db.commit()
        official = transaction_nowcast(db, "BUDAPEST_06", "new", "apartment")
        assert official is not None
        assert official.value_huf_m2 == 1_700_000
        assert official.local_year is None
        assert official.local_factor == 1.0
