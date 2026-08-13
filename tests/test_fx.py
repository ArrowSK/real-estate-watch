from datetime import date, timedelta

from app.services.fx import parse_mnb_current_rates, validate_rate, validate_rate_date


HTML = """
<html><body>
  <h1>Az MNB legfrissebb hivatalos devizaárfolyamai</h1>
  <p>Napi árfolyamok: 2026. augusztus 13., csütörtök</p>
  <table>
    <tr><th>Pénznem</th><th>Devizanév</th><th>Egység</th><th>Forintban kifejezett érték</th></tr>
    <tr><td>CHF</td><td>svájci frank</td><td>1</td><td>390,00</td></tr>
    <tr><td>EUR</td><td>euro</td><td>1</td><td>363,36</td></tr>
    <tr><td>USD</td><td>USA dollár</td><td>1</td><td>314,30</td></tr>
  </table>
</body></html>
"""


def test_parse_mnb_current_rates():
    day, rates = parse_mnb_current_rates(HTML)
    assert day.isoformat() == "2026-08-13"
    assert rates == {"EUR": 363.36, "USD": 314.30}


def test_fx_safety_jump():
    try:
        validate_rate("EUR", 500, 395)
    except ValueError as exc:
        assert "15%" in str(exc)
    else:
        raise AssertionError("large FX jump should be rejected")


def test_fx_source_date_rejects_old_page():
    old = date.today() - timedelta(days=11)
    try:
        validate_rate_date(old)
    except ValueError as exc:
        assert "unexpectedly old" in str(exc)
    else:
        raise AssertionError("stale MNB latest-rates page should be rejected")
