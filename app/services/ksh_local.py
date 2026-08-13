from __future__ import annotations

import re
import time
from datetime import date, datetime, timedelta, timezone
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from bs4 import BeautifulSoup
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import LocalBenchmark, SourceHealth
from app.services.http import request_with_retry
from app.services.source_health import mark_failure, mark_success

KSH_LOCAL_SOURCE_KEY = "ksh_ingatlanadattar"
PROPERTY_COLUMNS = {
    "house": (1, 2),
    "condominium": (3, 4),
    "panel": (5, 6),
    "all": (7, 8),
}


def street_key(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", value.casefold().strip())


def _number(value: str) -> float | None:
    cleaned = value.strip().replace("\xa0", " ")
    if cleaned in {"", "–", "—", "-", "..", "."}:
        return None
    cleaned = cleaned.replace(" ", "").replace(",", ".")
    return float(cleaned) if re.fullmatch(r"\d+(?:\.\d+)?", cleaned) else None


def _year_from_page(soup: BeautifulSoup) -> int:
    years: list[int] = []
    for option in soup.find_all("option"):
        for value in (option.get("value"), option.get_text(" ", strip=True)):
            match = re.search(r"\b(19\d{2}|20\d{2})\b", str(value or ""))
            if match:
                years.append(int(match.group(1)))
    if years:
        return max(years)
    text = soup.get_text(" ", strip=True)
    years = [int(value) for value in re.findall(r"\b(?:19|20)\d{2}\b", text)]
    plausible = [value for value in years if 1997 <= value <= date.today().year]
    if plausible:
        return max(plausible)
    return date.today().year - 1


def _district_code(label: str) -> str | None:
    match = re.search(r"Budapest\s+0?(\d{1,2})\.\s*kerület", label, re.I)
    if not match:
        return None
    district = int(match.group(1))
    return f"BUDAPEST_{district:02d}" if 1 <= district <= 23 else None


def _district_links(soup: BeautifulSoup, base_url: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for anchor in soup.find_all("a", href=True):
        label = anchor.get_text(" ", strip=True)
        code = _district_code(label)
        if not code:
            continue
        href = str(anchor["href"])
        if href.startswith("http"):
            url = href
        elif href.startswith("/"):
            parsed = urlparse(base_url)
            url = f"{parsed.scheme}://{parsed.netloc}{href}"
        else:
            url = base_url.rsplit("/", 1)[0] + "/" + href
        result[code] = url
    return result


def parse_ksh_local_page(
    html: str,
    *,
    source_url: str,
    fixed_area_code: str | None = None,
    fixed_area_name: str | None = None,
) -> tuple[int, list[dict], dict[str, str]]:
    """Parse the public KSH Ingatlanadattár table without guessing missing cells.

    Root Budapest pages contain district rows. District pages contain street rows. The table
    uses the same factual column order for house, condominium, panel and all dwellings.
    """
    soup = BeautifulSoup(html, "html.parser")
    year = _year_from_page(soup)
    output: list[dict] = []
    table = soup.find("table")
    if table is None:
        raise ValueError("KSH Ingatlanadattár table not found")

    for tr in table.find_all("tr"):
        cells = [cell.get_text(" ", strip=True) for cell in tr.find_all(["th", "td"])]
        if len(cells) < 10:
            continue
        label = cells[0].strip()
        if not label or "ingatlan helye" in label.casefold():
            continue

        if fixed_area_code:
            area_code = fixed_area_code
            area_name = fixed_area_name or fixed_area_code
            street_name = label
        else:
            area_code = _district_code(label)
            if not area_code:
                if label.casefold().startswith("budapest összesen"):
                    area_code = "BUDAPEST"
                else:
                    continue
            area_name = label
            street_name = None

        relative_std = _number(cells[9])
        for property_type, (price_col, count_col) in PROPERTY_COLUMNS.items():
            price_thousand = _number(cells[price_col])
            count = _number(cells[count_col])
            if price_thousand is None:
                continue
            price_huf_m2 = price_thousand * 1000
            if not 50_000 <= price_huf_m2 <= 10_000_000:
                raise ValueError(f"KSH local value outside safety range: {price_huf_m2}")
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
                    "source_url": source_url,
                }
            )

    if not output:
        raise ValueError("KSH Ingatlanadattár contained no supported observations")
    return year, output, _district_links(soup, source_url)


def _url_with_year(url: str, year: int) -> str:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    query["year"] = [str(year)]
    return urlunparse(
        (parsed.scheme, parsed.netloc, parsed.path, parsed.params, urlencode(query, doseq=True), parsed.fragment)
    )


def _upsert(db: Session, data: dict) -> bool:
    row = db.scalar(
        select(LocalBenchmark).where(
            LocalBenchmark.source_key == KSH_LOCAL_SOURCE_KEY,
            LocalBenchmark.year == data["year"],
            LocalBenchmark.area_code == data["area_code"],
            LocalBenchmark.street_key == data["street_key"],
            LocalBenchmark.property_type == data["property_type"],
        )
    )
    if row is None:
        db.add(LocalBenchmark(source_key=KSH_LOCAL_SOURCE_KEY, **data))
        return True
    row.area_name = data["area_name"]
    row.street_name = data["street_name"]
    row.mean_huf_m2 = data["mean_huf_m2"]
    row.transaction_count = data["transaction_count"]
    row.relative_std_pct = data["relative_std_pct"]
    row.source_url = data["source_url"]
    row.status = "verified"
    return False


def local_refresh_due(db: Session) -> bool:
    settings = get_settings()
    health = db.scalar(select(SourceHealth).where(SourceHealth.source_key == KSH_LOCAL_SOURCE_KEY))
    if health is None or health.last_success_at is None:
        return True
    last = health.last_success_at
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - last >= timedelta(hours=settings.ksh_local_refresh_hours)


def refresh_ksh_local(db: Session, *, include_streets: bool = True, force: bool = False) -> dict:
    settings = get_settings()
    if not force and not local_refresh_due(db):
        return {"ok": True, "skipped": True, "reason": "granular KSH refresh not due"}

    root_url = f"{settings.ksh_local_url}?ter=01"
    try:
        response = request_with_retry(
            "GET",
            root_url,
            timeout=settings.http_timeout_seconds,
            headers={"User-Agent": "real-estate-watch/0.2"},
        )
        year, rows, district_links = parse_ksh_local_page(response.text, source_url=root_url)
        inserted = 0
        for item in rows:
            inserted += int(_upsert(db, item))
        db.commit()

        street_rows = 0
        districts_loaded = 0
        if include_streets:
            if len(district_links) < 20:
                raise ValueError(
                    f"KSH local root exposed only {len(district_links)} district links; refusing partial street crawl"
                )
            for code, link in sorted(district_links.items()):
                time.sleep(0.08)
                district_url = _url_with_year(link, year)
                page = request_with_retry(
                    "GET",
                    district_url,
                    timeout=settings.http_timeout_seconds,
                    attempts=2,
                    headers={"User-Agent": "real-estate-watch/0.2"},
                )
                district_name = f"Budapest {int(code[-2:]):02d}. kerület"
                parsed_year, district_rows, _ = parse_ksh_local_page(
                    page.text,
                    source_url=district_url,
                    fixed_area_code=code,
                    fixed_area_name=district_name,
                )
                if parsed_year != year:
                    raise ValueError(
                        f"KSH local year mismatch for {code}: root {year}, district {parsed_year}"
                    )
                for item in district_rows:
                    inserted += int(_upsert(db, item))
                street_rows += len(district_rows)
                districts_loaded += 1
                db.commit()

        mark_success(
            db,
            KSH_LOCAL_SOURCE_KEY,
            f"{year}: {len(rows)} district/type rows; {street_rows} street/type rows; {inserted} inserted",
        )
        db.commit()
        return {
            "ok": True,
            "year": year,
            "district_rows": len(rows),
            "districts_loaded": districts_loaded,
            "street_rows": street_rows,
            "inserted": inserted,
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
