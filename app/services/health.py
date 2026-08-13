from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import (
    FxSnapshot,
    LocalMarketBenchmark,
    MarketSnapshot,
    ObservedListing,
    ProviderPolicyState,
    SourceHealth,
)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def run_self_checks(db: Session) -> list[dict]:
    checks: list[dict] = []
    try:
        db.execute(text("SELECT 1"))
        checks.append({"key": "database", "ok": True, "detail": "Database query succeeded"})
    except Exception as exc:
        return [{"key": "database", "ok": False, "detail": str(exc)}]

    market_count = db.scalar(select(func.count()).select_from(MarketSnapshot)) or 0
    checks.append(
        {
            "key": "market_data",
            "ok": market_count > 0,
            "detail": f"{market_count} official quarterly market observations stored",
        }
    )

    counted = db.scalar(
        select(func.count()).select_from(MarketSnapshot).where(MarketSnapshot.sample_size.is_not(None))
    ) or 0
    checks.append(
        {
            "key": "transaction_counts",
            "ok": counted > 0,
            "detail": f"{counted} market observations have an official transaction count",
            "soft": True,
        }
    )

    local_count = db.scalar(select(func.count()).select_from(LocalMarketBenchmark)) or 0
    checks.append(
        {
            "key": "local_market_data",
            "ok": local_count > 0,
            "detail": f"{local_count} granular KSH district/street benchmark rows stored",
            "soft": True,
        }
    )

    fx_count = db.scalar(select(func.count()).select_from(FxSnapshot)) or 0
    checks.append(
        {
            "key": "fx_data",
            "ok": fx_count >= 2,
            "detail": f"{fx_count} FX observations stored; HUF-only operation remains available if this is zero",
            "soft": True,
        }
    )

    settings = get_settings()
    observed_count = db.scalar(
        select(func.count()).select_from(ObservedListing).where(
            ObservedListing.provider_key == "duna_house",
            ObservedListing.active.is_(True),
            ObservedListing.quality_state == "usable",
        )
    ) or 0
    checks.append(
        {
            "key": "observed_asking_market",
            "ok": observed_count >= settings.duna_house_min_aggregate_sample,
            "detail": (
                f"{observed_count} usable active Duna House observations stored; "
                "this is an observed subset, not the complete Hungarian listing market"
            ),
            "soft": True,
        }
    )

    policy = db.scalar(
        select(ProviderPolicyState).where(ProviderPolicyState.provider_key == "duna_house")
    )
    policy_ok = policy is not None and policy.state == "reviewed_experimental"
    checks.append(
        {
            "key": "duna_house_policy_gate",
            "ok": policy_ok or not settings.duna_house_enabled,
            "detail": (
                "Duna House reviewed access markers unchanged"
                if policy_ok
                else (
                    "Duna House provider disabled by configuration"
                    if not settings.duna_house_enabled
                    else "Duna House policy gate has not passed; observed collection remains paused"
                )
            ),
            "soft": True,
        }
    )

    sources = list(db.scalars(select(SourceHealth).order_by(SourceHealth.source_key)))
    degraded = [source for source in sources if source.state == "degraded"]
    checks.append(
        {
            "key": "sources",
            "ok": not degraded,
            "detail": (
                "All attempted sources healthy"
                if not degraded
                else f"{len(degraded)} source(s) degraded; last known-good data retained"
            ),
            "soft": True,
        }
    )

    cutoff = datetime.now(timezone.utc) - timedelta(hours=settings.source_stale_hours)
    stale = [
        source.source_key
        for source in sources
        if source.last_success_at is not None and (_as_utc(source.last_success_at) or cutoff) < cutoff
        and source.source_key != "ksh_local_market"
    ]
    checks.append(
        {
            "key": "source_freshness",
            "ok": not stale,
            "detail": (
                f"No daily source success is older than {settings.source_stale_hours} hours"
                if not stale
                else f"Stale source(s): {', '.join(stale)}"
            ),
            "soft": True,
        }
    )

    checks.append(
        {
            "key": "self_heal",
            "ok": settings.self_heal_enabled,
            "detail": (
                "Reference-data recovery enabled"
                if settings.self_heal_enabled
                else "Reference-data recovery disabled by configuration"
            ),
            "soft": True,
        }
    )
    return checks


def readiness(db: Session) -> tuple[bool, list[dict]]:
    checks = run_self_checks(db)
    hard_failures = [c for c in checks if not c["ok"] and not c.get("soft")]
    return not hard_failures, checks
