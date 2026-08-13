from datetime import date, datetime, timedelta, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import (
    AskingMarketSnapshot,
    ListingSnapshot,
    LocalBenchmark,
    MarketSnapshot,
    ObservedListing,
    ObservedListingAttribute,
)
from app.services.duna_house import DH_SOURCE_KEY, rebuild_asking_aggregates
from app.services.live_intelligence import (
    live_signals,
    local_district_signal,
    local_street_signals,
)


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_live_signals_reconcile_price_cuts_duration_features_and_postcodes():
    now = datetime.now(timezone.utc)
    with _session() as db:
        listing = ObservedListing(
            source_key=DH_SOURCE_KEY,
            external_id="LK123456",
            listing_url="https://dh.hu/ingatlan/LK123456",
            area_code="BUDAPEST_06",
            locality="Budapest 6. kerület",
            postcode="1061",
            property_type="apartment",
            market_segment="second_hand",
            rooms=2,
            first_seen_at=now - timedelta(days=4),
            last_seen_at=now,
            active=True,
            quality_state="usable",
        )
        db.add(listing)
        db.flush()
        db.add_all(
            [
                ListingSnapshot(
                    listing_id=listing.id,
                    snapshot_date=date.today() - timedelta(days=4),
                    asking_price_huf=100_000_000,
                    floor_area_m2=50,
                    price_huf_m2=2_000_000,
                ),
                ListingSnapshot(
                    listing_id=listing.id,
                    snapshot_date=date.today(),
                    asking_price_huf=95_000_000,
                    floor_area_m2=50,
                    price_huf_m2=1_900_000,
                ),
                ObservedListingAttribute(
                    listing_id=listing.id,
                    building_type="tégla",
                    condition="jó állapotú",
                    floor="2. emelet",
                    lift="van",
                    heating="gáz cirkó",
                ),
            ]
        )
        db.commit()

        rebuild_asking_aggregates(db, discovery_count=100)
        signals = live_signals(
            db,
            area_code="BUDAPEST_06",
            property_type="apartment",
            market_segment="second_hand",
        )
        assert signals.sample_size == 1
        assert signals.price_cut_count == 1
        assert signals.price_cut_share == 1
        assert round(signals.median_price_cut_pct or 0, 1) == -5.0
        assert signals.new_7d_count == 1
        assert signals.median_observed_days is not None
        assert 3.5 <= signals.median_observed_days <= 4.5
        assert signals.attribute_listing_coverage_pct == 100
        assert signals.attribute_field_coverage_pct == 50
        assert signals.postcodes == (("1061", 1),)

        postcode_aggregate = db.scalar(
            select(AskingMarketSnapshot).where(
                AskingMarketSnapshot.area_code == "POSTCODE_1061",
                AskingMarketSnapshot.property_type == "apartment",
            )
        )
        assert postcode_aggregate is not None
        assert postcode_aggregate.median_huf_m2 == 1_900_000


def test_local_detail_uses_same_year_local_factor_on_latest_second_hand_benchmark():
    with _session() as db:
        db.add_all(
            [
                MarketSnapshot(
                    country_code="HU",
                    area_code="BUDAPEST",
                    area_name_en="Budapest",
                    area_name_hu="Budapest",
                    property_market="second_hand",
                    period="2026-Q1",
                    observation_date=date(2026, 3, 31),
                    price_huf_m2=1_200_000,
                    source_key="ksh_housing_prices",
                    source_url="https://ksh.example/latest",
                ),
                LocalBenchmark(
                    source_key="ksh_ingatlanadattar",
                    year=2024,
                    area_code="BUDAPEST",
                    area_name="Budapest",
                    street_key="",
                    property_type="all",
                    mean_huf_m2=1_000_000,
                    transaction_count=10_000,
                    source_url="https://ksh.example/city",
                ),
                LocalBenchmark(
                    source_key="ksh_ingatlanadattar",
                    year=2024,
                    area_code="BUDAPEST_06",
                    area_name="Budapest 06. kerület",
                    street_key="",
                    property_type="condominium",
                    mean_huf_m2=1_500_000,
                    transaction_count=300,
                    relative_std_pct=25,
                    source_url="https://ksh.example/district",
                ),
                LocalBenchmark(
                    source_key="ksh_ingatlanadattar",
                    year=2024,
                    area_code="BUDAPEST_06",
                    area_name="Budapest 06. kerület",
                    street_name="Andrássy út",
                    street_key="andrássy út",
                    property_type="condominium",
                    mean_huf_m2=1_800_000,
                    transaction_count=40,
                    relative_std_pct=30,
                    source_url="https://ksh.example/street",
                ),
            ]
        )
        db.commit()

        district = local_district_signal(
            db,
            area_code="BUDAPEST_06",
            property_type="condominium",
            year=2024,
        )
        assert district is not None
        assert district.local_factor == 1.5
        assert district.current_huf_m2 == 1_800_000
        assert district.confidence == "high"

        streets = local_street_signals(
            db,
            area_code="BUDAPEST_06",
            property_type="condominium",
            year=2024,
        )
        assert len(streets) == 1
        assert streets[0].street_name == "Andrássy út"
        assert streets[0].local_factor == 1.8
        assert streets[0].current_huf_m2 == 2_160_000
        assert streets[0].confidence == "medium"
