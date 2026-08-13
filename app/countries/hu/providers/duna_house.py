from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import ListingSnapshot, ObservedListing, ProviderPolicyState
from app.services.http import request_with_retry_client
from app.services.source_health import mark_failure, mark_success

PROVIDER_KEY = "duna_house"
SOURCE_KEY = "duna_house_observed"
POLICY_SOURCE_KEY = "duna_house_policy"

# We do not interpret robots.txt as a licence. These signatures merely pin the access state
# that was manually reviewed for this experimental provider on 2026-08-13. Any change pauses
# collection until the repository manifest is reviewed again.
REVIEWED_ON = "2026-08-13"
REVIEWED_ROBOTS_LINES = (
    "User-agent: *",
    "Allow: /",
    "Sitemap: https://newdhapi01.dh.hu/api/getFileItem/sitemap_properties",
)
REVIEWED_LEGAL_MARKERS = (
    "Adatkezelési tájékoztató",
    "Duna House Franchise Kft.",
    "A Weboldalt a DUNA HOUSE önállóan tartja fenn",
    "A hirdetésben személyes adatok nem szerepelnek, csak a Partnerek, és az Ingatlanértékesítő elérhetőségei.",
)
REVIEWED_ROBOTS_SIGNATURE = "4d4267d3f6d33db46548447da307a6f35093a47cd3416978cb8618071650fdcf"
REVIEWED_LEGAL_SIGNATURE = "502d2b19c52ee531d0c6dad96933be1e49605ba4b28c926bc971f667d3062933"

USER_AGENT = "RealEstateWatch/0.2 (+https://github.com/ArrowSK/real-estate-watch)"


@dataclass(frozen=True)
class SitemapItem:
    url: str
    lastmod: str | None = None


@dataclass(frozen=True)
class ParsedListing:
    external_id: str
    source_url: str
    price_huf: float
    area_m2: float
    rooms: float | None
    postal_code: str | None
    city: str | None
    district: int | None
    property_type: str
    market_class: str
    market_segment: str
    status_label: str | None
    building_type: str | None
    condition: str | None
    construction_year: int | None
    floor: str | None
    lift: str | None
    balcony: str | None
    view: str | None
    orientation: str | None
    heating: str | None
    energy_rating: str | None

    @property
    def price_huf_m2(self) -> float:
        return self.price_huf / self.area_m2

    @property
    def area_code(self) -> str:
        if self.district:
            return f"BUDAPEST-{self.district:02d}"
        if self.postal_code:
            return f"HU-{self.postal_code}"
        if self.city:
            safe = re.sub(r"[^A-Z0-9]+", "-", self.city.upper()).strip("-")
            return f"HU-{safe}"
        return "HU-UNKNOWN"


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _policy_state(db: Session) -> ProviderPolicyState:
    row = db.scalar(select(ProviderPolicyState).where(ProviderPolicyState.provider_key == PROVIDER_KEY))
    if row is None:
        row = ProviderPolicyState(provider_key=PROVIDER_KEY)
        db.add(row)
        db.flush()
    return row


def evaluate_policy_text(robots_text: str, legal_text: str) -> tuple[bool, dict[str, str]]:
    normalized_robots = _normalize_space(robots_text)
    normalized_legal = _normalize_space(BeautifulSoup(legal_text, "html.parser").get_text(" ", strip=True))

    missing_robots = [line for line in REVIEWED_ROBOTS_LINES if _normalize_space(line) not in normalized_robots]
    missing_legal = [marker for marker in REVIEWED_LEGAL_MARKERS if _normalize_space(marker) not in normalized_legal]

    robots_signature = _sha("\n".join(REVIEWED_ROBOTS_LINES))
    legal_signature = _sha("\n".join(REVIEWED_LEGAL_MARKERS))
    signatures_match = (
        robots_signature == REVIEWED_ROBOTS_SIGNATURE
        and legal_signature == REVIEWED_LEGAL_SIGNATURE
    )
    ok = not missing_robots and not missing_legal and signatures_match
    detail = {
        "reviewed_on": REVIEWED_ON,
        "robots_signature": robots_signature,
        "legal_signature": legal_signature,
        "missing_robots": ", ".join(missing_robots),
        "missing_legal": ", ".join(missing_legal),
    }
    return ok, detail


def check_provider_policy(db: Session, client: httpx.Client | None = None) -> dict:
    settings = get_settings()
    if not settings.duna_house_enabled:
        return {"ok": False, "paused": True, "reason": "provider disabled by configuration"}

    owned_client = client is None
    client = client or httpx.Client(
        timeout=settings.http_timeout_seconds,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT},
    )
    try:
        robots = request_with_retry_client(client, "GET", settings.duna_house_robots_url).text
        legal = request_with_retry_client(client, "GET", settings.duna_house_legal_url).text
        ok, detail = evaluate_policy_text(robots, legal)
        state = _policy_state(db)
        state.checked_at = datetime.now(timezone.utc)
        state.robots_signature = detail["robots_signature"]
        state.legal_signature = detail["legal_signature"]
        state.detail = json.dumps(detail, ensure_ascii=False)
        state.state = "reviewed_experimental" if ok else "paused_policy_change"
        if ok:
            mark_success(db, POLICY_SOURCE_KEY, f"reviewed access markers unchanged since {REVIEWED_ON}")
        else:
            mark_failure(db, POLICY_SOURCE_KEY, ValueError("Duna House access/legal markers changed"))
        db.commit()
        return {"ok": ok, "paused": not ok, **detail}
    except Exception as exc:
        db.rollback()
        state = _policy_state(db)
        state.checked_at = datetime.now(timezone.utc)
        state.state = "paused_policy_check_failed"
        state.detail = str(exc)[:2000]
        mark_failure(db, POLICY_SOURCE_KEY, exc)
        db.commit()
        return {"ok": False, "paused": True, "reason": str(exc)}
    finally:
        if owned_client:
            client.close()


def parse_sitemap(xml_text: str) -> list[SitemapItem]:
    root = ET.fromstring(xml_text)
    local_name = root.tag.rsplit("}", 1)[-1]
    if local_name not in {"urlset", "sitemapindex"}:
        raise ValueError(f"Unsupported sitemap root: {local_name}")

    items: list[SitemapItem] = []
    if local_name == "sitemapindex":
        for node in root:
            loc = next((x.text for x in node if x.tag.endswith("loc") and x.text), None)
            if loc:
                items.append(SitemapItem(loc.strip(), None))
        return items

    for node in root:
        loc = next((x.text for x in node if x.tag.endswith("loc") and x.text), None)
        if not loc:
            continue
        url = loc.strip()
        parsed = urlparse(url)
        if parsed.hostname not in {"dh.hu", "www.dh.hu"} or "/ingatlan/" not in parsed.path:
            continue
        lastmod = next((x.text for x in node if x.tag.endswith("lastmod") and x.text), None)
        items.append(SitemapItem(url, lastmod.strip() if lastmod else None))
    if not items:
        raise ValueError("Duna House sitemap contained no property URLs")
    return items


def _digits_number(value: str) -> float | None:
    cleaned = value.replace("\xa0", " ").replace(".", " ").replace(",", ".")
    match = re.search(r"\d[\d ]*(?:\.\d+)?", cleaned)
    if not match:
        return None
    return float(match.group(0).replace(" ", ""))


def _json_ld_candidates(soup: BeautifulSoup) -> list[dict]:
    output: list[dict] = []
    for node in soup.select('script[type="application/ld+json"]'):
        try:
            value = json.loads(node.string or node.get_text())
        except (json.JSONDecodeError, TypeError):
            continue
        stack = value if isinstance(value, list) else [value]
        for item in stack:
            if isinstance(item, dict):
                graph = item.get("@graph")
                if isinstance(graph, list):
                    output.extend(x for x in graph if isinstance(x, dict))
                output.append(item)
    return output


def _label_value(text: str, labels: tuple[str, ...]) -> str | None:
    for label in labels:
        match = re.search(rf"{re.escape(label)}\s*:?\s*([^|\n]{{1,120}})", text, re.IGNORECASE)
        if match:
            value = _normalize_space(match.group(1))
            if value:
                return value
    return None


def _extract_price_area_rooms(soup: BeautifulSoup, text: str) -> tuple[float | None, float | None, float | None]:
    price = area = rooms = None
    for data in _json_ld_candidates(soup):
        offers = data.get("offers")
        if isinstance(offers, dict) and str(offers.get("priceCurrency", "")).upper() == "HUF":
            price = _digits_number(str(offers.get("price", ""))) or price
        floor_size = data.get("floorSize")
        if isinstance(floor_size, dict):
            area = _digits_number(str(floor_size.get("value", ""))) or area
        elif floor_size:
            area = _digits_number(str(floor_size)) or area
        rooms_value = data.get("numberOfRooms")
        if rooms_value is not None:
            rooms = _digits_number(str(rooms_value)) or rooms

    if price is None:
        match = re.search(r"([\d\s.,]+)\s*Ft\b", text)
        price = _digits_number(match.group(1)) if match else None
    if area is None:
        matches = re.findall(r"([\d\s.,]+)\s*m(?:²|2)\b", text, re.IGNORECASE)
        candidates = [x for x in (_digits_number(v) for v in matches) if x and 8 <= x <= 5000]
        area = candidates[0] if candidates else None
    if rooms is None:
        match = re.search(r"([\d.,]+)\s*(?:szoba|room)", text, re.IGNORECASE)
        rooms = _digits_number(match.group(1)) if match else None
    return price, area, rooms


def parse_listing_page(url: str, html: str) -> ParsedListing:
    soup = BeautifulSoup(html, "html.parser")
    text = _normalize_space(soup.get_text(" | ", strip=True))
    path = urlparse(url).path
    match = re.search(r"/ingatlan/([^/]+)", path)
    if not match:
        raise ValueError("Duna House listing URL has no stable identifier")
    external_id = match.group(1)

    price, area, rooms = _extract_price_area_rooms(soup, text)
    if price is None or area is None:
        raise ValueError("Listing price or floor area missing")

    postal_match = re.search(r"\b(1\d{3}|[2-9]\d{3})\b", text)
    postal_code = postal_match.group(1) if postal_match else None
    district = None
    district_match = re.search(r"Budapest\s*(?:[,|]\s*)?(\d{1,2})\.?(?:\s*kerület)?", text, re.IGNORECASE)
    if district_match:
        candidate = int(district_match.group(1))
        if 1 <= candidate <= 23:
            district = candidate
    if district is None and postal_code and postal_code.startswith("1"):
        # Budapest postcodes are 1Dxx; D is the district for 01-09, while 10-23 need text.
        candidate = int(postal_code[1:3])
        if 1 <= candidate <= 23:
            district = candidate

    city = "Budapest" if district else None
    if city is None and postal_code:
        city_match = re.search(rf"{postal_code}\s+([^|,]{{2,60}})", text)
        if city_match:
            city = _normalize_space(city_match.group(1))

    lower = text.lower()
    property_type = "house" if any(token in lower for token in ("eladó ház", "családi ház")) else "apartment"
    market_segment = "new" if any(token in lower for token in ("újépítésű", "új építésű")) else "second_hand"
    building_type = _label_value(text, ("Épület szerkezete", "Építés módja", "Szerkezet"))
    if building_type and "panel" in building_type.lower():
        market_class = "panel"
    elif property_type == "house":
        market_class = "family_house"
    else:
        market_class = "condominium"

    year_text = _label_value(text, ("Építés éve", "Építési év"))
    year_value = int(year_text) if year_text and re.fullmatch(r"(?:18|19|20)\d{2}", year_text.strip()) else None
    status_label = "price_drop" if "áresés" in lower or "árcsökkent" in lower else None

    return ParsedListing(
        external_id=external_id,
        source_url=url,
        price_huf=price,
        area_m2=area,
        rooms=rooms,
        postal_code=postal_code,
        city=city,
        district=district,
        property_type=property_type,
        market_class=market_class,
        market_segment=market_segment,
        status_label=status_label,
        building_type=building_type,
        condition=_label_value(text, ("Ingatlan állapota", "Állapot")),
        construction_year=year_value,
        floor=_label_value(text, ("Emelet",)),
        lift=_label_value(text, ("Lift",)),
        balcony=_label_value(text, ("Erkély", "Terasz")),
        view=_label_value(text, ("Kilátás",)),
        orientation=_label_value(text, ("Tájolás",)),
        heating=_label_value(text, ("Fűtés",)),
        energy_rating=_label_value(text, ("Energetikai besorolás", "Energetika")),
    )


def validate_listing(item: ParsedListing) -> tuple[bool, str | None]:
    if not 1_000_000 <= item.price_huf <= 5_000_000_000:
        return False, "price outside safety range"
    if not 8 <= item.area_m2 <= 5000:
        return False, "floor area outside safety range"
    if not 50_000 <= item.price_huf_m2 <= 15_000_000:
        return False, "price per m² outside safety range"
    if item.rooms is not None and not 0.5 <= item.rooms <= 50:
        return False, "room count outside safety range"
    return True, None


def _signature(item: ParsedListing) -> str:
    payload = (
        item.external_id,
        round(item.price_huf),
        round(item.area_m2, 2),
        item.rooms,
        item.area_code,
        item.market_segment,
        item.market_class,
        item.status_label,
    )
    return _sha(json.dumps(payload, ensure_ascii=False))


def upsert_listing(db: Session, item: ParsedListing, *, sitemap_lastmod: str | None = None) -> ObservedListing:
    now = datetime.now(timezone.utc)
    usable, reason = validate_listing(item)
    row = db.scalar(
        select(ObservedListing).where(
            ObservedListing.provider_key == PROVIDER_KEY,
            ObservedListing.external_id == item.external_id,
        )
    )
    sig = _signature(item)
    if row is None:
        row = ObservedListing(
            provider_key=PROVIDER_KEY,
            external_id=item.external_id,
            source_url=item.source_url,
            area_code=item.area_code,
            city=item.city,
            district=item.district,
            postal_code=item.postal_code,
            property_type=item.property_type,
            market_class=item.market_class,
            market_segment=item.market_segment,
            status_label=item.status_label,
            first_seen_at=now,
            last_seen_at=now,
            last_fetched_at=now,
            active=True,
            sitemap_miss_count=0,
            sitemap_lastmod=sitemap_lastmod,
            first_price_huf=item.price_huf,
            price_huf=item.price_huf,
            area_m2=item.area_m2,
            rooms=item.rooms,
            price_huf_m2=item.price_huf_m2,
            building_type=item.building_type,
            condition=item.condition,
            construction_year=item.construction_year,
            floor=item.floor,
            lift=item.lift,
            balcony=item.balcony,
            view=item.view,
            orientation=item.orientation,
            heating=item.heating,
            energy_rating=item.energy_rating,
            quality_state="usable" if usable else "excluded",
            quality_reason=reason,
            content_signature=sig,
        )
        db.add(row)
        db.flush()
    else:
        row.source_url = item.source_url
        row.area_code = item.area_code
        row.city = item.city
        row.district = item.district
        row.postal_code = item.postal_code
        row.property_type = item.property_type
        row.market_class = item.market_class
        row.market_segment = item.market_segment
        row.status_label = item.status_label
        row.last_seen_at = now
        row.last_fetched_at = now
        row.active = True
        row.inactive_at = None
        row.sitemap_miss_count = 0
        row.sitemap_lastmod = sitemap_lastmod
        row.price_huf = item.price_huf
        row.area_m2 = item.area_m2
        row.rooms = item.rooms
        row.price_huf_m2 = item.price_huf_m2
        row.building_type = item.building_type
        row.condition = item.condition
        row.construction_year = item.construction_year
        row.floor = item.floor
        row.lift = item.lift
        row.balcony = item.balcony
        row.view = item.view
        row.orientation = item.orientation
        row.heating = item.heating
        row.energy_rating = item.energy_rating
        row.quality_state = "usable" if usable else "excluded"
        row.quality_reason = reason
        row.content_signature = sig

    snapshot = db.scalar(
        select(ListingSnapshot).where(
            ListingSnapshot.listing_id == row.id,
            ListingSnapshot.observation_date == date.today(),
        )
    )
    if snapshot is None:
        db.add(
            ListingSnapshot(
                listing_id=row.id,
                observation_date=date.today(),
                observed_at=now,
                price_huf=item.price_huf,
                area_m2=item.area_m2,
                rooms=item.rooms,
                price_huf_m2=item.price_huf_m2,
                status_label=item.status_label,
                content_signature=sig,
            )
        )
    else:
        snapshot.observed_at = now
        snapshot.price_huf = item.price_huf
        snapshot.area_m2 = item.area_m2
        snapshot.rooms = item.rooms
        snapshot.price_huf_m2 = item.price_huf_m2
        snapshot.status_label = item.status_label
        snapshot.content_signature = sig
    return row


def _external_id(url: str) -> str | None:
    match = re.search(r"/ingatlan/([^/]+)", urlparse(url).path)
    return match.group(1) if match else None


def collect_duna_house(db: Session, *, contract_only: bool = False) -> dict:
    settings = get_settings()
    if not settings.duna_house_enabled:
        return {"ok": True, "disabled": True}

    client = httpx.Client(
        timeout=settings.http_timeout_seconds,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT, "Accept-Language": "hu-HU,hu;q=0.9,en;q=0.5"},
    )
    try:
        policy = check_provider_policy(db, client)
        if not policy.get("ok"):
            return {"ok": False, "paused": True, "policy": policy}

        sitemap_response = request_with_retry_client(client, "GET", settings.duna_house_sitemap_url)
        sitemap_items = parse_sitemap(sitemap_response.text)
        if contract_only:
            sitemap_items = sitemap_items[:1]

        existing = {
            row.external_id: row
            for row in db.scalars(
                select(ObservedListing).where(ObservedListing.provider_key == PROVIDER_KEY)
            )
        }
        sitemap_ids = {_external_id(item.url) for item in sitemap_items if _external_id(item.url)}

        if not contract_only:
            # Two sitemap misses are required before an observed listing is marked inactive.
            now = datetime.now(timezone.utc)
            for ext_id, row in existing.items():
                if ext_id in sitemap_ids:
                    row.sitemap_miss_count = 0
                    row.last_seen_at = now
                else:
                    row.sitemap_miss_count += 1
                    if row.sitemap_miss_count >= settings.duna_house_inactive_after_misses:
                        row.active = False
                        row.inactive_at = row.inactive_at or now
            db.commit()

        if contract_only:
            selected = sitemap_items
        else:
            unseen = [item for item in sitemap_items if _external_id(item.url) not in existing]
            changed = [
                item
                for item in sitemap_items
                if (row := existing.get(_external_id(item.url) or ""))
                and item.lastmod
                and item.lastmod != row.sitemap_lastmod
            ]
            stale = [
                item
                for item in sitemap_items
                if (row := existing.get(_external_id(item.url) or ""))
                and item not in changed
                and (datetime.now(timezone.utc) - (row.last_fetched_at if row.last_fetched_at.tzinfo else row.last_fetched_at.replace(tzinfo=timezone.utc))).days
                >= 7
            ]
            selected = (unseen + changed + stale)[: settings.duna_house_daily_page_limit]

        fetched = parsed_count = excluded = failed = 0
        for item in selected:
            try:
                response = request_with_retry_client(client, "GET", item.url)
                parsed = parse_listing_page(str(response.url), response.text)
                row = upsert_listing(db, parsed, sitemap_lastmod=item.lastmod)
                fetched += 1
                parsed_count += 1
                excluded += int(row.quality_state != "usable")
                db.commit()
            except Exception:
                db.rollback()
                failed += 1
            if not contract_only and settings.duna_house_request_delay_seconds > 0:
                time.sleep(settings.duna_house_request_delay_seconds)

        if not contract_only and selected and parsed_count == 0:
            raise ValueError("Duna House collector could not parse any selected property page")
        if contract_only and parsed_count != 1:
            raise ValueError("Duna House live contract could not parse the sampled property page")

        mark_success(
            db,
            SOURCE_KEY,
            f"sitemap={len(sitemap_items)} selected={len(selected)} parsed={parsed_count} excluded={excluded}",
        )
        db.commit()
        return {
            "ok": True,
            "policy": policy,
            "sitemap": len(sitemap_items),
            "selected": len(selected),
            "fetched": fetched,
            "parsed": parsed_count,
            "excluded": excluded,
            "failed": failed,
            "contract_only": contract_only,
        }
    except Exception as exc:
        db.rollback()
        mark_failure(db, SOURCE_KEY, exc)
        db.commit()
        return {"ok": False, "error": str(exc)}
    finally:
        client.close()
