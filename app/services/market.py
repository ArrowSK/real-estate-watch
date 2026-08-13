from __future__ import annotations

import json
import re
from datetime import date
from importlib.resources import files

from bs4 import BeautifulSoup
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import MarketSnapshot
from app.services.http import request_with_retry
from app.services.source_health import mark_failure, mark_success

KSH_SOURCE_KEY = "ksh_housing_prices"
KSH_SOURCE_URL = "https://www.ksh.hu/stadat_files/lak/en/lak0052.html"

KSH_AREA_ROWS: dict[tuple[str, str], tuple[str, str, str]] = {
    ("Budapest", "capital"): ("BUDAPEST", "Budapest", "Budapest"),
    ("Pest", "together"): ("PEST", "Pest region", "Pest régió"),
    ("Central Transdanubia", "together"): (
        "CENTRAL_TRANSDANUBIA",
        "Central Transdanubia",
        "Közép-Dunántúl",
    ),
    ("Western Transdanubia", "together"): (
        "WESTERN_TRANSDANUBIA",
        "Western Transdanubia",
        "Nyugat-Dunántúl",
    ),
    ("Southern Transdanubia", "together"): (
        "SOUTHERN_TRANSDANUBIA",
        "Southern Transdanubia",
        "Dél-Dunántúl",
    ),
    ("Northern Hungary", "together"): (
        "NORTHERN_HUNGARY",
        "Northern Hungary",
        "Észak-Magyarország",
    ),
    ("Northern Great Plain", "together"): (
        "NORTHERN_GREAT_PLAIN",
        "Northern Great Plain",
        "Észak-Alföld",
    ),
    ("Southern Great Plain", "together"): (
        "SOUTHERN_GREAT_PLAIN",
        "Southern Great Plain",
        "Dél-Alföld",
    ),
    ("Country", "total"): ("HU", "Hungary", "Magyarország"),
}


def _quarter_end(year: int, quarter: int) -> date:
    return date(year, quarter * 3, (31, 30, 30, 31)[quarter - 1])


def _seed_rows() -> list[dict]:
    path = files("app.countries.hu.data").joinpath("market_seed.json")
    return json.loads(path.read_text(encoding="utf-8"))


def validate_market_value(price_huf_m2: float) -> None:
    if not 50_000 <= price_huf_m2 <= 10_000_000:
        raise ValueError(f"Market value outside safety range: {price_huf_m2}")


def upsert_market_snapshot(db: Session, data: dict, *, source_key: str = KSH_SOURCE_KEY) -> MarketSnapshot:
    price = float(data["price_huf_m2"])
    validate_market_value(price)
    row = db.scalar(
        select(MarketSnapshot).where(
            MarketSnapshot.source_key == source_key,
            MarketSnapshot.area_code == data["area_code"],
            MarketSnapshot.property_market == data["property_market"],
            MarketSnapshot.period == data["period"],
            MarketSnapshot.metric == data.get("metric", "mean"),
        )
    )
    if row is None:
        row = MarketSnapshot(
            country_code="HU",
            area_code=data["area_code"],
            area_name_en=data["area_name_en"],
            area_name_hu=data["area_name_hu"],
            property_market=data["property_market"],
            period=data["period"],
            observation_date=date.fromisoformat(str(data["observation_date"])),
            metric=data.get("metric", "mean"),
            price_huf_m2=price,
            sample_size=data.get("sample_size"),
            source_key=source_key,
            source_url=data.get("source_url", KSH_SOURCE_URL),
            status=data.get("status", "verified"),
            note_en=data.get(
                "note_en",
                "KSH mean transaction price per square metre; official data may be revised.",
            ),
            note_hu=data.get(
                "note_hu",
                "KSH átlagos tranzakciós négyzetméterár; a hivatalos adat később módosulhat.",
            ),
        )
        db.add(row)
    else:
        # Official KSH tables can revise preliminary observations. Replace only after validation.
        row.price_huf_m2 = price
        row.observation_date = date.fromisoformat(str(data["observation_date"]))
        row.status = data.get("status", "verified")
        row.source_url = data.get("source_url", KSH_SOURCE_URL)
    return row


def ensure_seed_market_data(db: Session) -> int:
    count = 0
    for item in _seed_rows():
        upsert_market_snapshot(db, item)
        count += 1
    db.commit()
    return count


def _number(value: str) -> int | None:
    value = value.strip().replace("\xa0", " ")
    if not value or value in {"..", ".", "-"}:
        return None
    value = value.replace(",", "").replace(" ", "")
    return int(value) if re.fullmatch(r"\d+", value) else None


def parse_ksh_benchmarks(html: str) -> list[dict]:
    """Parse the deliberately supported KSH series.

    The parser is intentionally narrow. If KSH changes the table structure, collection fails
    rather than guessing. The caller then keeps the last known-good data.
    """
    soup = BeautifulSoup(html, "html.parser")
    rows = soup.find_all("tr")
    if not rows:
        raise ValueError("KSH table rows not found")

    current_market: str | None = None
    output: list[dict] = []
    for tr in rows:
        cells = [c.get_text(" ", strip=True) for c in tr.find_all(["th", "td"])]
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

        row_key = (cells[0].strip(), cells[1].strip().lower())
        descriptor = KSH_AREA_ROWS.get(row_key)
        if descriptor is None:
            continue
        area_code, area_en, area_hu = descriptor

        values = [_number(x) for x in cells[2:]]
        for idx, value in enumerate(values):
            if value is None:
                continue
            year = 2021 + idx // 4
            quarter = 1 + idx % 4
            if year > date.today().year + 1:
                raise ValueError("KSH row length no longer matches expected quarterly structure")
            output.append(
                {
                    "area_code": area_code,
                    "area_name_en": area_en,
                    "area_name_hu": area_hu,
                    "property_market": current_market,
                    "period": f"{year}-Q{quarter}",
                    "observation_date": _quarter_end(year, quarter).isoformat(),
                    "price_huf_m2": value * 1000,
                    "source_url": KSH_SOURCE_URL,
                }
            )

    required = {
        ("BUDAPEST", "second_hand"),
        ("BUDAPEST", "new"),
        ("HU", "second_hand"),
        ("HU", "new"),
    }
    seen = {(x["area_code"], x["property_market"]) for x in output}
    if not required.issubset(seen):
        raise ValueError(f"KSH parser incomplete; supported series missing: {sorted(required - seen)}")
    return output


def refresh_ksh(db: Session) -> dict:
    settings = get_settings()
    try:
        response = request_with_retry(
            "GET",
            settings.ksh_market_url,
            timeout=settings.http_timeout_seconds,
            headers={"User-Agent": "real-estate-watch/0.1"},
        )
        parsed = parse_ksh_benchmarks(response.text)
        for item in parsed:
            upsert_market_snapshot(db, item)
        mark_success(db, KSH_SOURCE_KEY, f"{len(parsed)} verified quarterly observations")
        db.commit()
        return {"ok": True, "count": len(parsed)}
    except Exception as exc:
        db.rollback()
        mark_failure(db, KSH_SOURCE_KEY, exc)
        db.commit()
        return {"ok": False, "error": str(exc)}


def market_series(db: Session, area_code: str, property_market: str) -> list[MarketSnapshot]:
    return list(
        db.scalars(
            select(MarketSnapshot)
            .where(
                MarketSnapshot.area_code == area_code,
                MarketSnapshot.property_market == property_market,
                MarketSnapshot.status == "verified",
            )
            .order_by(MarketSnapshot.observation_date.asc())
        )
    )


def latest_market(db: Session, area_code: str, property_market: str) -> MarketSnapshot | None:
    return db.scalar(
        select(MarketSnapshot)
        .where(
            MarketSnapshot.area_code == area_code,
            MarketSnapshot.property_market == property_market,
            MarketSnapshot.status == "verified",
        )
        .order_by(MarketSnapshot.observation_date.desc())
        .limit(1)
    )
