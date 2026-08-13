from sqlalchemy import create_engine, delete, func, select
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import MarketSnapshot
from app.services.market import ensure_seed_market_data
from app.services.self_heal import heal_reference_data


def make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def test_self_heal_restores_reference_market():
    Session = make_session()
    with Session() as db:
        result = heal_reference_data(db)
        count = db.scalar(select(func.count()).select_from(MarketSnapshot))
        assert result["enabled"]
        assert result["actions"]
        assert count and count > 0


def test_seed_never_overwrites_live_revision():
    Session = make_session()
    with Session() as db:
        first_insert = ensure_seed_market_data(db)
        assert first_insert > 0
        row = db.scalar(
            select(MarketSnapshot).where(
                MarketSnapshot.area_code == "BUDAPEST",
                MarketSnapshot.property_market == "second_hand",
                MarketSnapshot.period == "2026-Q1",
            )
        )
        assert row is not None
        row.price_huf_m2 = 1_250_000
        db.commit()

        second_insert = ensure_seed_market_data(db)
        db.refresh(row)
        assert second_insert == 0
        assert row.price_huf_m2 == 1_250_000


def test_self_heal_repairs_only_missing_reference_rows():
    Session = make_session()
    with Session() as db:
        ensure_seed_market_data(db)
        before = db.scalar(select(func.count()).select_from(MarketSnapshot))
        db.execute(
            delete(MarketSnapshot).where(
                MarketSnapshot.area_code == "BUDAPEST",
                MarketSnapshot.property_market == "new",
                MarketSnapshot.period == "2026-Q1",
            )
        )
        db.commit()

        result = heal_reference_data(db)
        after = db.scalar(select(func.count()).select_from(MarketSnapshot))
        restored = db.scalar(
            select(MarketSnapshot).where(
                MarketSnapshot.area_code == "BUDAPEST",
                MarketSnapshot.property_market == "new",
                MarketSnapshot.period == "2026-Q1",
            )
        )
        assert result["actions"] == ["restored 1 missing bundled KSH reference observations"]
        assert after == before
        assert restored is not None
        assert restored.price_huf_m2 == 1_557_000
