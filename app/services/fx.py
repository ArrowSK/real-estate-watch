from __future__ import annotations

import re
from datetime import date

from bs4 import BeautifulSoup
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import FxSnapshot
from app.services.http import request_with_retry
from app.services.source_health import mark_failure, mark_success

MNB_FX_SOURCE_KEY = "mnb_fx"

_HU_MONTHS = {
    "január": 1,
    "február": 2,
    "március": 3,
    "április": 4,
    "május": 5,
    "június": 6,
    "július": 7,
    "augusztus": 8,
    "szeptember": 9,
    "október": 10,
    "november": 11,
    "december": 12,
}


def _parse_decimal(text: str) -> float:
    return float(text.strip().replace("\xa0", " ").replace(" ", "").replace(",", "."))


def _parse_mnb_rate_date(page_text: str) -> date:
    match = re.search(
        r"Napi\s+árfolyamok\s*:\s*(\d{4})\.\s*([a-záéíóöőúüű]+)\s+(\d{1,2})\.",
        page_text,
        flags=re.IGNORECASE,
    )
    if not match:
        raise ValueError("MNB latest-rates date not found")
    year = int(match.group(1))
    month_name = match.group(2).lower()
    month = _HU_MONTHS.get(month_name)
    if month is None:
        raise ValueError(f"Unknown Hungarian month name in MNB response: {month_name}")
    return date(year, month, int(match.group(3)))


def parse_mnb_current_rates(html: str) -> tuple[date, dict[str, float]]:
    """Parse the official MNB latest-rates page.

    The older SOAP endpoint is still documented by MNB, but in August 2026 its public POST
    route returned HTTP 404 in our live contract check. The public latest-rates page is an
    official MNB source, exposes the same published daily rates, and can be validated without
    depending on an undocumented SOAP routing workaround.
    """
    soup = BeautifulSoup(html, "html.parser")
    page_text = soup.get_text(" ", strip=True)
    rate_date = _parse_mnb_rate_date(page_text)

    rates: dict[str, float] = {}
    for row in soup.find_all("tr"):
        cells = [cell.get_text(" ", strip=True) for cell in row.find_all(["th", "td"])]
        if len(cells) < 4:
            continue
        currency = cells[0].strip().upper()
        if currency not in {"EUR", "USD"}:
            continue
        try:
            unit = _parse_decimal(cells[2])
            value_huf = _parse_decimal(cells[3])
        except ValueError as exc:
            raise ValueError(f"Malformed {currency} row in MNB response") from exc
        if unit <= 0:
            raise ValueError(f"Invalid {currency} unit in MNB response")
        rates[currency] = value_huf / unit

    if set(rates) != {"EUR", "USD"}:
        raise ValueError("MNB response did not contain both EUR and USD")
    return rate_date, rates


def validate_rate_date(rate_date: date) -> None:
    age_days = (date.today() - rate_date).days
    if age_days < -1:
        raise ValueError(f"MNB rate date is unexpectedly in the future: {rate_date.isoformat()}")
    # Weekends and Hungarian public holidays can legitimately leave the most recent fixing a
    # few days old. Ten days is deliberately generous but still prevents a stale archived page
    # from being accepted as current indefinitely.
    if age_days > 10:
        raise ValueError(f"MNB latest official rate is unexpectedly old: {rate_date.isoformat()}")


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
    try:
        response = request_with_retry(
            "GET",
            settings.mnb_fx_url,
            timeout=settings.http_timeout_seconds,
            headers={"User-Agent": "real-estate-watch/0.1"},
        )
        rate_date, rates = parse_mnb_current_rates(response.text)
        validate_rate_date(rate_date)
        for currency, value in rates.items():
            validate_rate(
                currency,
                value,
                previous.get(currency).huf_per_unit if currency in previous else None,
            )
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
