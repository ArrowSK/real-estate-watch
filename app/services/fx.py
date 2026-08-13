from __future__ import annotations

from datetime import date, datetime
from xml.etree import ElementTree as ET

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import FxSnapshot
from app.services.source_health import mark_failure, mark_success

MNB_FX_SOURCE_KEY = "mnb_fx"

SOAP_ENVELOPE = """<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <GetCurrentExchangeRates xmlns="http://www.mnb.hu/webservices/" />
  </soap:Body>
</soap:Envelope>
"""


def _parse_decimal(text: str) -> float:
    return float(text.strip().replace(" ", "").replace(",", "."))


def parse_mnb_current_rates(xml_text: str) -> tuple[date, dict[str, float]]:
    root = ET.fromstring(xml_text)
    result_node = next((n for n in root.iter() if n.tag.endswith("GetCurrentExchangeRatesResult")), None)
    if result_node is None or not result_node.text:
        raise ValueError("MNB exchange-rate result missing")
    inner = ET.fromstring(result_node.text)
    day = next((n for n in inner.iter() if n.tag.endswith("Day")), None)
    if day is None:
        raise ValueError("MNB exchange-rate day missing")
    rate_date = datetime.strptime(day.attrib["date"], "%Y-%m-%d").date()
    rates: dict[str, float] = {}
    for node in day:
        if not node.tag.endswith("Rate") or not node.text:
            continue
        currency = node.attrib.get("curr")
        unit = float(node.attrib.get("unit", "1"))
        if currency in {"EUR", "USD"}:
            rates[currency] = _parse_decimal(node.text) / unit
    if set(rates) != {"EUR", "USD"}:
        raise ValueError("MNB response did not contain both EUR and USD")
    return rate_date, rates


def validate_rate(currency: str, value: float, previous: float | None = None) -> None:
    if currency not in {"EUR", "USD"}:
        raise ValueError(f"Unsupported currency: {currency}")
    if not 50 <= value <= 1000:
        raise ValueError(f"Implausible {currency}/HUF rate: {value}")
    if previous and abs(value / previous - 1) > 0.15:
        raise ValueError(f"{currency}/HUF moved more than 15% since last stored rate")


def latest_fx(db: Session) -> dict[str, FxSnapshot]:
    result: dict[str, FxSnapshot] = {}
    for currency in ("EUR", "USD"):
        row = db.scalar(
            select(FxSnapshot)
            .where(FxSnapshot.currency == currency, FxSnapshot.status == "verified")
            .order_by(FxSnapshot.rate_date.desc())
            .limit(1)
        )
        if row:
            result[currency] = row
    return result


def refresh_mnb_fx(db: Session) -> dict:
    settings = get_settings()
    previous = latest_fx(db)
    headers = {
        "Content-Type": "text/xml; charset=utf-8",
        "SOAPAction": "http://www.mnb.hu/webservices/MNBArfolyamServiceSoap/GetCurrentExchangeRates",
        "User-Agent": "real-estate-watch/0.1",
    }
    try:
        with httpx.Client(timeout=settings.http_timeout_seconds, follow_redirects=True) as client:
            response = client.post(settings.mnb_fx_url, content=SOAP_ENVELOPE.encode(), headers=headers)
            response.raise_for_status()
        rate_date, rates = parse_mnb_current_rates(response.text)
        for currency, value in rates.items():
            validate_rate(currency, value, previous.get(currency).huf_per_unit if currency in previous else None)
            row = db.scalar(
                select(FxSnapshot).where(
                    FxSnapshot.rate_date == rate_date,
                    FxSnapshot.currency == currency,
                )
            )
            if row is None:
                db.add(
                    FxSnapshot(
                        rate_date=rate_date,
                        currency=currency,
                        huf_per_unit=value,
                        source_key=MNB_FX_SOURCE_KEY,
                        status="verified",
                    )
                )
            else:
                row.huf_per_unit = value
                row.status = "verified"
        mark_success(db, MNB_FX_SOURCE_KEY, f"{rate_date.isoformat()}: EUR and USD")
        db.commit()
        return {"ok": True, "date": rate_date.isoformat(), "rates": rates}
    except Exception as exc:
        db.rollback()
        mark_failure(db, MNB_FX_SOURCE_KEY, exc)
        db.commit()
        return {"ok": False, "error": str(exc)}


def converted_amounts(huf: float, rates: dict[str, FxSnapshot]) -> dict[str, float | None]:
    return {
        "HUF": huf,
        "EUR": huf / rates["EUR"].huf_per_unit if "EUR" in rates else None,
        "USD": huf / rates["USD"].huf_per_unit if "USD" in rates else None,
    }
