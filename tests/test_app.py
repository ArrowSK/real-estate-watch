from fastapi.testclient import TestClient

from app.db import SessionLocal, init_db
from app.main import app
from app.services.market import ensure_seed_market_data


def seed_database() -> None:
    init_db()
    with SessionLocal() as db:
        ensure_seed_market_data(db)


def test_health_market_and_language_routes():
    seed_database()
    with TestClient(app) as client:
        live = client.get("/health/live")
        assert live.status_code == 200
        page = client.get("/?area=BUDAPEST&market=second_hand&property_type=all&range=6m")
        assert page.status_code == 200
        assert "Real Estate Watch" in page.text
        assert "6 months" in page.text
        assert "Two markets, kept separate" in page.text
        district = client.get("/?area=BUDAPEST_06&market=second_hand&property_type=apartment")
        assert district.status_code == 200
        mortgage = client.get("/mortgage")
        assert mortgage.status_code == 200
        hu = client.get("/language/hu?next=/", follow_redirects=True)
        assert hu.status_code == 200
        assert "Ingatlanpiaci Figyelő" in hu.text


def test_valuation_uses_selected_market_baseline():
    seed_database()
    with TestClient(app) as client:
        response = client.post(
            "/valuation",
            data={
                "area": "BUDAPEST",
                "market": "second_hand",
                "property_type": "all",
                "floor_area": "80",
                "asking_price": "",
                "factors": "balcony",
            },
        )
        assert response.status_code == 200
        assert "1,221,000 HUF/m²" in response.text
        assert "102,564,000" in response.text


def test_market_api_exposes_layers_and_sample_size():
    seed_database()
    with TestClient(app) as client:
        response = client.get(
            "/api/market?area=BUDAPEST&market=second_hand&property_type=all"
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["quarterly_series"]
        assert "sample_size" in payload["quarterly_series"][-1]
        assert payload["official_nowcast"]
        assert "price_huf_m2" in payload["official_nowcast"]
        assert "observed_asking" in payload
