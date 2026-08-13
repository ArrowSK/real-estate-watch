from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.countries.hu.provider import HungaryProvider
from app.countries.hu.providers.duna_house import collect_duna_house
from app.models import JobRun
from app.services.fx import refresh_mnb_fx
from app.services.health import run_self_checks
from app.services.ksh_local import refresh_ksh_local
from app.services.market import latest_market, refresh_ksh
from app.services.market_intelligence import refresh_observed_market_aggregates
from app.services.notifications import send_notifications
from app.services.self_heal import heal_reference_data
from app.services.transaction_counts import refresh_ksh_transaction_counts


def _tracked_hungary_series() -> list[tuple[str, str]]:
    areas = HungaryProvider().areas()
    return [
        (area["code"], market)
        for area in areas
        for market in ("second_hand", "new")
    ]


def run_daily_collection(db: Session) -> dict:
    now = datetime.now(timezone.utc)
    running = db.scalar(
        select(JobRun)
        .where(JobRun.job_name == "daily_collection", JobRun.state == "running")
        .order_by(JobRun.started_at.desc())
        .limit(1)
    )
    if running:
        started = running.started_at
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        if now - started < timedelta(hours=2):
            return {"ok": False, "skipped": True, "reason": "daily collection already running"}
        running.state = "abandoned"
        running.finished_at = now
        running.detail = "Recovered stale job lock after two hours"
        db.commit()

    job = JobRun(job_name="daily_collection", state="running")
    db.add(job)
    db.commit()
    result: dict = {"ok": True, "job_id": job.id}
    try:
        result["self_heal"] = heal_reference_data(db)
        tracked = _tracked_hungary_series()
        before = {
            key: (row.period, row.price_huf_m2) if (row := latest_market(db, *key)) else None
            for key in tracked
        }

        # Official sources remain the backbone. Granular KSH is internally freshness-gated,
        # so calling it daily does not mean downloading the annual street tables every day.
        result["market"] = refresh_ksh(db)
        result["transaction_counts"] = refresh_ksh_transaction_counts(db)
        result["local_market"] = refresh_ksh_local(db)
        result["fx"] = refresh_mnb_fx(db)

        # The Duna House provider is an optional observed asking-market subset. Its own policy
        # gate can pause it without taking the official KSH/MNB application offline.
        result["observed_market"] = collect_duna_house(db)
        result["observed_aggregates"] = refresh_observed_market_aggregates(db)

        after = {
            key: (row.period, row.price_huf_m2) if (row := latest_market(db, *key)) else None
            for key in tracked
        }
        changes = []
        threshold = get_settings().market_notify_change_percent / 100
        for key in tracked:
            old, new = before[key], after[key]
            if not old or not new:
                continue
            period_changed = old[0] != new[0]
            pct = (new[1] / old[1] - 1) if old[1] else 0.0
            if period_changed or abs(pct) >= threshold:
                changes.append(
                    {
                        "area": key[0],
                        "market": key[1],
                        "from": old,
                        "to": new,
                        "change_percent": pct * 100,
                    }
                )
        result["market_changes"] = changes
        if changes:
            result["market_notification"] = send_notifications(
                db,
                "market_change",
                {"event": "market_change", "changes": changes},
            )

        core_results = (
            result["market"],
            result["transaction_counts"],
            result["local_market"],
            result["fx"],
        )
        optional_results = (result["observed_market"], result["observed_aggregates"])
        result["ok"] = all(item.get("ok") for item in core_results)
        result["degraded"] = not all(item.get("ok") for item in (*core_results, *optional_results))
        result["checks"] = run_self_checks(db)

        if result["degraded"]:
            result["source_notification"] = send_notifications(
                db,
                "source_degraded",
                {
                    "event": "source_degraded",
                    "market": result["market"],
                    "transaction_counts": result["transaction_counts"],
                    "local_market": result["local_market"],
                    "fx": result["fx"],
                    "observed_market": result["observed_market"],
                    "message": "A data source is degraded. Real Estate Watch kept the last known-good data and did not bypass its policy or validation gates.",
                },
            )
        job.state = "failed" if not result["ok"] else ("degraded" if result["degraded"] else "success")
        job.detail = str({k: v for k, v in result.items() if k not in {"checks"}})[:4000]
    except Exception as exc:
        db.rollback()
        job = db.get(JobRun, job.id)
        job.state = "failed"
        job.detail = str(exc)[:4000]
        result = {"ok": False, "job_id": job.id, "error": str(exc)}
    finally:
        job.finished_at = datetime.now(timezone.utc)
        db.commit()
    return result
