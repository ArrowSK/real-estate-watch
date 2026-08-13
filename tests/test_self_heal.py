from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import MarketSnapshot
from app.services.self_heal import heal_reference_data


def test_self_heal_restores_reference_market(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    with Session() as db:
        result = heal_reference_data(db)
        count = db.scalar(select(func.count()).select_from(MarketSnapshot))
        assert result["enabled"]
        assert count and count > 0
