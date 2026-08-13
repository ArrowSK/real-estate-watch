from __future__ import annotations

import re
from datetime import date

from bs4 import BeautifulSoup
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import MarketSnapshot
from app.services.http import request_with_retry
from app.services.market import KSH_AREA_ROWS, KSH_SOURCE_KEY
from app.services.source_health import mark_failure, mark_success

KSH_COUNTS_SOURCE_KEY = "ksh_transaction_counts"
KSH_COUNTS_SOURCE_URL = "https://www.ksh.hu/stadat_files/lak/en/lak0053.html"


def _count(value: str) -> int | None:
    value = value.strip().replace("\xa0", " ")
    if not value or value in {"..", ".", "-"}:
        return None
    value = value.replace(",", "").replace(" ", "")
    if not re.fullmatch(r"\d+", value):
        return None
    number = int(value)
    if number < 0 or number > 5_000_000:
        raise ValueError(f"Implausible transaction count: {number}")
    return number


def parse_ksh_transaction_counts(html: str) -> list[dict]:
    """Parse the KSH transaction-count table using the same supported geography as prices."""
    soup = BeautifulSoup(html, "html.parser")
    rows = soup.find_all("tr")
    if not rows:
        raise ValueError("KSH transaction-count table rows not found")

    current_market: str | None = None
    output: list[dict] = []
    for tr in rows:
        cells = [cell.get_text(" ", strip=True) for cell in tr.find_all(["th", "td"])]
        if not cells:
            continue
        joined = " ".join(cells).lower()
        if "second hand dwellings" in joined:
            current_market = "second_hand"
            continue
        if "new dwellings" in joined:
            current_market = "new"
            continue
        if current_market is None or len(cells) < 3:
            continue

        descriptor = KSH_AREA_ROWS.get((cells[0].strip(), cells[1].strip().lower()))
        if descriptor is None:
            continue
        area_code = descriptor[0]

        for idx, raw in enumerate(cells[2:]):
            count = _count(raw)
            if count is None:
                continue
            year = 2021 + idx // 4
            quarter = 1 + idx % 4
            if year > date.today().year + 1:
                raise ValueError("KSH count row length no longer matches expected quarterly structure")
            output.append(
                {
                    "area_code": area_code,
                    "property_market": current_market,
                    "period": f"{year}-Q{quarter}",
                    "sample_size": count,
                }
            )

    required = {
        ("BUDAPEST", "second_hand"),
        ("BUDAPEST", "new"),
        ("HU", "second_hand"),
        ("HU", "new"),
    }
    seen = {(item["area_code"], item["property_market"]) for item in output}
    if not required.issubset(seen):
        raise ValueError(f"KSH transaction-count parser incomplete: {sorted(required - seen)}")
    return output


def refresh_ksh_transaction_counts(db: Session) -> dict:
    """Attach official transaction counts to matching KSH price observations.

    Counts are supplementary. If a price is unavailable for a quarter, no synthetic market
    observation is created just because KSH published a transaction count for that quarter.
    """
    settings = get_settings()
    try:
        response = request_with_retry(
            "GET",
            settings.ksh_transactions_url,
            timeout=settings.http_timeout_seconds,
            headers={"User-Agent": "real-estate-watch/0.1"},
        )
        parsed = parse_ksh_transaction_counts(response.text)
        matched = 0
        for item in parsed:
            row = db.scalar(
                select(MarketSnapshot).where(
                    MarketSnapshot.source_key == KSH_SOURCE_KEY,
                    MarketSnapshot.area_code == item["area_code"],
                    MarketSnapshot.property_market == item["property_market"],
                    MarketSnapshot.period == item["period"],
                    MarketSnapshot.metric == "mean",
                )
            )
            if row is None:
                continue
            row.sample_size = item["sample_size"]
            matched += 1
        mark_success(
            db,
            KSH_COUNTS_SOURCE_KEY,
            f"{matched} market observations enriched from {len(parsed)} published counts",
        )
        db.commit()
        return {"ok": True, "published": len(parsed), "matched": matched}
    except Exception as exc:
        db.rollback()
        mark_failure(db, KSH_COUNTS_SOURCE_KEY, exc)
        db.commit()
        return {"ok": False, "error": str(exc)}
