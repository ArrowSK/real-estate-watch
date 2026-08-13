from __future__ import annotations

import logging
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Form, Header, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import __version__
from app.config import get_settings
from app.countries.hu.provider import HungaryProvider
from app.db import SessionLocal, get_db, init_db
from app.i18n import normalize_language, translator
from app.jobs import run_daily_collection
from app.models import JobRun, ProviderPolicyState, SourceHealth
from app.services.analytics import (
    ASKING_PROPERTY_MAP,
    LOCAL_PROPERTY_MAP,
    market_comparison,
    transaction_nowcast,
)
from app.services.duna_house import DH_SOURCE_KEY, asking_market_series
from app.services.fx import converted_amounts, latest_fx
from app.services.health import readiness, run_self_checks
from app.services.ksh_local import streets_for_area
from app.services.live_intelligence import (
    live_comparison,
    live_history,
    live_signals,
    local_district_signal,
    local_street_signals,
    local_years,
)
from app.services.market import ensure_seed_market_data, market_series
from app.services.mortgage import calculate_mortgage
from app.services.self_heal import heal_reference_data
from app.services.valuation import DEFAULT_ADJUSTMENTS, value_property

settings = get_settings()
logging.basicConfig(level=getattr(logging, settings.app_log_level.upper(), logging.INFO))
logger = logging.getLogger("real_estate_watch")
BASE_DIR = Path(__file__).resolve().parent

HU_ERROR_TRANSLATIONS = {
    "Floor area is outside the supported range": "Az alapterület a támogatott tartományon kívül esik.",
    "Baseline must be positive": "Az alap négyzetméterárnak pozitívnak kell lennie.",
    "Purchase price must be positive": "A vételárnak pozitívnak kell lennie.",
    "Down payment must be between zero and the purchase price": "Az önerőnek nulla és a vételár közé kell esnie.",
    "Interest rate must be between 0% and 30%": "A kamatnak 0% és 30% közé kell esnie.",
    "Term must be between 1 and 40 years": "A futamidőnek 1 és 40 év közé kell esnie.",
}

PROPERTY_TYPES = (
    ("all", "All homes", "Minden lakás"),
    ("apartment", "Apartments", "Társasházi lakások"),
    ("house", "Houses", "Családi házak"),
    ("panel", "Panel apartments", "Lakótelepi panellakások"),
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    with SessionLocal() as db:
        ensure_seed_market_data(db)
        heal_reference_data(db)
    yield


app = FastAPI(title="Real Estate Watch", version=__version__, lifespan=lifespan)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


def language_from_request(request: Request, explicit: str | None = None) -> str:
    if explicit:
        return normalize_language(explicit, settings.app_default_language)
    cookie = request.cookies.get("rew_lang")
    if cookie:
        return normalize_language(cookie, settings.app_default_language)
    return normalize_language(settings.app_default_language)


def fmt_number(value: float | int | None, digits: int = 0) -> str:
    if value is None:
        return "—"
    return f"{value:,.{digits}f}"


def localized_error(language: str, error: Exception | str) -> str:
    message = str(error)
    if language == "hu":
        return HU_ERROR_TRANSLATIONS.get(message, message)
    return message


def template_context(request: Request, language: str, **extra) -> dict:
    return {
        "request": request,
        "lang": language,
        "t": translator(language),
        "version": __version__,
        "fmt": fmt_number,
        **extra,
    }


def hungary_selection(
    area: str,
    market: str,
    property_type: str = "all",
) -> tuple[HungaryProvider, list[dict[str, str]], str, str, str]:
    provider = HungaryProvider()
    areas = provider.areas()
    valid_areas = {item["code"] for item in areas}
    selected_area = area if area in valid_areas else "BUDAPEST"
    selected_market = market if market in {"second_hand", "new"} else "second_hand"
    valid_property_types = {item[0] for item in PROPERTY_TYPES}
    selected_property_type = property_type if property_type in valid_property_types else "all"
    return provider, areas, selected_area, selected_market, selected_property_type


def _area_info(areas: list[dict[str, str]], area_code: str) -> dict[str, str]:
    return next((item for item in areas if item["code"] == area_code), areas[0])


@app.get("/language/{language}")
def set_language(language: str, next: str = Query("/")):
    lang = normalize_language(language, settings.app_default_language)
    response = RedirectResponse(next if next.startswith("/") else "/", status_code=303)
    response.set_cookie("rew_lang", lang, max_age=60 * 60 * 24 * 365, samesite="lax")
    return response


@app.get("/", response_class=HTMLResponse)
def market_page(
    request: Request,
    area: str = Query("BUDAPEST"),
    market: str = Query("second_hand"),
    property_type: str = Query("all"),
    range: str = Query("6m"),
    db: Session = Depends(get_db),
):
    language = language_from_request(request)
    _, areas, area, market, property_type = hungary_selection(area, market, property_type)
    selected_range = range if range in {"6m", "1y", "all"} else "6m"
    area_info = _area_info(areas, area)
    comparison = market_comparison(db, area, market, property_type)
    official = comparison.official
    asking = comparison.asking
    fx = latest_fx(db)
    official_converted = converted_amounts(official.value_huf_m2, fx) if official else {}
    asking_converted = converted_amounts(asking.median_huf_m2, fx) if asking else {}

    quarterly_area = "BUDAPEST" if area.startswith("BUDAPEST_") else area
    official_rows = market_series(db, quarterly_area, market)
    if selected_range == "6m":
        chart_rows = official_rows[-3:]
    elif selected_range == "1y":
        chart_rows = official_rows[-5:]
    else:
        chart_rows = official_rows
    official_chart = [
        {"period": row.period, "date": row.observation_date.isoformat(), "price": row.price_huf_m2}
        for row in chart_rows
    ]

    asking_type = comparison.asking_scope or ASKING_PROPERTY_MAP.get(property_type, "all")
    asking_rows = asking_market_series(db, area, asking_type, market)
    if selected_range == "6m":
        asking_rows = asking_rows[-183:]
    elif selected_range == "1y":
        asking_rows = asking_rows[-366:]
    asking_chart = [
        {
            "period": row.snapshot_date.isoformat(),
            "date": row.snapshot_date.isoformat(),
            "price": row.median_huf_m2,
        }
        for row in asking_rows
    ]

    return templates.TemplateResponse(
        request,
        "market.html",
        template_context(
            request,
            language,
            areas=areas,
            selected_area=area,
            selected_area_info=area_info,
            selected_market=market,
            selected_property_type=property_type,
            property_types=PROPERTY_TYPES,
            selected_range=selected_range,
            comparison=comparison,
            official=official,
            asking=asking,
            official_converted=official_converted,
            asking_converted=asking_converted,
            fx=fx,
            official_chart=official_chart,
            asking_chart=asking_chart,
            latest=official,
            converted=official_converted,
            chart=official_chart,
        ),
    )


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


@app.get("/valuation", response_class=HTMLResponse)
def valuation_page(
    request: Request,
    area: str = Query("BUDAPEST_06"),
    market: str = Query("second_hand"),
    property_type: str = Query("apartment"),
    street: str = Query(""),
    db: Session = Depends(get_db),
):
    language = language_from_request(request)
    _, areas, area, market, property_type = hungary_selection(area, market, property_type)
    baseline = transaction_nowcast(db, area, market, property_type, street or None)
    comparison = market_comparison(db, area, market, property_type, street or None)
    streets = streets_for_area(db, area) if area.startswith("BUDAPEST_") else []
    return templates.TemplateResponse(
        request,
        "valuation.html",
        template_context(
            request,
            language,
            result=None,
            baseline=baseline,
            baseline_row=baseline,
            comparison=comparison,
            areas=areas,
            selected_area=area,
            selected_market=market,
            selected_property_type=property_type,
            property_types=PROPERTY_TYPES,
            street=street,
            streets=streets,
            factors=DEFAULT_ADJUSTMENTS,
            fx=latest_fx(db),
        ),
    )


@app.post("/valuation", response_class=HTMLResponse)
def valuation_calculate(
    request: Request,
    area: str = Form("BUDAPEST_06"),
    market: str = Form("second_hand"),
    property_type: str = Form("apartment"),
    street: str = Form(""),
    floor_area: float = Form(...),
    asking_price: float | None = Form(None),
    factors: list[str] = Form(default=[]),
    db: Session = Depends(get_db),
):
    language = language_from_request(request)
    _, areas, area, market, property_type = hungary_selection(area, market, property_type)
    baseline = transaction_nowcast(db, area, market, property_type, street or None)
    comparison = market_comparison(db, area, market, property_type, street or None)
    try:
        if baseline is None:
            raise ValueError(
                "Nincs elérhető piaci referencia ehhez a választáshoz."
                if language == "hu"
                else "No market benchmark is available for this selection."
            )
        result = value_property(
            floor_area_m2=floor_area,
            baseline_huf_m2=baseline.value_huf_m2,
            factors=factors,
        )
        error = None
    except ValueError as exc:
        result, error = None, localized_error(language, exc)
    fx = latest_fx(db)
    conversions = converted_amounts(result.estimated_value_huf, fx) if result else {}
    asking_gap = (
        (asking_price / result.estimated_value_huf - 1) * 100
        if result and asking_price and asking_price > 0
        else None
    )
    streets = streets_for_area(db, area) if area.startswith("BUDAPEST_") else []
    return templates.TemplateResponse(
        request,
        "valuation.html",
        template_context(
            request,
            language,
            result=result,
            error=error,
            baseline=baseline,
            baseline_row=baseline,
            comparison=comparison,
            floor_area=floor_area,
            asking_price=asking_price,
            asking_gap=asking_gap,
            selected_factors=factors,
            areas=areas,
            selected_area=area,
            selected_market=market,
            selected_property_type=property_type,
            property_types=PROPERTY_TYPES,
            street=street,
            streets=streets,
            factors=DEFAULT_ADJUSTMENTS,
            fx=fx,
            conversions=conversions,
        ),
    )


@app.get("/mortgage", response_class=HTMLResponse)
def mortgage_page(request: Request):
    language = language_from_request(request)
    return templates.TemplateResponse(
        request,
        "mortgage.html",
        template_context(request, language, result=None, values={}),
    )


@app.post("/mortgage", response_class=HTMLResponse)
def mortgage_calculate(
    request: Request,
    purchase_price: float = Form(...),
    down_payment: float = Form(...),
    net_income: float = Form(...),
    existing_debt: float = Form(0),
    interest_rate: float = Form(...),
    term_years: int = Form(...),
    fixation_years: int = Form(...),
    first_home: bool = Form(False),
    green: bool = Form(False),
):
    language = language_from_request(request)
    try:
        result = calculate_mortgage(
            purchase_price_huf=purchase_price,
            down_payment_huf=down_payment,
            net_income_huf=net_income,
            existing_debt_huf=existing_debt,
            annual_rate_percent=interest_rate,
            term_years=term_years,
            fixation_years=fixation_years,
            first_home=first_home,
            green=green,
        )
        error = None
    except ValueError as exc:
        result, error = None, localized_error(language, exc)
    return templates.TemplateResponse(
        request,
        "mortgage.html",
        template_context(
            request,
            language,
            result=result,
            error=error,
            values={
                "purchase_price": purchase_price,
                "down_payment": down_payment,
                "net_income": net_income,
                "existing_debt": existing_debt,
                "interest_rate": interest_rate,
                "term_years": term_years,
                "fixation_years": fixation_years,
                "first_home": first_home,
                "green": green,
            },
        ),
    )


@app.get("/diagnostics", response_class=HTMLResponse)
def diagnostics_page(request: Request, db: Session = Depends(get_db)):
    language = language_from_request(request)
    sources = list(db.scalars(select(SourceHealth).order_by(SourceHealth.source_key)))
    policies = list(db.scalars(select(ProviderPolicyState).order_by(ProviderPolicyState.source_key)))
    jobs = list(db.scalars(select(JobRun).order_by(JobRun.started_at.desc()).limit(8)))
    checks = run_self_checks(db)
    return templates.TemplateResponse(
        request,
        "diagnostics.html",
        template_context(
            request,
            language,
            sources=sources,
            policies=policies,
            jobs=jobs,
            checks=checks,
        ),
    )


@app.get("/health/live")
def health_live():
    return {"status": "ok", "version": __version__}


@app.get("/health/ready")
def health_ready(db: Session = Depends(get_db)):
    ready, checks = readiness(db)
    return JSONResponse(
        {"status": "ok" if ready else "not_ready", "checks": checks},
        status_code=200 if ready else 503,
    )


@app.get("/api/market")
def market_api(
    area: str = Query("BUDAPEST"),
    market: str = Query("second_hand"),
    property_type: str = Query("all"),
    db: Session = Depends(get_db),
):
    _, _, area, market, property_type = hungary_selection(area, market, property_type)
    comparison = market_comparison(db, area, market, property_type)
    official_area = "BUDAPEST" if area.startswith("BUDAPEST_") else area
    rows = market_series(db, official_area, market)
    fx = latest_fx(db)
    return {
        "country": "HU",
        "area": area,
        "market": market,
        "property_type": property_type,
        "currency": "HUF",
        "official_nowcast": (
            {
                "price_huf_m2": comparison.official.value_huf_m2,
                "local_base_huf_m2": comparison.official.local_base_huf_m2,
                "local_year": comparison.official.local_year,
                "city_reference_huf_m2": comparison.official.city_reference_huf_m2,
                "local_factor": comparison.official.local_factor,
                "geography": comparison.official.geography,
                "sample_size": comparison.official.sample_size,
                "method": comparison.official.method,
                "source_url": comparison.official.source_url,
            }
            if comparison.official
            else None
        ),
        "observed_asking": (
            {
                "median_huf_m2": comparison.asking.median_huf_m2,
                "p25_huf_m2": comparison.asking.p25_huf_m2,
                "p75_huf_m2": comparison.asking.p75_huf_m2,
                "sample_size": comparison.asking.sample_size,
                "confidence": comparison.asking.confidence,
                "status": comparison.asking.status,
                "snapshot_date": comparison.asking.snapshot_date,
            }
            if comparison.asking
            else None
        ),
        "asking_gap_pct": comparison.asking_gap_pct,
        "fx": {key: {"huf_per_unit": value.huf_per_unit, "date": value.rate_date} for key, value in fx.items()},
        "quarterly_series": [
            {
                "period": row.period,
                "observation_date": row.observation_date,
                "metric": row.metric,
                "price_huf_m2": row.price_huf_m2,
                "sample_size": row.sample_size,
                "source": row.source_key,
                "source_url": row.source_url,
            }
            for row in rows
        ],
    }


@app.get("/api/health")
def health_api(db: Session = Depends(get_db)):
    ready, checks = readiness(db)
    sources = list(db.scalars(select(SourceHealth).order_by(SourceHealth.source_key)))
    policies = list(db.scalars(select(ProviderPolicyState).order_by(ProviderPolicyState.source_key)))
    return {
        "ready": ready,
        "checks": checks,
        "sources": [
            {
                "source": source.source_key,
                "state": source.state,
                "last_success": source.last_success_at,
                "last_attempt": source.last_attempt_at,
                "failures": source.consecutive_failures,
            }
            for source in sources
        ],
        "provider_policies": [
            {
                "source": policy.source_key,
                "status": policy.status,
                "reviewed_on": policy.reviewed_on,
                "last_checked": policy.last_checked_at,
            }
            for policy in policies
        ],
    }


@app.post("/ops/refresh")
def operations_refresh(
    x_admin_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    if not settings.admin_key:
        raise HTTPException(status_code=503, detail="ADMIN_KEY is not configured")
    if not secrets.compare_digest(x_admin_key or "", settings.admin_key):
        raise HTTPException(status_code=403, detail="Invalid admin key")
    return run_daily_collection(db)
