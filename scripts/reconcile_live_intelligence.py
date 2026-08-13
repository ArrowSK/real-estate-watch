from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text()
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected exactly one match, found {count}: {old[:100]!r}")
    file.write_text(text.replace(old, new, 1))


def append_once(path: str, marker: str, addition: str) -> None:
    file = Path(path)
    text = file.read_text()
    if marker in text:
        return
    file.write_text(text.rstrip() + "\n\n" + addition.strip() + "\n")


# Duna House: retain main's reviewed provider boundary, while carrying over the feature
# branch's useful disappearance tolerance and structured factual fields.
replace_once(
    "app/services/duna_house.py",
    "from app.models import (\n    AskingMarketSnapshot,\n    ListingSnapshot,\n    ObservedListing,\n    ProviderPolicyState,\n)",
    "from app.models import (\n    AskingMarketSnapshot,\n    ListingSnapshot,\n    ObservedListing,\n    ObservedListingAttribute,\n    ObservedListingPresence,\n    ProviderPolicyState,\n)",
)
replace_once(
    "app/services/duna_house.py",
    "    property_type: str\n    market_segment: str\n\n    @property",
    "    property_type: str\n    market_segment: str\n    status_label: str | None = None\n    building_type: str | None = None\n    condition: str | None = None\n    construction_year: int | None = None\n    floor: str | None = None\n    lift: str | None = None\n    balcony: str | None = None\n    view: str | None = None\n    orientation: str | None = None\n    heating: str | None = None\n    energy_rating: str | None = None\n\n    @property",
)
replace_once(
    "app/services/duna_house.py",
    '    soup = BeautifulSoup(html, "html.parser")\n    visible = re.sub(r"\\s+", " ", soup.get_text(" ", strip=True))',
    '    soup = BeautifulSoup(html, "html.parser")\n    labelled_visible = re.sub(r"\\s+", " ", soup.get_text(" | ", strip=True))\n    visible = re.sub(r"\\s+", " ", soup.get_text(" ", strip=True))',
)
replace_once(
    "app/services/duna_house.py",
    "\ndef _area_from_postcode(postcode: str | None, locality: str | None) -> str:",
    """
def _label_value(text: str, labels: tuple[str, ...]) -> str | None:
    for label in labels:
        match = re.search(rf"{re.escape(label)}\s*:?\s*([^|]{{1,120}})", text, re.IGNORECASE)
        if match:
            value = re.sub(r"\s+", " ", match.group(1)).strip(" :-")
            if value:
                return value[:120]
    return None


def _area_from_postcode(postcode: str | None, locality: str | None) -> str:""",
)
replace_once(
    "app/services/duna_house.py",
    '    if "újépítésű" in visible.casefold() or (external_id or "").startswith("PR"):\n        market_segment = "new"\n\n    if not external_id:',
    '''    if "újépítésű" in visible.casefold() or (external_id or "").startswith("PR"):
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

    if not external_id:''',
)
replace_once(
    "app/services/duna_house.py",
    '        property_type=property_type,\n        market_segment=market_segment,\n    )',
    '''        property_type=property_type,
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
    )''',
)
replace_once(
    "app/services/duna_house.py",
    "\ndef _percentile(values: list[float], fraction: float) -> float:",
    '''
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


def _percentile(values: list[float], fraction: float) -> float:''',
)
replace_once(
    "app/services/duna_house.py",
    '        areas = {item.area_code}\n        if item.area_code.startswith("BUDAPEST_"):\n            areas.add("BUDAPEST")',
    '        areas = {item.area_code}\n        if item.area_code.startswith("BUDAPEST_"):\n            areas.add("BUDAPEST")\n        if item.postcode:\n            areas.add(f"POSTCODE_{item.postcode}")',
)
replace_once(
    "app/services/duna_house.py",
    '''        removed = 0
        for item in existing:
            if item.active and canonical_url(item.listing_url) not in discovered_urls:
                item.active = False
                removed += 1
        db.commit()''',
    '''        presence_summary = update_presence_from_sitemap(db, existing, discovered_urls)
        removed = presence_summary["marked_inactive"]''',
)
replace_once(
    "app/services/duna_house.py",
    '''                item.active = True
                item.quality_state = "usable"

            snapshot = db.scalar(''',
    '''                item.active = True
                item.quality_state = "usable"

            presence = _presence_row(db, item.id)
            presence.sitemap_miss_count = 0
            presence.missing_since_at = None
            presence.inactive_at = None
            presence.last_sitemap_seen_at = now
            _upsert_listing_attributes(db, item, facts, now)

            snapshot = db.scalar(''',
)
replace_once(
    "app/services/duna_house.py",
    '            "removed": removed,\n            "aggregates": aggregates,',
    '            "removed": removed,\n            "pending_missing": presence_summary["pending_missing"],\n            "recovered": presence_summary["recovered"],\n            "aggregates": aggregates,',
)

# Web routes: carry over the feature branch's useful Live and Local workspaces while keeping
# main's corrected local-factor methodology.
replace_once(
    "app/main.py",
    "from app.services.analytics import ASKING_PROPERTY_MAP, market_comparison, transaction_nowcast",
    "from app.services.analytics import (\n    ASKING_PROPERTY_MAP,\n    LOCAL_PROPERTY_MAP,\n    market_comparison,\n    transaction_nowcast,\n)",
)
replace_once(
    "app/main.py",
    "from app.services.duna_house import asking_market_series",
    "from app.services.duna_house import DH_SOURCE_KEY, asking_market_series",
)
replace_once(
    "app/main.py",
    "from app.services.ksh_local import streets_for_area\nfrom app.services.market import ensure_seed_market_data, market_series",
    '''from app.services.ksh_local import streets_for_area
from app.services.live_intelligence import (
    live_comparison,
    live_history,
    live_signals,
    local_district_signal,
    local_street_signals,
    local_years,
)
from app.services.market import ensure_seed_market_data, market_series''',
)

live_routes = r'''

@app.get("/live", response_class=HTMLResponse)
def live_market_page(
    request: Request,
    area: str = Query("BUDAPEST"),
    postcode: str = Query(""),
    market: str = Query("second_hand"),
    property_type: str = Query("all"),
    db: Session = Depends(get_db),
):
    language = language_from_request(request)
    provider = HungaryProvider()
    all_areas = provider.areas()
    areas = [
        item
        for item in all_areas
        if item["code"] in {"HU", "BUDAPEST"} or item["code"].startswith("BUDAPEST_")
    ]
    valid_areas = {item["code"] for item in areas}
    selected_area = area if area in valid_areas else "BUDAPEST"
    selected_market = market if market in {"second_hand", "new"} else "second_hand"
    selected_property_type = (
        property_type if property_type in {"all", "apartment", "house"} else "all"
    )

    district_signals = live_signals(
        db,
        area_code=selected_area,
        property_type=selected_property_type,
        market_segment=selected_market,
    )
    valid_postcodes = {value for value, _ in district_signals.postcodes}
    selected_postcode = postcode if postcode in valid_postcodes else ""
    scope_area = f"POSTCODE_{selected_postcode}" if selected_postcode else selected_area
    signals = (
        live_signals(
            db,
            area_code=scope_area,
            property_type=selected_property_type,
            market_segment=selected_market,
        )
        if selected_postcode
        else district_signals
    )
    comparison = live_comparison(
        db,
        area_code=scope_area,
        property_type=selected_property_type,
        market_segment=selected_market,
    )
    history = live_history(
        db,
        area_code=scope_area,
        property_type=selected_property_type,
        market_segment=selected_market,
    )
    policy = db.scalar(
        select(ProviderPolicyState).where(ProviderPolicyState.source_key == DH_SOURCE_KEY)
    )
    area_info = _area_info(areas, selected_area)
    area_name = area_info["name_hu"] if language == "hu" else area_info["name_en"]
    scope_label = f"{selected_postcode} · {area_name}" if selected_postcode else area_name
    return templates.TemplateResponse(
        request,
        "live.html",
        template_context(
            request,
            language,
            areas=areas,
            selected_area=selected_area,
            selected_postcode=selected_postcode,
            postcode_options=district_signals.postcodes,
            selected_market=selected_market,
            selected_property_type=selected_property_type,
            property_types=PROPERTY_TYPES,
            signals=signals,
            comparison=comparison,
            history=history,
            scope_label=scope_label,
            policy_ok=bool(policy and policy.status == "experimental_allowed"),
        ),
    )


@app.get("/local", response_class=HTMLResponse)
def local_market_page(
    request: Request,
    area: str = Query("BUDAPEST_06"),
    property_type: str = Query("apartment"),
    year: int | None = Query(None),
    q: str = Query(""),
    db: Session = Depends(get_db),
):
    language = language_from_request(request)
    provider = HungaryProvider()
    districts = [item for item in provider.areas() if item["code"].startswith("BUDAPEST_")]
    valid_areas = {item["code"] for item in districts}
    selected_area = area if area in valid_areas else "BUDAPEST_06"
    selected_property_type = (
        property_type
        if property_type in {"all", "apartment", "house", "panel"}
        else "apartment"
    )
    source_type = LOCAL_PROPERTY_MAP[selected_property_type]
    years = local_years(db, selected_area)
    selected_year = year if year in years else (years[0] if years else 0)
    search = q.strip()[:80]
    district_signal = (
        local_district_signal(
            db,
            area_code=selected_area,
            property_type=source_type,
            year=selected_year,
        )
        if selected_year
        else None
    )
    street_rows = (
        local_street_signals(
            db,
            area_code=selected_area,
            property_type=source_type,
            year=selected_year,
            search=search,
        )
        if selected_year
        else []
    )
    return templates.TemplateResponse(
        request,
        "local.html",
        template_context(
            request,
            language,
            districts=districts,
            selected_area=selected_area,
            property_types=PROPERTY_TYPES,
            selected_property_type=selected_property_type,
            years=years,
            selected_year=selected_year,
            search=search,
            district_signal=district_signal,
            street_rows=street_rows,
        ),
    )
'''
replace_once(
    "app/main.py",
    '\n\n@app.get("/valuation", response_class=HTMLResponse)',
    live_routes + '\n\n@app.get("/valuation", response_class=HTMLResponse)',
)

# Navigation.
replace_once(
    "app/templates/base.html",
    '''      <a href="/valuation" class="{% if request.url.path == '/valuation' %}active{% endif %}">
        <svg class="icon" aria-hidden="true"><use href="/static/icons.svg#valuation"></use></svg>
        <span>{{ t.valuation }}</span>
      </a>''',
    '''      <a href="/live" class="{% if request.url.path == '/live' %}active{% endif %}">
        <svg class="icon" aria-hidden="true"><use href="/static/icons.svg#asking"></use></svg>
        <span>{{ t.live_market }}</span>
      </a>
      <a href="/local" class="{% if request.url.path == '/local' %}active{% endif %}">
        <svg class="icon" aria-hidden="true"><use href="/static/icons.svg#location"></use></svg>
        <span>{{ t.local_market }}</span>
      </a>
      <a href="/valuation" class="{% if request.url.path == '/valuation' %}active{% endif %}">
        <svg class="icon" aria-hidden="true"><use href="/static/icons.svg#valuation"></use></svg>
        <span>{{ t.valuation }}</span>
      </a>''',
)

# Bilingual copy.
anchor = '        "diagnostics": "Diagnostics",\n'
replace_once(
    "app/i18n.py",
    anchor,
    anchor + '        "live_market": "Live asking",\n        "local_market": "Local evidence",\n',
)
anchor = '        "diagnostics": "Diagnosztika",\n'
replace_once(
    "app/i18n.py",
    anchor,
    anchor + '        "live_market": "Élő kínálat",\n        "local_market": "Helyi adatok",\n',
)

en_tail = '        "asking_market_not_ready": "Observed asking data has not yet reached the minimum publishable sample for this selection.",\n'
en_more = '''        "observed_subset": "Observed source subset",
        "live_title": "What sellers are asking now",
        "live_intro": "A dedicated view of the factual Duna House listings observed by this deployment. It shows source-subset behaviour, not a claim about every active Hungarian listing.",
        "experimental": "EXPERIMENTAL",
        "policy_ok": "Policy guard passed",
        "policy_paused": "Provider paused",
        "postcode": "Postcode",
        "all_postcodes": "All observed postcodes",
        "median_asking": "Median asking price",
        "price_cuts": "Observed price cuts",
        "observed_reductions": "Observed reductions",
        "median_cut": "median cut",
        "new_observations": "New observations",
        "last_7_days": "last 7 days",
        "today": "today",
        "observed_days": "Median observed days",
        "observed_days_note": "Time since this deployment first saw the listing; it is not the portal's original publication age.",
        "observed_history": "Observed asking history",
        "transaction_comparison": "Transaction comparison",
        "asking_gap_note": "The asking/transaction gap compares different populations and is not an expected negotiation discount.",
        "feature_coverage": "Structured factual coverage",
        "listings_with_features": "Listings with ≥1 structured feature",
        "feature_field_coverage": "Feature-field completeness",
        "usable_live_rows": "Usable active observations",
        "feature_privacy_note": "Only short factual attributes are retained: no descriptions, photos or contact details.",
        "source_policy": "Source policy boundary",
        "removed_not_sold": "Removed ≠ sold",
        "removed_not_sold_note": "A listing is marked inactive only after repeated sitemap absence. The app never converts disappearance into a completed sale.",
        "completed_transactions": "completed transaction evidence",
        "local_title": "Street-level evidence without false precision",
        "local_intro": "Inspect KSH annual district and street observations, then express their same-year local factor against the latest Budapest second-hand transaction benchmark.",
        "district": "District",
        "street_search": "Street filter",
        "street_search_placeholder": "e.g. Andrássy",
        "official_local": "Published local mean",
        "local_factor_note": "Published local mean divided by the same-year Budapest all-dwelling mean; applied to the latest Budapest second-hand benchmark.",
        "current_local_estimate": "Current local-factor estimate",
        "street_detail": "Street evidence ledger",
        "street": "Street",
        "no_street_rows": "No published street observations match this selection.",
        "local_method_note": "Street rows are KSH aggregates. Current values are transparent factor-based nowcasts, not observed current sale prices.",
        "local_source_note": "KSH Ingatlanadattár contains annual aggregate completed-transaction statistics derived from transaction records; missing cells stay missing.",
        "precision": "Precision discipline",
        "local_precision_note": "Low-count or dispersed street samples are labelled with lower confidence rather than being presented with equal authority.",
'''
replace_once("app/i18n.py", en_tail, en_tail + en_more)

hu_tail = '        "asking_market_not_ready": "A megfigyelt kínálati adatok még nem érték el az ehhez a választáshoz szükséges minimális közölhető mintát.",\n'
hu_more = '''        "observed_subset": "Megfigyelt forrásminta",
        "live_title": "Mennyit kérnek most az eladók",
        "live_intro": "Az adott telepítés által megfigyelt Duna House-hirdetések tényszerű adatait mutatja. Ez a forrás viselkedésének részhalmaza, nem az összes aktív magyar hirdetés teljes piacának állítása.",
        "experimental": "KÍSÉRLETI",
        "policy_ok": "Forrásszabály-ellenőrzés rendben",
        "policy_paused": "Forrás szüneteltetve",
        "postcode": "Irányítószám",
        "all_postcodes": "Minden megfigyelt irányítószám",
        "median_asking": "Medián kínálati ár",
        "price_cuts": "Megfigyelt árcsökkentések",
        "observed_reductions": "megfigyelt árcsökkentés",
        "median_cut": "medián csökkentés",
        "new_observations": "Új megfigyelések",
        "last_7_days": "utolsó 7 nap",
        "today": "ma",
        "observed_days": "Medián megfigyelési nap",
        "observed_days_note": "Az az idő, amióta ez a telepítés először látta a hirdetést; nem a portál eredeti hirdetési kora.",
        "observed_history": "Megfigyelt kínálati előzmények",
        "transaction_comparison": "Tranzakciós összevetés",
        "asking_gap_note": "A kínálati/tranzakciós különbség eltérő sokaságokat vet össze; nem azonos a várható alku mértékével.",
        "feature_coverage": "Strukturált tényadatok lefedettsége",
        "listings_with_features": "Legalább 1 strukturált jellemzővel",
        "feature_field_coverage": "Jellemzőmezők kitöltöttsége",
        "usable_live_rows": "Használható aktív megfigyelések",
        "feature_privacy_note": "Csak rövid tényszerű jellemzők tárolódnak; leírások, képek és elérhetőségek nem.",
        "source_policy": "Forráshasználati korlát",
        "removed_not_sold": "Eltűnt ≠ eladott",
        "removed_not_sold_note": "Egy hirdetés csak ismételt sitemap-hiány után lesz inaktív. Az eltűnésből az alkalmazás soha nem következtet lezárt adásvételre.",
        "completed_transactions": "lezárt tranzakciós adatok",
        "local_title": "Utcaszintű adatok hamis pontosság nélkül",
        "local_intro": "A KSH éves kerületi és utcaszintű megfigyelései, majd ezek azonos évi helyi szorzója a legfrissebb budapesti használtlakás-tranzakciós referenciára alkalmazva.",
        "district": "Kerület",
        "street_search": "Utcaszűrő",
        "street_search_placeholder": "pl. Andrássy",
        "official_local": "Közölt helyi átlag",
        "local_factor_note": "A közölt helyi átlag osztva az azonos évi budapesti összlakás-átlaggal; ezt alkalmazzuk a legfrissebb budapesti használtlakás-referenciára.",
        "current_local_estimate": "Aktuális helyiszorzó-becslés",
        "street_detail": "Utcaszintű adatnapló",
        "street": "Utca",
        "no_street_rows": "Nincs a kiválasztásnak megfelelő közölt utcaszintű megfigyelés.",
        "local_method_note": "Az utcasorok KSH-aggregátumok. Az aktuális értékek átlátható, szorzóalapú becslések, nem megfigyelt mai eladási árak.",
        "local_source_note": "A KSH Ingatlanadattár éves, aggregált lezárt tranzakciós statisztikákat tartalmaz; a hiányzó cellákat az alkalmazás nem tölti ki találgatással.",
        "precision": "Pontossági fegyelem",
        "local_precision_note": "A kis elemszámú vagy szórtabb utcaminták alacsonyabb megbízhatósági címkét kapnak, nem azonos súllyal jelennek meg.",
'''
replace_once("app/i18n.py", hu_tail, hu_tail + hu_more)

append_once(
    "app/static/app.css",
    ".intelligence-grid {",
    r'''
.intelligence-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.55fr) repeat(3, minmax(150px, .72fr));
  gap: 16px;
  margin-bottom: 18px;
}
.intelligence-signal { min-height: 205px; display: flex; flex-direction: column; justify-content: flex-end; }
.intelligence-signal .label { margin-bottom: auto; padding-right: 40px; }
.signal-number { margin: 18px 0 5px; font: 800 clamp(2.2rem, 4vw, 3.5rem)/.95 var(--mono); color: var(--ink); letter-spacing: -.06em; }
.compact-number { font-size: clamp(1.45rem, 2.8vw, 2.25rem); letter-spacing: -.045em; }
.signal-stamps { display: flex; flex-wrap: wrap; gap: 9px; justify-content: flex-end; }
.signal-stamps .source-badge { gap: 6px; align-items: center; }
.live-secondary-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; margin-bottom: 18px; }
.data-ledger { display: grid; border-top: 1px solid var(--line); }
.data-ledger > div { display: flex; justify-content: space-between; gap: 20px; padding: 10px 0; border-bottom: 1px solid var(--line); }
.data-ledger span { color: var(--muted); font-size: .75rem; }
.data-ledger strong { font: 800 .82rem var(--mono); text-align: right; color: var(--ink); }
.street-ledger-head, .street-ledger-row { display: grid; grid-template-columns: minmax(190px, 2fr) .65fr 1fr 1fr .65fr; gap: 14px; align-items: center; }
.street-ledger-head { padding: 8px 12px; background: var(--ink); color: var(--paper-2); font: 800 .63rem var(--mono); letter-spacing: .06em; text-transform: uppercase; }
.street-ledger-row { padding: 11px 12px; border-bottom: 1px solid var(--line); }
.street-ledger-row:hover { background: var(--paper-2); }
.street-primary { min-width: 0; display: grid; gap: 2px; }
.street-primary strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-family: var(--serif); color: var(--ink); }
.street-primary small { color: var(--muted); font: 650 .68rem var(--mono); }
.street-count, .street-value { font: 760 .78rem var(--mono); font-variant-numeric: tabular-nums; }
.street-value.current { color: var(--asking); font-weight: 850; }
.confidence-chip { justify-self: start; padding: 4px 6px; border: 1px solid var(--line-dark); font: 800 .58rem var(--mono); letter-spacing: .06em; }
.confidence-chip.high { color: var(--good); }
.confidence-chip.medium { color: var(--warn); }
.confidence-chip.low { color: var(--bad); }
.street-ledger-card { margin-bottom: 18px; }
.current-local-card { border-top: 3px solid var(--asking); }

@media (max-width: 920px) {
  .intelligence-grid { grid-template-columns: 1fr 1fr; }
  .intelligence-lead { grid-column: 1 / -1; }
  .live-secondary-grid { grid-template-columns: 1fr; }
  .live-filter, .local-filter { grid-template-columns: 1fr 1fr; }
  .live-filter button, .local-filter button { grid-column: 1 / -1; }
  .street-ledger-head { display: none; }
  .street-ledger-row { grid-template-columns: minmax(0, 1.7fr) .55fr 1fr; }
  .street-ledger-row .street-value:first-of-type { display: none; }
  .street-ledger-row .confidence-chip { display: none; }
}

@media (max-width: 600px) {
  .intelligence-grid { grid-template-columns: 1fr; }
  .intelligence-lead { grid-column: auto; }
  .live-filter, .local-filter { grid-template-columns: 1fr; }
  .live-filter button, .local-filter button { grid-column: auto; }
  .signal-stamps { justify-content: flex-start; }
  .street-ledger-row { grid-template-columns: minmax(0, 1fr) auto; gap: 9px; }
  .street-ledger-row .street-count { display: none; }
  .street-ledger-row .street-value.current { text-align: right; }
}
''',
)
