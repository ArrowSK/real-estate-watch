from app.services.notifications import notification_text


def test_market_notification_text_contains_change():
    subject, body = notification_text(
        "market_change",
        {
            "changes": [
                {
                    "area": "BUDAPEST",
                    "market": "second_hand",
                    "from": ["2025-Q4", 1_231_000],
                    "to": ["2026-Q1", 1_221_000],
                    "change_percent": -0.8123,
                }
            ]
        },
        "en",
    )
    assert subject == "Market benchmark changed"
    assert "BUDAPEST" in body
    assert "2026-Q1" in body
    assert "HUF/m²" in body


def test_hungarian_source_failure_notification():
    subject, body = notification_text("source_degraded", {}, "hu")
    assert subject == "Adatforrás hiba"
    assert "ellenőrzött adatokat" in body
