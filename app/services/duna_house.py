from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from statistics import mean, median
from urllib import robotparser
from urllib.parse import urlparse, urlunparse
from xml.etree import ElementTree as ET

from bs4 import BeautifulSoup
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import (
    AskingMarketSnapshot,
    ListingSnapshot,
    ObservedListing,
    ObservedListingAttribute,
    ObservedListingPresence,
    ProviderPolicyState,
)
from app.services.http import request_with_retry
from app.services.source_health import mark_failure, mark_success

DH_SOURCE_KEY = "duna_house_observed"
DH_POLICY_SOURCE_KEY = "duna_house_policy"
DH_POLICY_REVIEWED_ON = date(2026, 8, 13)
DH_USER_AGENT = "RealEstateWatch/0.2 (+https://github.com/ArrowSK/real-estate-watch)"

# These patterns are deliberately narrow. Their presence is not interpreted legally; it is a
# safety trigger telling the collector that the reviewed access assumptions may have changed.
POLICY_STOP_PATTERNS = (
    r"screen\s*scrap",
    r"scrap(?:ing|er)",
    r"automatiz[aá]lt\s+adatgy[uű]jt",
    r"automatiz[aá]lt.{0,40}let[oö]lt",
    r"robot.{0,50}tilos",
    r"adatb[aá]zis.{0,80}(?:m[aá]sol|kim[aá]sol).{0,40}tilos",
)


@dataclass(frozen=True)
class SitemapEntry:
    url: str
    lastmod: datetime | None = None


@dataclass(frozen=True)
class ListingFacts:
    external_id: str
    listing_url: str
    asking_price_huf: float
    floor_area_m2: float
    rooms: float | None
    postcode: str | None
    locality: str | None
    area_code: str
    property_type: str
    market_segment: str
    status_label: str | None = None
    building_type: str | None = None
    condition: str | None = None
    construction_year: int | None = None
    floor: str | None = None
    lift: str | None = None
    balcony: str | None = None
    view: str | None = None
    orientation: str | None = None
    heating: str | None = None
    energy_rating: str | None = None

    @property
    def price_huf_m2(self) -> float:
        return self.asking_price_huf / self.floor_area_m2


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def canonical_url(url: str) -> str:
    parsed = urlparse(url.strip())
    host = parsed.netloc.lower().removeprefix("www.")
    path = re.sub(r"/+", "/", parsed.path).rstrip("/") or "/"
    return urlunparse(("https", host, path, "", "", ""))


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _clean_legal_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    for selector in ("header", "footer", "nav"):
        for tag in soup.select(selector):
            tag.decompose()
    main = soup.find("main") or soup.find("article") or soup.body or soup
    return re.sub(r"\s+", " ", main.get_text(" ", strip=True)).strip()


def _robots_contract(robots_text: str, sitemap_url: str) -> tuple[bool, list[str]]:
    parser = robotparser.RobotFileParser()
    parser.parse(robots_text.splitlines())
    allowed = parser.can_fetch(DH_USER_AGENT, "https://dh.hu/elado-ingatlan/lakas-haz")
    normalized_lines = [line.strip() for line in robots_text.splitlines()]
    sitemaps = [
        line.split(":", 1)[1].strip()
        for line in normalized_lines
        if line.lower().startswith("sitemap:")
    ]
    normalized = {canonical_url(item) for item in sitemaps}
    return allowed and canonical_url(sitemap_url) in normalized, sitemaps


def check_dh_policy(db: Session) -> dict:
    settings = get_settings()
    now = _utcnow()
    state = db.scalar(
        select(ProviderPolicyState).where(ProviderPolicyState.source_key == DH_SOURCE_KEY)
    )

    if not settings.dh_enabled:
        return {"ok": False, "paused": True, "reason": "Duna House provider disabled by configuration"}

    if date.today() > DH_POLICY_REVIEWED_ON + timedelta(days=settings.dh_policy_review_max_age_days):
        detail = (
            f"Policy review expired; code review date {DH_POLICY_REVIEWED_ON.isoformat()} is older "
            f"than {settings.dh_policy_review_max_age_days} days"
        )
        if state is None:
            state = ProviderPolicyState(source_key=DH_SOURCE_KEY)
            db.add(state)
        state.status = "review_expired"
        state.reviewed_on = DH_POLICY_REVIEWED_ON
        state.last_checked_at = now
        state.detail = detail
        db.commit()
        mark_failure(db, DH_POLICY_SOURCE_KEY, RuntimeError(detail))
        db.commit()
        return {"ok": False, "paused": True, "reason": detail}

    try:
        robots_response = request_with_retry(
            "GET",
            settings.dh_robots_url,
            timeout=settings.http_timeout_seconds,
            headers={"User-Agent": DH_USER_AGENT},
        )
        legal_response = request_with_retry(
            "GET",
            settings.dh_legal_url,
            timeout=settings.http_timeout_seconds,
            headers={"User-Agent": DH_USER_AGENT},
        )
        robots_text = robots_response.text.strip()
        allowed, sitemaps = _robots_contract(robots_text, settings.dh_sitemap_url)
        if not allowed:
            raise RuntimeError("robots.txt no longer allows the reviewed property-discovery path")

        legal_text = _clean_legal_text(legal_response.text)
        if len(legal_text) < 1500:
            raise RuntimeError("Duna House legal/policy page is unexpectedly short")
        lower_legal = legal_text.casefold()
        stop_matches = [pattern for pattern in POLICY_STOP_PATTERNS if re.search(pattern, lower_legal)]
        if stop_matches:
            raise RuntimeError("Policy page contains a new automated-access stop pattern")

        robots_hash = _hash_text(re.sub(r"\s+", " ", robots_text).strip())
        legal_hash = _hash_text(legal_text)
        if state is None:
            state = ProviderPolicyState(
                source_key=DH_SOURCE_KEY,
                status="experimental_allowed",
                reviewed_on=DH_POLICY_REVIEWED_ON,
                robots_hash=robots_hash,
                legal_hash=legal_hash,
                last_checked_at=now,
                detail="Initial policy fingerprint recorded after the reviewed contract checks passed",
            )
            db.add(state)
            db.commit()
        elif state.robots_hash != robots_hash or state.legal_hash != legal_hash:
            if state.reviewed_on and state.reviewed_on < DH_POLICY_REVIEWED_ON:
                state.status = "experimental_allowed"
                state.reviewed_on = DH_POLICY_REVIEWED_ON
                state.robots_hash = robots_hash
                state.legal_hash = legal_hash
                state.last_checked_at = now
                state.changed_at = now
                state.detail = "Changed source policy accepted by a newer code review date"
                db.commit()
            else:
                state.status = "policy_changed"
                state.last_checked_at = now
                state.changed_at = now
                state.detail = "robots.txt or the reviewed policy body changed; collection paused"
                db.commit()
                raise RuntimeError(state.detail)
        else:
            state.status = "experimental_allowed"
            state.reviewed_on = DH_POLICY_REVIEWED_ON
            state.last_checked_at = now
            state.detail = "Reviewed access contract unchanged"
            db.commit()

        mark_success(
            db,
            DH_POLICY_SOURCE_KEY,
            f"reviewed {DH_POLICY_REVIEWED_ON.isoformat()}; {len(sitemaps)} sitemap declarations",
        )
        db.commit()
        return {
            "ok": True,
            "status": state.status,
            "reviewed_on": DH_POLICY_REVIEWED_ON.isoformat(),
            "robots_hash": robots_hash,
            "legal_hash": legal_hash,
            "sitemaps": sitemaps,
        }
    except Exception as exc:
        db.rollback()
        if state is None:
            state = ProviderPolicyState(source_key=DH_SOURCE_KEY)
            db.add(state)
        state.status = "paused"
        state.reviewed_on = DH_POLICY_REVIEWED_ON
        state.last_checked_at = now
        state.detail = str(exc)[:2000]
        db.commit()
        mark_failure(db, DH_POLICY_SOURCE_KEY, exc)
        db.commit()
        return {"ok": False, "paused": True, "reason": str(exc)}


def parse_sitemap(xml_text: str) -> list[SitemapEntry]:
    root = ET.fromstring(xml_text)
    entries: list[SitemapEntry] = []
    for node in root.iter():
        if not node.tag.endswith("url"):
            continue
        loc = next((child.text for child in node if child.tag.endswith("loc") and child.text), None)
        if not loc:
            continue
        lastmod_text = next(
            (child.text for child in node if child.tag.endswith("lastmod") and child.text),
            None,
        )
        lastmod = None
        if lastmod_text:
            cleaned = lastmod_text.strip().replace("Z", "+00:00")
            try:
                lastmod = datetime.fromisoformat(cleaned)
                if lastmod.tzinfo is None:
                    lastmod = lastmod.replace(tzinfo=timezone.utc)
            except ValueError:
                try:
                    lastmod = datetime.combine(
                        date.fromisoformat(cleaned[:10]), datetime.min.time(), tzinfo=timezone.utc
                    )
                except ValueError:
                    lastmod = None
        url = canonical_url(loc)
        if urlparse(url).netloc == "dh.hu":
            entries.append(SitemapEntry(url=url, lastmod=lastmod))
    if not entries:
        raise ValueError("Duna House property sitemap contained no usable URLs")
    return entries


def discover_dh_listings() -> list[SitemapEntry]:
    settings = get_settings()
    response = request_with_retry(
        "GET",
        settings.dh_sitemap_url,
        timeout=settings.http_timeout_seconds,
        headers={"User-Agent": DH_USER_AGENT, "Accept": "application/xml,text/xml,*/*;q=0.5"},
    )
    return parse_sitemap(response.text)


def _external_id_from_url(url: str) -> str | None:
    parts = [part for part in urlparse(url).path.split("/") if part]
    try:
        index = parts.index("ingatlan")
    except ValueError:
        return None
    if index + 1 >= len(parts):
        return None
    candidate = parts[index + 1].upper()
    return candidate if re.fullmatch(r"[A-Z]{1,4}\d{5,8}", candidate) else None


def _extract_external_id(text: str, url: str) -> str | None:
    from_url = _external_id_from_url(url)
    if from_url:
        return from_url
    for candidate in (text, url):
        match = re.search(r"\b[A-Z]{1,4}\d{5,8}\b", candidate, re.IGNORECASE)
        if match:
            return match.group(0).upper()
    return None


def _property_type_from_id(external_id: str) -> str:
    prefix = re.match(r"[A-Z]+", external_id.upper())
    value = prefix.group(0) if prefix else ""
    if value == "LK":
        return "apartment"
    if value in {"HZ", "H"}:
        return "house"
    if value == "PR":
        return "project"
    return "unknown"


def _residential_entries(entries: list[SitemapEntry]) -> list[SitemapEntry]:
    return [
        entry
        for entry in entries
        if (external_id := _external_id_from_url(entry.url))
        and _property_type_from_id(external_id) in {"apartment", "house"}
    ]


def _jsonld_objects(soup: BeautifulSoup) -> list[dict]:
    output: list[dict] = []
    for node in soup.find_all("script", attrs={"type": "application/ld+json"}):
        if not node.string:
            continue
        try:
            parsed = json.loads(node.string)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(parsed, dict):
            graph = parsed.get("@graph")
            if isinstance(graph, list):
                output.extend(item for item in graph if isinstance(item, dict))
            output.append(parsed)
        elif isinstance(parsed, list):
            output.extend(item for item in parsed if isinstance(item, dict))
    return output


def _numeric(value) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, dict):
        value = value.get("value") or value.get("minValue")
    if value is None:
        return None
    match = re.search(r"\d+(?:[.,]\d+)?", str(value).replace("\xa0", " "))
    return float(match.group(0).replace(",", ".")) if match else None


def _price_numeric(value) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if value is None:
        return None
    digits = re.sub(r"[^0-9]", "", str(value))
    return float(digits) if digits else None


def _label_value(text: str, labels: tuple[str, ...]) -> str | None:
    for label in labels:
        match = re.search(rf"{re.escape(label)}\s*:?\s*([^|]{{1,120}})", text, re.IGNORECASE)
        if match:
            value = re.sub(r"\s+", " ", match.group(1)).strip(" :-")
            if value:
                return value[:120]
    return None


def _area_from_postcode(postcode: str | None, locality: str | None) -> str:
    if postcode and re.fullmatch(r"1\d{3}", postcode):
        district = int(postcode[1:3])
        if 1 <= district <= 23:
            return f"BUDAPEST_{district:02d}"
    if locality and "budapest" in locality.casefold():
        match = re.search(r"(?:^|\D)([0-9]{1,2})\.?\s*ker", locality.casefold())
        if match and 1 <= int(match.group(1)) <= 23:
            return f"BUDAPEST_{int(match.group(1)):02d}"
        return "BUDAPEST"
    return "HU"


def _property_type(external_id: str, json_type: str | None, text: str) -> str:
    direct = _property_type_from_id(external_id)
    if direct != "unknown":
        return direct
    probe = f"{json_type or ''} {text[:500]}".casefold()
    if "apartment" in probe or "lakás" in probe:
        return "apartment"
    if "house" in probe or "ház" in probe:
        return "house"
    return "unknown"


def parse_dh_listing(html: str, url: str) -> ListingFacts:
    soup = BeautifulSoup(html, "html.parser")
    labelled_visible = re.sub(r"\s+", " ", soup.get_text(" | ", strip=True))
    visible = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
    title = " ".join(
        x for x in [soup.title.string.strip() if soup.title and soup.title.string else "", visible[:1200]] if x
    )
    objects = _jsonld_objects(soup)

    external_id = _extract_external_id(title, url)
    price = None
    area = None
    rooms = None
    postcode = None
    locality = None
    json_type = None
    market_segment = "second_hand"

    for item in objects:
        json_type = str(item.get("@type") or json_type or "")
        offers = item.get("offers")
        offer_items = offers if isinstance(offers, list) else [offers]
        for offer in offer_items:
            if isinstance(offer, dict):
                currency = str(offer.get("priceCurrency") or "HUF").upper()
                if currency in {"HUF", "FT"} and price is None:
                    price = _price_numeric(offer.get("price"))
        if area is None:
            area = _numeric(item.get("floorSize") or item.get("size") or item.get("area"))
        if rooms is None:
            rooms = _numeric(item.get("numberOfRooms") or item.get("numberOfBedrooms"))
        address = item.get("address")
        if isinstance(address, dict):
            postcode = postcode or str(address.get("postalCode") or "").strip() or None
            locality = locality or str(address.get("addressLocality") or "").strip() or None
        if item.get("isNew") is True:
            market_segment = "new"

    if price is None:
        matches = re.findall(r"(?<!\d)(\d[\d\s\u00a0.]{4,})\s*(?:Ft|HUF)\b", visible, re.I)
        plausible = [_price_numeric(value) for value in matches]
        price = next((value for value in plausible if value and 1_000_000 <= value <= 5_000_000_000), None)
    if area is None:
        match = re.search(r"(?<!\d)(\d{1,4}(?:[.,]\d+)?)\s*m[²2]\b", visible, re.I)
        area = float(match.group(1).replace(",", ".")) if match else None
    if rooms is None:
        match = re.search(r"(?<!\d)(\d{1,2}(?:[.,]\d+)?)\s*szoba\b", visible, re.I)
        rooms = float(match.group(1).replace(",", ".")) if match else None
    if postcode is None:
        match = re.search(r"\b(\d{4})\s+(?:Budapest|[A-ZÁÉÍÓÖŐÚÜŰ])", visible)
        postcode = match.group(1) if match else None
    if locality is None:
        match = re.search(r"\b\d{4}\s+(Budapest(?:\s+\d{1,2}\.?\s*kerület)?)", visible, re.I)
        locality = match.group(1) if match else None
    if "újépítésű" in visible.casefold() or (external_id or "").startswith("PR"):
        market_segment = "new"

    building_type = _label_value(labelled_visible, ("Épület szerkezete", "Építés módja", "Szerkezet"))
    condition = _label_value(labelled_visible, ("Ingatlan állapota", "Állapot"))
    year_text = _label_value(labelled_visible, ("Építés éve", "Építési év"))
    construction_year = (
        int(year_text)
        if year_text and re.fullmatch(r"(?:18|19|20)\d{2}", year_text.strip())
        else None
    )
    status_label = (
        "price_drop"
        if "áresés" in visible.casefold() or "árcsökkent" in visible.casefold()
        else None
    )

    if not external_id:
        raise ValueError("Duna House listing reference number not found")
    property_type = _property_type(external_id, json_type, title)
    if property_type not in {"apartment", "house"}:
        raise ValueError(f"Duna House reference {external_id} is outside the residential observer scope")
    if price is None or not 1_000_000 <= price <= 5_000_000_000:
        raise ValueError("Duna House asking price missing or outside safety range")
    if area is None or not 10 <= area <= 3000:
        raise ValueError("Duna House floor area missing or outside safety range")
    price_m2 = price / area
    if not 50_000 <= price_m2 <= 25_000_000:
        raise ValueError("Duna House price per square metre outside safety range")

    return ListingFacts(
        external_id=external_id,
        listing_url=canonical_url(url),
        asking_price_huf=price,
        floor_area_m2=area,
        rooms=rooms,
        postcode=postcode,
        locality=locality,
        area_code=_area_from_postcode(postcode, locality),
        property_type=property_type,
        market_segment=market_segment,
        status_label=status_label,
        building_type=building_type,
        condition=condition,
        construction_year=construction_year,
        floor=_label_value(labelled_visible, ("Emelet",)),
        lift=_label_value(labelled_visible, ("Lift",)),
        balcony=_label_value(labelled_visible, ("Erkély", "Terasz")),
        view=_label_value(labelled_visible, ("Kilátás",)),
        orientation=_label_value(labelled_visible, ("Tájolás",)),
        heating=_label_value(labelled_visible, ("Fűtés",)),
        energy_rating=_label_value(labelled_visible, ("Energetikai besorolás", "Energetika")),
    )


def probe_dh(db: Session) -> dict:
    policy = check_dh_policy(db)
    if not policy.get("ok"):
        return {"ok": False, "policy": policy}
    all_entries = discover_dh_listings()
    entries = _residential_entries(all_entries)
    if not entries:
        raise ValueError("Duna House sitemap contained no residential LK/HZ property references")
    ranked = sorted(
        entries,
        key=lambda item: item.lastmod or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    failures: list[str] = []
    for entry in ranked[:8]:
        try:
            response = request_with_retry(
                "GET",
                entry.url,
                timeout=get_settings().http_timeout_seconds,
                attempts=2,
                headers={"User-Agent": DH_USER_AGENT},
            )
            facts = parse_dh_listing(response.text, entry.url)
            return {
                "ok": True,
                "policy": {k: v for k, v in policy.items() if k not in {"robots_hash", "legal_hash"}},
                "sitemap_entries": len(all_entries),
                "residential_entries": len(entries),
                "sample": {
                    "external_id": facts.external_id,
                    "area_code": facts.area_code,
                    "property_type": facts.property_type,
                    "market_segment": facts.market_segment,
                    "has_price": facts.asking_price_huf > 0,
                    "has_area": facts.floor_area_m2 > 0,
                    "has_rooms": facts.rooms is not None,
                },
            }
        except Exception as exc:
            failures.append(str(exc)[:180])
    raise ValueError(
        "Duna House residential contract probe could not parse any of eight recent pages: "
        + " | ".join(failures)
    )


def _presence_row(db: Session, listing_id: int) -> ObservedListingPresence:
    row = db.get(ObservedListingPresence, listing_id)
    if row is None:
        row = ObservedListingPresence(listing_id=listing_id)
        db.add(row)
        db.flush()
    return row


def update_presence_from_sitemap(
    db: Session,
    existing: list[ObservedListing],
    discovered_urls: set[str],
    *,
    now: datetime | None = None,
) -> dict[str, int]:
    settings = get_settings()
    now = now or _utcnow()
    marked_inactive = 0
    pending_missing = 0
    recovered = 0
    for item in existing:
        presence = _presence_row(db, item.id)
        if canonical_url(item.listing_url) in discovered_urls:
            recovered += int(not item.active or presence.sitemap_miss_count > 0)
            item.active = True
            presence.sitemap_miss_count = 0
            presence.missing_since_at = None
            presence.inactive_at = None
            presence.last_sitemap_seen_at = now
            continue
        presence.sitemap_miss_count += 1
        presence.missing_since_at = presence.missing_since_at or now
        if presence.sitemap_miss_count >= max(1, settings.dh_inactive_after_misses):
            if item.active:
                marked_inactive += 1
            item.active = False
            presence.inactive_at = presence.inactive_at or now
        else:
            pending_missing += 1
    db.commit()
    return {
        "marked_inactive": marked_inactive,
        "pending_missing": pending_missing,
        "recovered": recovered,
    }


def _upsert_listing_attributes(
    db: Session,
    item: ObservedListing,
    facts: ListingFacts,
    now: datetime,
) -> None:
    row = db.get(ObservedListingAttribute, item.id)
    if row is None:
        row = ObservedListingAttribute(listing_id=item.id)
        db.add(row)
    for field in (
        "status_label",
        "building_type",
        "condition",
        "construction_year",
        "floor",
        "lift",
        "balcony",
        "view",
        "orientation",
        "heating",
        "energy_rating",
    ):
        setattr(row, field, getattr(facts, field))
    row.updated_at = now


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("Cannot calculate percentile of empty values")
    position = (len(ordered) - 1) * fraction
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    weight = position - low
    return ordered[low] * (1 - weight) + ordered[high] * weight


def _latest_snapshots(db: Session) -> tuple[dict[int, ListingSnapshot], dict[int, ListingSnapshot | None]]:
    snapshots = list(
        db.scalars(
            select(ListingSnapshot).order_by(
                ListingSnapshot.listing_id,
                ListingSnapshot.snapshot_date.desc(),
            )
        )
    )
    latest: dict[int, ListingSnapshot] = {}
    previous: dict[int, ListingSnapshot | None] = {}
    for snap in snapshots:
        if snap.listing_id not in latest:
            latest[snap.listing_id] = snap
            previous[snap.listing_id] = None
        elif previous[snap.listing_id] is None:
            previous[snap.listing_id] = snap
    return latest, previous


def rebuild_asking_aggregates(db: Session, discovery_count: int | None = None) -> int:
    settings = get_settings()
    today = date.today()
    listings = list(
        db.scalars(
            select(ObservedListing).where(
                ObservedListing.source_key == DH_SOURCE_KEY,
                ObservedListing.active.is_(True),
                ObservedListing.quality_state == "usable",
                ObservedListing.property_type.in_(("apartment", "house")),
            )
        )
    )
    latest, previous = _latest_snapshots(db)
    source_active_count = len([item for item in listings if item.id in latest])
    coverage = source_active_count / discovery_count if discovery_count and discovery_count > 0 else None

    buckets: dict[tuple[str, str, str], list[tuple[ObservedListing, ListingSnapshot]]] = {}
    for item in listings:
        snap = latest.get(item.id)
        if snap is None:
            continue
        areas = {item.area_code}
        if item.area_code.startswith("BUDAPEST_"):
            areas.add("BUDAPEST")
        if item.postcode:
            areas.add(f"POSTCODE_{item.postcode}")
        types = {item.property_type, "all"}
        for area_code in areas:
            for property_type in types:
                buckets.setdefault((area_code, property_type, item.market_segment), []).append((item, snap))

    written = 0
    for (area_code, property_type, market_segment), rows in buckets.items():
        values = [snap.price_huf_m2 for _, snap in rows]
        if len(values) < settings.dh_min_aggregate_sample:
            continue
        cuts: list[float] = []
        for item, snap in rows:
            old = previous.get(item.id)
            if old and old.asking_price_huf > snap.asking_price_huf:
                cuts.append((snap.asking_price_huf / old.asking_price_huf - 1) * 100)
        new_count = sum(1 for item, _ in rows if item.first_seen_at.date() == today)
        confidence = "low"
        if len(values) >= 30 and (coverage is None or coverage >= 0.05):
            confidence = "medium"
        if len(values) >= 100 and coverage is not None and coverage >= 0.20:
            confidence = "high"

        aggregate = db.scalar(
            select(AskingMarketSnapshot).where(
                AskingMarketSnapshot.source_key == DH_SOURCE_KEY,
                AskingMarketSnapshot.snapshot_date == today,
                AskingMarketSnapshot.area_code == area_code,
                AskingMarketSnapshot.property_type == property_type,
                AskingMarketSnapshot.market_segment == market_segment,
            )
        )
        payload = {
            "sample_size": len(values),
            "median_huf_m2": median(values),
            "mean_huf_m2": mean(values),
            "p25_huf_m2": _percentile(values, 0.25),
            "p75_huf_m2": _percentile(values, 0.75),
            "new_listing_count": new_count,
            "price_cut_count": len(cuts),
            "median_price_cut_pct": median(cuts) if cuts else None,
            "observed_active_count": source_active_count,
            "discovery_count": discovery_count,
            "coverage_ratio": coverage,
            "confidence": confidence,
            "status": "observed_subset",
        }
        if aggregate is None:
            aggregate = AskingMarketSnapshot(
                source_key=DH_SOURCE_KEY,
                snapshot_date=today,
                area_code=area_code,
                property_type=property_type,
                market_segment=market_segment,
                **payload,
            )
            db.add(aggregate)
        else:
            for key, value in payload.items():
                setattr(aggregate, key, value)
        written += 1
    db.commit()
    return written


def collect_dh(db: Session, *, limit: int | None = None) -> dict:
    settings = get_settings()
    policy = check_dh_policy(db)
    if not policy.get("ok"):
        return {"ok": False, "paused": True, "policy": policy}

    try:
        all_entries = discover_dh_listings()
        entries = _residential_entries(all_entries)
        if not entries:
            raise ValueError("Duna House sitemap contained no residential LK/HZ property references")
        discovered_urls = {entry.url for entry in entries}
        existing = list(db.scalars(select(ObservedListing).where(ObservedListing.source_key == DH_SOURCE_KEY)))
        by_url = {canonical_url(item.listing_url): item for item in existing}

        presence_summary = update_presence_from_sitemap(db, existing, discovered_urls)
        removed = presence_summary["marked_inactive"]

        def priority(entry: SitemapEntry) -> tuple[int, float]:
            item = by_url.get(entry.url)
            if item is None:
                return (0, -(entry.lastmod.timestamp() if entry.lastmod else 0))
            if entry.lastmod and (item.source_lastmod_at is None or entry.lastmod > item.source_lastmod_at):
                return (1, -entry.lastmod.timestamp())
            return (2, item.last_seen_at.timestamp())

        candidates = sorted(entries, key=priority)
        run_limit = max(1, limit or settings.dh_max_listings_per_run)
        now = _utcnow()
        today = now.date()
        imported = 0
        updated_today = 0
        errors = 0

        for index, entry in enumerate(candidates[:run_limit]):
            if index and settings.dh_request_delay_seconds > 0:
                time.sleep(settings.dh_request_delay_seconds)
            try:
                response = request_with_retry(
                    "GET",
                    entry.url,
                    timeout=settings.http_timeout_seconds,
                    attempts=2,
                    headers={"User-Agent": DH_USER_AGENT},
                )
                facts = parse_dh_listing(response.text, entry.url)
            except Exception:
                errors += 1
                continue

            item = db.scalar(
                select(ObservedListing).where(
                    ObservedListing.source_key == DH_SOURCE_KEY,
                    ObservedListing.external_id == facts.external_id,
                )
            )
            if item is None:
                item = ObservedListing(
                    source_key=DH_SOURCE_KEY,
                    external_id=facts.external_id,
                    listing_url=facts.listing_url,
                    area_code=facts.area_code,
                    locality=facts.locality,
                    postcode=facts.postcode,
                    property_type=facts.property_type,
                    market_segment=facts.market_segment,
                    rooms=facts.rooms,
                    first_seen_at=now,
                    last_seen_at=now,
                    source_lastmod_at=entry.lastmod,
                    active=True,
                    quality_state="usable",
                )
                db.add(item)
                db.flush()
            else:
                item.listing_url = facts.listing_url
                item.area_code = facts.area_code
                item.locality = facts.locality
                item.postcode = facts.postcode
                item.property_type = facts.property_type
                item.market_segment = facts.market_segment
                item.rooms = facts.rooms
                item.last_seen_at = now
                item.source_lastmod_at = entry.lastmod or item.source_lastmod_at
                item.active = True
                item.quality_state = "usable"

            presence = _presence_row(db, item.id)
            presence.sitemap_miss_count = 0
            presence.missing_since_at = None
            presence.inactive_at = None
            presence.last_sitemap_seen_at = now
            _upsert_listing_attributes(db, item, facts, now)

            snapshot = db.scalar(
                select(ListingSnapshot).where(
                    ListingSnapshot.listing_id == item.id,
                    ListingSnapshot.snapshot_date == today,
                )
            )
            if snapshot is None:
                db.add(
                    ListingSnapshot(
                        listing_id=item.id,
                        snapshot_date=today,
                        observed_at=now,
                        asking_price_huf=facts.asking_price_huf,
                        floor_area_m2=facts.floor_area_m2,
                        price_huf_m2=facts.price_huf_m2,
                        rooms=facts.rooms,
                    )
                )
                imported += 1
            else:
                snapshot.observed_at = now
                snapshot.asking_price_huf = facts.asking_price_huf
                snapshot.floor_area_m2 = facts.floor_area_m2
                snapshot.price_huf_m2 = facts.price_huf_m2
                snapshot.rooms = facts.rooms
                updated_today += 1
            db.commit()

        aggregates = rebuild_asking_aggregates(db, discovery_count=len(entries))
        if imported == 0 and updated_today == 0 and errors >= min(run_limit, len(candidates)):
            raise RuntimeError("No residential Duna House listing page could be parsed in this run")
        mark_success(
            db,
            DH_SOURCE_KEY,
            (
                f"{len(entries)} residential URLs from {len(all_entries)} sitemap entries; "
                f"{imported} new daily snapshots; {errors} parse/fetch errors"
            ),
        )
        db.commit()
        return {
            "ok": True,
            "sitemap_discovered": len(all_entries),
            "residential_discovered": len(entries),
            "processed": min(run_limit, len(candidates)),
            "imported": imported,
            "updated_today": updated_today,
            "errors": errors,
            "removed": removed,
            "pending_missing": presence_summary["pending_missing"],
            "recovered": presence_summary["recovered"],
            "aggregates": aggregates,
        }
    except Exception as exc:
        db.rollback()
        mark_failure(db, DH_SOURCE_KEY, exc)
        db.commit()
        return {"ok": False, "error": str(exc)}


def latest_asking_market(
    db: Session,
    area_code: str,
    property_type: str = "all",
    market_segment: str = "second_hand",
) -> AskingMarketSnapshot | None:
    return db.scalar(
        select(AskingMarketSnapshot)
        .where(
            AskingMarketSnapshot.source_key == DH_SOURCE_KEY,
            AskingMarketSnapshot.area_code == area_code,
            AskingMarketSnapshot.property_type == property_type,
            AskingMarketSnapshot.market_segment == market_segment,
        )
        .order_by(AskingMarketSnapshot.snapshot_date.desc())
        .limit(1)
    )


def asking_market_series(
    db: Session,
    area_code: str,
    property_type: str = "all",
    market_segment: str = "second_hand",
) -> list[AskingMarketSnapshot]:
    return list(
        db.scalars(
            select(AskingMarketSnapshot)
            .where(
                AskingMarketSnapshot.source_key == DH_SOURCE_KEY,
                AskingMarketSnapshot.area_code == area_code,
                AskingMarketSnapshot.property_type == property_type,
                AskingMarketSnapshot.market_segment == market_segment,
            )
            .order_by(AskingMarketSnapshot.snapshot_date.asc())
        )
    )
