from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import LocalMarketBenchmark, SourceHealth
from app.services.http import request_with_retry_client
from app.services.source_health import mark_failure, mark_success

SOURCE_KEY = "ksh_local_market"
USER_AGENT = "RealEstateWatch/0.2 (+https://github.com/ArrowSK/real-estate-watch)"
PROPERTY_COLUMNS = {
    "family_house": (1, 2),
    "condominium": (3, 4),
    "panel": (5, 6),
    "total": (7, 8),
}


def _number(value: str) -> float | None:
    cleaned = value.replace("\xa0", " ").strip()
    if not cleaned or cleaned in {"–", "-", "..", "."}:
        return None
    cleaned = cleaned.replace(" ", "").replace(",", ".")
    return float(cleaned) if re.fullmatch(r"\d+(?:\.\d+)?", cleaned) else None


def _slug(value: str) -> str:
    value = value.upper()
    replacements = str.maketrans("ÁÉÍÓÖŐÚÜŰ", "AEIOOOUUU")
    value = value.translate(replacements)
    return re.sub(r"[^A-Z0-9]+", "-", value).strip("-")[:110]


def parse_ksh_local_table(
    html: str,
    *,
    year: int,
    level: str,
    parent_area_code: str | None = None,
) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    rows = []
    for tr in soup.find_all("tr"):
        cells = [cell.get_text(" ", strip=True) for cell in tr.find_all(["th", "td"])]
        if len(cells) < 10:
            continue
        name = cells[0].strip()
        if not name or name.lower().startswith("az ingatlan"):
            continue

        if level == "district":
            district_match = re.search(r"Budapest\s+(\d{2})\.\s*kerület", name, re.IGNORECASE)
            if not district_match:
                continue
            district = int(district_match.group(1))
            area_code = f"BUDAPEST-{district:02d}"
            parent = "BUDAPEST"
        elif level == "street":
            if not parent_area_code:
                raise ValueError("Street-level KSH rows require a parent district")
            area_code = f"{parent_area_code}:{_slug(name)}"
            parent = parent_area_code
        else:
            raise ValueError(f"Unsupported KSH local level: {level}")

        relative_std = _number(cells[9])
        for property_type, (price_idx, count_idx) in PROPERTY_COLUMNS.items():
            price_thousand = _number(cells[price_idx])
            transactions = _number(cells[count_idx])
            if price_thousand is None:
                continue
            price_huf_m2 = price_thousand * 1000
            if not 20_000 <= price_huf_m2 <= 20_000_000:
                raise ValueError(f"KSH local price outside safety range: {price_huf_m2}")
            rows.append(
                {
                    "area_code": area_code,
                    "parent_area_code": parent,
                    "level": level,
                    "area_name": name,
                    "year": year,
                    "property_type": property_type,
                    "price_huf_m2": price_huf_m2,
                    "transactions": int(transactions) if transactions is not None else None,
                    "relative_std_pct": relative_std,
                }
            )
    if not rows:
        raise ValueError(f"No {level} KSH Ingatlanadattár rows found")
    return rows


def discover_budapest_district_pages(html: str, base_url: str) -> dict[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    output: dict[str, str] = {}
    for link in soup.find_all("a", href=True):
        text = link.get_text(" ", strip=True)
        match = re.search(r"Budapest\s+(\d{2})\.\s*kerület", text, re.IGNORECASE)
        if not match:
            continue
        district = int(match.group(1))
        href = urljoin(base_url, link["href"])
        query = parse_qs(urlparse(href).query)
        if query.get("ter"):
            output[f"BUDAPEST-{district:02d}"] = href
    if len(output) < 20:
        raise ValueError(f"KSH district link discovery incomplete: only {len(output)} districts")
    return output


def _upsert(db: Session, row: dict, source_url: str) -> None:
    existing = db.scalar(
        select(LocalMarketBenchmark).where(
            LocalMarketBenchmark.source_key == SOURCE_KEY,
            LocalMarketBenchmark.year == row["year"],
            LocalMarketBenchmark.area_code == row["area_code"],
            LocalMarketBenchmark.property_type == row["property_type"],
        )
    )
    if existing is None:
        db.add(
            LocalMarketBenchmark(
                parent_area_code=row["parent_area_code"],
                area_code=row["area_code"],
                level=row["level"],
                area_name=row["area_name"],
                year=row["year"],
                property_type=row["property_type"],
                price_huf_m2=row["price_huf_m2"],
                transactions=row["transactions"],
                relative_std_pct=row["relative_std_pct"],
                source_key=SOURCE_KEY,
                source_url=source_url,
            )
        )
    else:
        existing.parent_area_code = row["parent_area_code"]
        existing.level = row["level"]
        existing.area_name = row["area_name"]
        existing.price_huf_m2 = row["price_huf_m2"]
        existing.transactions = row["transactions"]
        existing.relative_std_pct = row["relative_std_pct"]
        existing.source_url = source_url
        existing.collected_at = datetime.now(timezone.utc)


def refresh_ksh_local(
    db: Session,
    *,
    include_streets: bool | None = None,
    force: bool = False,
    contract_only: bool = False,
) -> dict:
    settings = get_settings()
    include_streets = settings.ksh_local_streets_enabled if include_streets is None else include_streets
    health = db.scalar(select(SourceHealth).where(SourceHealth.source_key == SOURCE_KEY))
    if not force and not contract_only and health and health.last_success_at:
        last_success = health.last_success_at
        if last_success.tzinfo is None:
            last_success = last_success.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) - last_success < timedelta(hours=settings.ksh_local_refresh_hours):
            return {"ok": True, "skipped": True, "reason": "granular KSH data is still fresh"}

    overview_url = f"{settings.ksh_local_base_url}?ter=01&year={settings.ksh_local_year}"
    client = httpx.Client(
        timeout=settings.http_timeout_seconds,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT, "Accept-Language": "hu-HU,hu;q=0.9"},
    )
    try:
        response = request_with_retry_client(client, "GET", overview_url)
        district_rows = parse_ksh_local_table(
            response.text,
            year=settings.ksh_local_year,
            level="district",
        )
        for row in district_rows:
            _upsert(db, row, overview_url)

        district_pages: dict[str, str] = {}
        street_rows_count = 0
        if include_streets or contract_only:
            district_pages = discover_budapest_district_pages(response.text, overview_url)
        if include_streets and not contract_only:
            for district_code, district_url in sorted(district_pages.items()):
                street_response = request_with_retry_client(client, "GET", district_url)
                street_rows = parse_ksh_local_table(
                    street_response.text,
                    year=settings.ksh_local_year,
                    level="street",
                    parent_area_code=district_code,
                )
                for row in street_rows:
                    _upsert(db, row, district_url)
                street_rows_count += len(street_rows)
        elif contract_only and district_pages:
            # One street page is enough to verify the live HTML contract in CI.
            district_code, district_url = sorted(district_pages.items())[0]
            street_response = request_with_retry_client(client, "GET", district_url)
            street_rows = parse_ksh_local_table(
                street_response.text,
                year=settings.ksh_local_year,
                level="street",
                parent_area_code=district_code,
            )
            street_rows_count = len(street_rows)

        db.commit()
        mark_success(
            db,
            SOURCE_KEY,
            f"year={settings.ksh_local_year} district_rows={len(district_rows)} street_rows={street_rows_count}",
        )
        db.commit()
        return {
            "ok": True,
            "year": settings.ksh_local_year,
            "district_rows": len(district_rows),
            "street_rows": street_rows_count,
            "district_pages": len(district_pages),
            "contract_only": contract_only,
        }
    except Exception as exc:
        db.rollback()
        mark_failure(db, SOURCE_KEY, exc)
        db.commit()
        return {"ok": False, "error": str(exc)}
    finally:
        client.close()


def local_benchmarks(
    db: Session,
    *,
    parent_area_code: str | None = None,
    level: str | None = None,
    property_type: str = "total",
    year: int | None = None,
) -> list[LocalMarketBenchmark]:
    query = select(LocalMarketBenchmark).where(
        LocalMarketBenchmark.property_type == property_type
    )
    if parent_area_code:
        query = query.where(LocalMarketBenchmark.parent_area_code == parent_area_code)
    if level:
        query = query.where(LocalMarketBenchmark.level == level)
    if year:
        query = query.where(LocalMarketBenchmark.year == year)
    return list(query.order_by(LocalMarketBenchmark.area_name))
