from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace

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
from app.models import ProviderPolicyState, SourceHealth
from app.services.fx import converted_amounts, latest_fx
from app.services.health import readiness, run_self_checks
from app.services.ksh_local import local_benchmarks
from app.services.market import ensure_seed_market_data, latest_market, market_series
from app.services.market_intelligence import (
    latest_observed_market,
    local_nowcast,
    observed_market_history,
)
from app.services.mortgage import calculate_mortgage
from app.services.self_heal import heal_reference_data
from app.services.valuation import DEFAULT_ADJUSTMENTS, value_property

settings = get_settings()
logging.basicConfig(level=getattr(logging, settings.app_log_level.upper(), logging.INFO))
logger = logging.getLogger("real_estate_watch")
BASE_DIR = Path(__file__).resolve().parent


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


def template_context(request: Request, language: str, **extra) -> dict:
    return {
        "request": request,
        "lang": language,
        "t": translator(language),
        "version": __version__,
        "fmt": fmt_number,
        **extra,
    }


def _budapest_district_options(db: Session) -> list:
    rows = local_benchmarks(
        db,
        parent_area_code="BUDAPEST",
        level="district",
        property_type="total",
        year=settings.ksh_local_year,
    )
    if rows:
        return rows
    return [
        SimpleNamespace(area_code=f"BUDAPEST-{district:02d}", area_name=f"Budapest {district:02d}. kerület")
        for district in range(1, 24)
    ]


@app.get("/language/{language}")
def set_language(language: str, next: str = Query("/")):
    lang = normalize_language(language, settings.app_default_language)
    safe_next = next if next.startswith("/") and not next.startswith("//") else "/"
    response = RedirectResponse(safe_next, status_code=303)
    response.set_cookie("rew_lang", lang, max_age=60 * 60 * 24 * 365, samesite="lax")
    return response


@app.get("/", response_class=HTMLResponse)
def market_page(
    request: Request,
    area: str = Query("BUDAPEST"),
    market: str = Query("second_hand"),
    db: Session = Depends(get_db),
):
    language = language_from_request(request)
    provider = HungaryProvider()
    areas = provider.areas()
    valid_areas = {x["code"] for x in areas}
    area = area if area in valid_areas else "BUDAPEST"
    market = market if market in {"second_hand", "new"} else "second_hand"
    series = market_series(db, area, market)
    latest = series[-1] if series else None
    fx = latest_fx(db)
    converted = converted_amounts(latest.price_huf_m2, fx) if latest else {}
    chart = [{"period": row.period, "price": row.price_huf_m2} for row in series[-10:]]
    return templates.TemplateResponse(
        request,
        "market.html",
        template_context(
            request,
            language,
            areas=areas,
            selected_area=area,
            selected_market=market,
            latest=latest,
            converted=converted,
            fx=fx,
            chart=chart,
        ),
    )


@app.get("/live", response_class=HTMLResponse)
def live_market_page(
    request: Request,
    area: str = Query("BUDAPEST"),
    market_class: str = Query("condominium"),
    segment: str = Query("second_hand"),
    db: Session = Depends(get_db),
):
    language = language_from_request(request)
    district_options = _budapest_district_options(db)
    areas = [{"code": "BUDAPEST", "name": "Budapest"}] + [
        {"code": row.area_code, "name": row.area_name} for row in district_options
    ]
    valid_areas = {x["code"] for x in areas}
    area = area if area in valid_areas else "BUDAPEST"
    market_class = market_class if market_class in {"condominium", "panel", "family_house"} else "condominium"
    segment = segment if segment in {"second_hand", "new"} else "second_hand"
    latest = latest_observed_market(
        db,
        area_code=area,
        market_class=market_class,
        market_segment=segment,
    )
    history_rows = observed_market_history(
        db,
        area_code=area,
        market_class=market_class,
        market_segment=segment,
    )
    history = [
        {"period": row.snapshot_date.isoformat(), "price": row.median_huf_m2}
        for row in history_rows
    ]
    policy = db.scalar(
        select(ProviderPolicyState).where(ProviderPolicyState.provider_key == "duna_house")
    )
    policy_ok = bool(policy and policy.state == "reviewed_experimental")
    asking_gap = None
    if latest and area.startswith("BUDAPEST-") and segment == "second_hand":
        local_type = market_class if market_class in {"condominium", "panel", "family_house"} else "total"
        nowcast = local_nowcast(db, area_code=area, property_type=local_type)
        if nowcast and nowcast.nowcast_huf_m2:
            asking_gap = (latest.median_huf_m2 / nowcast.nowcast_huf_m2 - 1) * 100
    return templates.TemplateResponse(
        request,
        "live.html",
        template_context(
            request,
            language,
            areas=areas,
            selected_area=area,
            selected_class=market_class,
            selected_segment=segment,
            latest=latest,
            history=history,
            policy_ok=policy_ok,
            asking_gap=asking_gap,
        ),
    )


@app.get("/local", response_class=HTMLResponse)
def local_market_page(
    request: Request,
    area: str = Query("BUDAPEST-06"),
    property_type: str = Query("condominium"),
    db: Session = Depends(get_db),
):
    language = language_from_request(request)
    districts = _budapest_district_options(db)
    valid_areas = {row.area_code for row in districts}
    area = area if area in valid_areas else "BUDAPEST-06"
    property_type = property_type if property_type in {"condominium", "panel", "family_house", "total"} else "condominium"
    nowcast = local_nowcast(db, area_code=area, property_type=property_type)
    streets = local_benchmarks(
        db,
        parent_area_code=area,
        level="street",
        property_type=property_type,
        year=settings.ksh_local_year,
    )
    return templates.TemplateResponse(
        request,
        "local.html",
        template_context(
            request,
            language,
            districts=districts,
            selected_area=area,
            selected_type=property_type,
            selected_year=settings.ksh_local_year,
            nowcast=nowcast,
            streets=streets,
        ),
    )


@app.get("/valuation", response_class=HTMLResponse)
def valuation_page(
    request: Request,
    district: str = Query("BUDAPEST-06"),
    property_type: str = Query("condominium"),
    db: Session = Depends(get_db),
):
    language = language_from_request(request)
    districts = _budapest_district_options(db)
    valid = {row.area_code for row in districts}
    district = district if district in valid else "BUDAPEST-06"
    property_type = property_type if property_type in {"condominium", "panel", "family_house", "total"} else "condominium"
    local = local_nowcast(db, area_code=district, property_type=property_type)
    latest = latest_market(db, "BUDAPEST", "second_hand")
    baseline = local.nowcast_huf_m2 if local else (latest.price_huf_m2 if latest else 1_200_000)
    return templates.TemplateResponse(
        request,
        "valuation.html",
        template_context(
            request,
            language,
            result=None,
            baseline=baseline,
            factors=DEFAULT_ADJUSTMENTS,
            fx=latest_fx(db),
            districts=districts,
            district=district,
            property_type=property_type,
            local_nowcast=local,
        ),
    )


@app.post("/valuation", response_class=HTMLResponse)
def valuation_calculate(
    request: Request,
    floor_area: float = Form(...),
    baseline: float = Form(...),
    factors: list[str] = Form(default=[]),
    district: str = Form("BUDAPEST-06"),
    property_type: str = Form("condominium"),
    db: Session = Depends(get_db),
):
    language = language_from_request(request)
    try:
        result = value_property(floor_area_m2=floor_area, baseline_huf_m2=baseline, factors=factors)
        error = None
    except ValueError as exc:
        result, error = None, str(exc)
    fx = latest_fx(db)
    conversions = converted_amounts(result.estimated_value_huf, fx) if result else {}
    districts = _budapest_district_options(db)
    local = local_nowcast(db, area_code=district, property_type=property_type)
    return templates.TemplateResponse(
        request,
        "valuation.html",
        template_context(
            request,
            language,
            result=result,
            error=error,
            baseline=baseline,
            floor_area=floor_area,
            selected_factors=factors,
            factors=DEFAULT_ADJUSTMENTS,
            fx=fx,
            conversions=conversions,
            districts=districts,
            district=district,
            property_type=property_type,
            local_nowcast=local,
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
        result, error = None, str(exc)
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
    checks = run_self_checks(db)
    return templates.TemplateResponse(
        request,
        "diagnostics.html",
        template_context(request, language, sources=sources, checks=checks),
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
    db: Session = Depends(get_db),
):
    rows = market_series(db, area, market)
    fx = latest_fx(db)
    return {
        "country": "HU",
        "area": area,
        "market": market,
        "currency": "HUF",
        "fx": {k: {"huf_per_unit": v.huf_per_unit, "date": v.rate_date} for k, v in fx.items()},
        "series": [
            {
                "period": x.period,
                "observation_date": x.observation_date,
                "metric": x.metric,
                "price_huf_m2": x.price_huf_m2,
                "sample_size": x.sample_size,
                "source": x.source_key,
                "source_url": x.source_url,
            }
            for x in rows
        ],
    }


@app.get("/api/observed-market")
def observed_market_api(
    area: str = Query("BUDAPEST"),
    market_class: str = Query("condominium"),
    segment: str = Query("second_hand"),
    db: Session = Depends(get_db),
):
    rows = observed_market_history(
        db,
        area_code=area,
        market_class=market_class,
        market_segment=segment,
    )
    return {
        "provider": "duna_house",
        "coverage": "observed_subset",
        "area": area,
        "market_class": market_class,
        "market_segment": segment,
        "series": [
            {
                "date": row.snapshot_date,
                "sample": row.active_count,
                "median_huf_m2": row.median_huf_m2,
                "p25_huf_m2": row.p25_huf_m2,
                "p75_huf_m2": row.p75_huf_m2,
                "price_cut_share": row.price_cut_share,
            }
            for row in rows
        ],
    }


@app.get("/api/local-market")
def local_market_api(
    area: str = Query("BUDAPEST-06"),
    property_type: str = Query("condominium"),
    db: Session = Depends(get_db),
):
    estimate = local_nowcast(db, area_code=area, property_type=property_type)
    if estimate is None:
        return {"available": False, "area": area, "property_type": property_type}
    return {
        "available": True,
        "area": area,
        "area_name": estimate.area_name,
        "property_type": property_type,
        "official_year": estimate.source_year,
        "official_huf_m2": estimate.official_huf_m2,
        "official_transactions": estimate.official_transactions,
        "relative_std_pct": estimate.relative_std_pct,
        "nowcast_huf_m2": estimate.nowcast_huf_m2,
        "confidence": estimate.confidence,
        "method": "annual local KSH benchmark rolled forward by Budapest second-hand transaction trend",
        "latest_budapest_period": estimate.latest_period,
    }


@app.get("/api/health")
def health_api(db: Session = Depends(get_db)):
    ready, checks = readiness(db)
    sources = list(db.scalars(select(SourceHealth).order_by(SourceHealth.source_key)))
    return {
        "ready": ready,
        "checks": checks,
        "sources": [
            {
                "source": s.source_key,
                "state": s.state,
                "last_success": s.last_success_at,
                "last_attempt": s.last_attempt_at,
                "failures": s.consecutive_failures,
            }
            for s in sources
        ],
    }


@app.post("/ops/refresh")
def operations_refresh(
    x_admin_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    if not settings.admin_key:
        raise HTTPException(status_code=503, detail="ADMIN_KEY is not configured")
    if x_admin_key != settings.admin_key:
        raise HTTPException(status_code=403, detail="Invalid admin key")
    return run_daily_collection(db)
