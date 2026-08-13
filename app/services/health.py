from datetime import datetime, timezone

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import FxSnapshot, MarketSnapshot, SourceHealth


def run_self_checks(db: Session) -> list[dict]:
    checks: list[dict] = []
    try:
        db.execute(text("SELECT 1"))
        checks.append({"key": "database", "ok": True, "detail": "Database query succeeded"})
    except Exception as exc:
        return [{"key": "database", "ok": False, "detail": str(exc)}]

    market_count = db.scalar(select(func.count()).select_from(MarketSnapshot)) or 0
    checks.append({
        "key": "market_data",
        "ok": market_count > 0,
        "detail": f"{market_count} market observations stored",
    })

    fx_count = db.scalar(select(func.count()).select_from(FxSnapshot)) or 0
    checks.append({
        "key": "fx_data",
        "ok": fx_count >= 2,
        "detail": f"{fx_count} FX observations stored; HUF-only operation remains available if this is zero",
        "soft": True,
    })

    settings = get_settings()
    degraded = list(db.scalars(select(SourceHealth).where(SourceHealth.state == "degraded")))
    checks.append({
        "key": "sources",
        "ok": not degraded,
        "detail": "All attempted sources healthy" if not degraded else f"{len(degraded)} source(s) degraded; last known-good data retained",
        "soft": True,
    })
    checks.append({
        "key": "self_heal",
        "ok": settings.self_heal_enabled,
        "detail": "Reference-data recovery enabled" if settings.self_heal_enabled else "Reference-data recovery disabled by configuration",
        "soft": True,
    })
    return checks


def readiness(db: Session) -> tuple[bool, list[dict]]:
    checks = run_self_checks(db)
    hard_failures = [c for c in checks if not c["ok"] and not c.get("soft")]
    return not hard_failures, checks
