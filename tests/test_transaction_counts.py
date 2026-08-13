from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import MarketSnapshot
from app.services.market import ensure_seed_market_data
from app.services.transaction_counts import parse_ksh_transaction_counts


def test_ksh_transaction_count_parser():
    html = """
    <table>
      <tr><th>Second hand dwellings</th></tr>
      <tr><td>Budapest</td><td>capital</td><td>8,446</td></tr>
      <tr><td>Pest</td><td>together</td><td>4,060</td></tr>
      <tr><td>Country</td><td>total</td><td>40,591</td></tr>
      <tr><th>New dwellings</th></tr>
      <tr><td>Budapest</td><td>capital</td><td>1,584</td></tr>
      <tr><td>Pest</td><td>together</td><td>759</td></tr>
      <tr><td>Country</td><td>total</td><td>3,989</td></tr>
    </table>
    """
    rows = parse_ksh_transaction_counts(html)
    assert len(rows) == 6
    assert rows[0] == {
        "area_code": "BUDAPEST",
        "property_market": "second_hand",
        "period": "2021-Q1",
        "sample_size": 8446,
    }


def test_counts_can_enrich_existing_market_snapshot():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    with Session() as db:
        ensure_seed_market_data(db)
        row = db.scalar(
            select(MarketSnapshot).where(
                MarketSnapshot.area_code == "BUDAPEST",
                MarketSnapshot.property_market == "second_hand",
                MarketSnapshot.period == "2026-Q1",
            )
        )
        assert row is not None
        row.sample_size = 6338
        db.commit()
        db.refresh(row)
        assert row.sample_size == 6338
