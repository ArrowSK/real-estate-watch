from pathlib import Path

from fastapi.testclient import TestClient

from app.db import SessionLocal, init_db
from app.main import app
from app.services.market import ensure_seed_market_data


def test_health_and_market_page(tmp_path: Path):
    # The application may already be bound to the default development SQLite engine in this
    # process. This test checks route behaviour rather than engine reconfiguration.
    init_db()
    with SessionLocal() as db:
        ensure_seed_market_data(db)
    with TestClient(app) as client:
        live = client.get("/health/live")
        assert live.status_code == 200
        page = client.get("/")
        assert page.status_code == 200
        assert "Real Estate Watch" in page.text
        mortgage = client.get("/mortgage")
        assert mortgage.status_code == 200
        hu = client.get("/language/hu?next=/", follow_redirects=True)
        assert hu.status_code == 200
        assert "Ingatlanpiaci Figyelő" in hu.text
