from app.services.fx import parse_mnb_current_rates, validate_rate


SOAP = """<?xml version='1.0'?>
<soap:Envelope xmlns:soap='http://schemas.xmlsoap.org/soap/envelope/'>
  <soap:Body>
    <GetCurrentExchangeRatesResponse xmlns='http://www.mnb.hu/webservices/'>
      <GetCurrentExchangeRatesResult>&lt;MNBCurrentExchangeRates&gt;&lt;Day date=&quot;2026-08-13&quot;&gt;&lt;Rate curr=&quot;EUR&quot; unit=&quot;1&quot;&gt;395,50&lt;/Rate&gt;&lt;Rate curr=&quot;USD&quot; unit=&quot;1&quot;&gt;340,25&lt;/Rate&gt;&lt;/Day&gt;&lt;/MNBCurrentExchangeRates&gt;</GetCurrentExchangeRatesResult>
    </GetCurrentExchangeRatesResponse>
  </soap:Body>
</soap:Envelope>
"""


def test_parse_mnb_current_rates():
    day, rates = parse_mnb_current_rates(SOAP)
    assert day.isoformat() == "2026-08-13"
    assert rates == {"EUR": 395.5, "USD": 340.25}


def test_fx_safety_jump():
    try:
        validate_rate("EUR", 500, 395)
    except ValueError as exc:
        assert "15%" in str(exc)
    else:
        raise AssertionError("large FX jump should be rejected")
