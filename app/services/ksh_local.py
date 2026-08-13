from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import LocalBenchmark, SourceHealth
from app.services.http import request_with_retry
from app.services.source_health import mark_failure, mark_success

KSH_LOCAL_SOURCE_KEY = "ksh_ingatlanadattar"

# KSH's own Ingatlanadattár client maps these territorial identifiers to Budapest districts.
# They are stable source identifiers, not values invented by this application.
BUDAPEST_DISTRICTS: dict[str, int] = {
    "09566": 1,
    "03179": 2,
    "18069": 3,
    "05467": 4,
    "13392": 5,
    "16586": 6,
    "29744": 7,
    "25405": 8,
    "29586": 9,
    "10700": 10,
    "14216": 11,
    "24697": 12,
    "24299": 13,
    "16337": 14,
    "11314": 15,
    "08208": 16,
    "02112": 17,
    "29285": 18,
    "04011": 19,
    "06026": 20,
    "13189": 21,
    "10214": 22,
    "34139": 23,
}

PROPERTY_FIELDS: dict[str, tuple[str, str]] = {
    "house": ("cshaz_ar", "cshaz_db"),
    "condominium": ("tobbl_ar", "tobbl_db"),
    "panel": ("panel_ar", "panel_db"),
    "all": ("total_ar", "total_db"),
}


def street_key(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", value.casefold().strip())


def _district_descriptor(territory_id: str) -> tuple[str, str] | None:
    district = BUDAPEST_DISTRICTS.get(territory_id)
    if district is None:
        return None
    return f"BUDAPEST_{district:02d}", f"Budapest {district:02d}. kerület"


def _source_page(territory_id: str, year: int) -> str:
    return f"https://www.ksh.hu/s/ingatlanadattar/adattar?ter={territory_id}&year={year}"


def _as_number(value) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    cleaned = str(value).strip().replace("\xa0", " ").replace(" ", "").replace(",", ".")
    if not cleaned or not re.fullmatch(r"-?\d+(?:\.\d+)?", cleaned):
        return None
    return float(cleaned)


def parse_ksh_local_json(payload: object, *, include_streets: bool = True) -> list[dict]:
    """Normalize Budapest records from KSH Ingatlanadattár's official client JSON.

    The source currently uses hierarchy level 3 for district totals and level 2 for street
    observations. Missing property-type fields stay missing. Prices are published in thousand
    HUF/m² and are converted to HUF/m² here.
    """
    if not isinstance(payload, list):
        raise ValueError("KSH Ingatlanadattár JSON root is not a list")

    output: list[dict] = []
    seen_district_totals: set[str] = set()
    for raw in payload:
        if not isinstance(raw, dict) or str(raw.get("megye")) != "01":
            continue
        level = raw.get("szint")
        if level not in ({2, 3} if include_streets else {3}):
            continue
        territory_id = str(raw.get("telaz") or "")
        descriptor = _district_descriptor(territory_id)
        if descriptor is None:
            continue
        area_code, area_name = descriptor

        year_value = _as_number(raw.get("ev"))
        if year_value is None:
            raise ValueError("KSH local row is missing its observation year")
        year = int(year_value)
        if year < 1997 or year > datetime.now(timezone.utc).year:
            raise ValueError(f"KSH local observation year outside safety range: {year}")

        if level == 3:
            street_name = None
            seen_district_totals.add(area_code)
        else:
            street_name = str(raw.get("kozter") or "").strip() or None
            if not street_name or street_name.casefold() == "együtt":
                continue

        relative_std = _as_number(raw.get("szoras"))
        for property_type, (price_field, count_field) in PROPERTY_FIELDS.items():
            price_thousand = _as_number(raw.get(price_field))
            if price_thousand is None:
                continue
            price_huf_m2 = price_thousand * 1000
            if not 50_000 <= price_huf_m2 <= 10_000_000:
                raise ValueError(f"KSH local value outside safety range: {price_huf_m2}")
            count = _as_number(raw.get(count_field))
            if count is not None and (count < 0 or count > 1_000_000):
                raise ValueError(f"KSH local transaction count outside safety range: {count}")
            output.append(
                {
                    "year": year,
                    "area_code": area_code,
                    "area_name": area_name,
                    "street_name": street_name,
                    "street_key": street_key(street_name),
                    "property_type": property_type,
                    "mean_huf_m2": price_huf_m2,
                    "transaction_count": int(count) if count is not None else None,
                    "relative_std_pct": relative_std if property_type == "all" else None,
                    "source_url": _source_page(territory_id, year),
                }
            )

    if not output:
        raise ValueError("KSH Ingatlanadattár JSON contained no supported Budapest observations")
    missing = {f"BUDAPEST_{district:02d}" for district in range(1, 24)} - seen_district_totals
    if missing:
        raise ValueError(
            "KSH granular JSON is missing Budapest district totals: " + ", ".join(sorted(missing))
        )
    return output


def local_refresh_due(db: Session) -> bool:
    settings = get_settings()
    health = db.scalar(select(SourceHealth).where(SourceHealth.source_key == KSH_LOCAL_SOURCE_KEY))
    if health is None or health.last_success_at is None:
        return True
    last = health.last_success_at
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - last >= timedelta(hours=settings.ksh_local_refresh_hours)


def _existing_rows(db: Session) -> dict[tuple[int, str, str, str], LocalBenchmark]:
    rows = db.scalars(
        select(LocalBenchmark).where(LocalBenchmark.source_key == KSH_LOCAL_SOURCE_KEY)
    )
    return {
        (row.year, row.area_code, row.street_key, row.property_type): row
        for row in rows
    }


def _upsert_many(db: Session, rows: list[dict]) -> tuple[int, int]:
    existing = _existing_rows(db)
    inserted = 0
    updated = 0
    for data in rows:
        key = (
            data["year"],
            data["area_code"],
            data["street_key"],
            data["property_type"],
        )
        row = existing.get(key)
        if row is None:
            row = LocalBenchmark(source_key=KSH_LOCAL_SOURCE_KEY, **data)
            db.add(row)
            existing[key] = row
            inserted += 1
            continue
        changed = False
        for field in (
            "area_name",
            "street_name",
            "mean_huf_m2",
            "transaction_count",
            "relative_std_pct",
            "source_url",
        ):
            new_value = data[field]
            if getattr(row, field) != new_value:
                setattr(row, field, new_value)
                changed = True
        if row.status != "verified":
            row.status = "verified"
            changed = True
        updated += int(changed)
    return inserted, updated


def refresh_ksh_local(db: Session, *, include_streets: bool = True, force: bool = False) -> dict:
    settings = get_settings()
    if not force and not local_refresh_due(db):
        return {"ok": True, "skipped": True, "reason": "granular KSH refresh not due"}

    try:
        response = request_with_retry(
            "GET",
            settings.ksh_local_data_url,
            timeout=max(settings.http_timeout_seconds, 60),
            attempts=2,
            headers={
                "User-Agent": "real-estate-watch/0.2",
                "Accept": "application/json",
            },
        )
        payload = response.json()
        if not isinstance(payload, list) or len(payload) < 10_000:
            raise ValueError("KSH granular JSON response is unexpectedly small or malformed")
        rows = parse_ksh_local_json(payload, include_streets=include_streets)
        if len(rows) < 1_000:
            raise ValueError("KSH granular Budapest normalization produced unexpectedly few rows")

        inserted, updated = _upsert_many(db, rows)
        years = sorted({row["year"] for row in rows})
        districts = {row["area_code"] for row in rows if row["street_key"] == ""}
        streets = {f'{row["area_code"]}|{row["street_key"]}' for row in rows if row["street_key"]}
        mark_success(
            db,
            KSH_LOCAL_SOURCE_KEY,
            (
                f"{years[0]}–{years[-1]}: {len(rows)} normalized rows; "
                f"{len(districts)} districts; {len(streets)} district/street keys; "
                f"{inserted} inserted; {updated} revised"
            ),
        )
        db.commit()
        return {
            "ok": True,
            "source_rows": len(payload),
            "normalized_rows": len(rows),
            "year_from": years[0],
            "year_to": years[-1],
            "districts": len(districts),
            "street_keys": len(streets),
            "inserted": inserted,
            "updated": updated,
        }
    except Exception as exc:
        db.rollback()
        mark_failure(db, KSH_LOCAL_SOURCE_KEY, exc)
        db.commit()
        return {"ok": False, "error": str(exc)}


def latest_local_benchmark(
    db: Session,
    area_code: str,
    property_type: str = "all",
    street: str | None = None,
) -> LocalBenchmark | None:
    query = select(LocalBenchmark).where(
        LocalBenchmark.source_key == KSH_LOCAL_SOURCE_KEY,
        LocalBenchmark.area_code == area_code,
        LocalBenchmark.property_type == property_type,
        LocalBenchmark.status == "verified",
        LocalBenchmark.street_key == street_key(street),
    )
    return db.scalar(query.order_by(LocalBenchmark.year.desc()).limit(1))


def streets_for_area(db: Session, area_code: str) -> list[str]:
    rows = db.scalars(
        select(LocalBenchmark.street_name)
        .where(
            LocalBenchmark.source_key == KSH_LOCAL_SOURCE_KEY,
            LocalBenchmark.area_code == area_code,
            LocalBenchmark.street_key != "",
            LocalBenchmark.street_name.is_not(None),
        )
        .distinct()
        .order_by(LocalBenchmark.street_name)
    )
    return [value for value in rows if value]
