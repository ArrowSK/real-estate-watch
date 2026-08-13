from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import (
    AskingMarketSnapshot,
    FxSnapshot,
    LocalBenchmark,
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
            "detail": f"{market_count} quarterly market observations stored",
        }
    )

    transaction_count_rows = db.scalar(
        select(func.count()).select_from(MarketSnapshot).where(MarketSnapshot.sample_size.is_not(None))
    ) or 0
    checks.append(
        {
            "key": "transaction_counts",
            "ok": transaction_count_rows > 0,
            "detail": f"{transaction_count_rows} quarterly observations have an official transaction count",
            "soft": True,
        }
    )

    local_count = db.scalar(select(func.count()).select_from(LocalBenchmark)) or 0
    checks.append(
        {
            "key": "granular_ksh",
            "ok": local_count > 0,
            "detail": (
                f"{local_count} district/street benchmark rows stored"
                if local_count
                else "Granular KSH data has not been collected yet; quarterly benchmarks remain available"
            ),
            "soft": True,
        }
    )

    listing_count = db.scalar(
        select(func.count()).select_from(ObservedListing).where(ObservedListing.active.is_(True))
    ) or 0
    asking_count = db.scalar(select(func.count()).select_from(AskingMarketSnapshot)) or 0
    checks.append(
        {
            "key": "asking_market",
            "ok": asking_count > 0,
            "detail": (
                f"{listing_count} active factual listing observations; {asking_count} aggregate snapshots"
                if asking_count
                else "Observed asking-market data has not reached a publishable sample yet"
            ),
            "soft": True,
        }
    )

    policy = db.scalar(
        select(ProviderPolicyState).where(ProviderPolicyState.source_key == "duna_house_observed")
    )
    policy_ok = policy is None or policy.status == "experimental_allowed"
    checks.append(
        {
            "key": "provider_policy",
            "ok": policy_ok,
            "detail": (
                "Duna House policy guard has not run yet"
                if policy is None
                else f"Duna House policy guard: {policy.status}"
            ),
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
    sources = list(db.scalars(select(SourceHealth).order_by(SourceHealth.source_key)))
    degraded = [source for source in sources if source.state == "degraded"]
    checks.append(
        {
            "key": "sources",
            "ok": not degraded,
            "detail": (
                "All attempted sources healthy"
                if not degraded
                else f"{len(degraded)} source(s) degraded; verified data retained"
            ),
            "soft": True,
        }
    )

    cutoff = datetime.now(timezone.utc) - timedelta(hours=settings.source_stale_hours)
    stale = [
        source.source_key
        for source in sources
        if source.last_success_at is not None and (_as_utc(source.last_success_at) or cutoff) < cutoff
    ]
    checks.append(
        {
            "key": "source_freshness",
            "ok": not stale,
            "detail": (
                f"No successful source refresh is older than {settings.source_stale_hours} hours"
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
    hard_failures = [check for check in checks if not check["ok"] and not check.get("soft")]
    return not hard_failures, checks
