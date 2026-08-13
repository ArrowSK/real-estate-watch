from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import JobRun
from app.services.fx import refresh_mnb_fx
from app.services.health import run_self_checks
from app.services.market import latest_market, refresh_ksh
from app.services.notifications import send_notifications
from app.services.self_heal import heal_reference_data


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
        tracked = [("BUDAPEST", "second_hand"), ("BUDAPEST", "new"), ("HU", "second_hand"), ("HU", "new")]
        before = {
            key: (row.period, row.price_huf_m2) if (row := latest_market(db, *key)) else None
            for key in tracked
        }
        result["market"] = refresh_ksh(db)
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
                changes.append({"area": key[0], "market": key[1], "from": old, "to": new, "change_percent": pct * 100})
        result["market_changes"] = changes
        if changes:
            result["market_notification"] = send_notifications(
                db,
                "market_change",
                {"event": "market_change", "changes": changes},
            )
        result["fx"] = refresh_mnb_fx(db)
        result["checks"] = run_self_checks(db)
        result["ok"] = bool(result["market"].get("ok") and result["fx"].get("ok"))
        if not result["ok"]:
            result["source_notification"] = send_notifications(
                db,
                "source_degraded",
                {
                    "event": "source_degraded",
                    "market": result["market"],
                    "fx": result["fx"],
                    "message": "A data source failed. Real Estate Watch kept the last known-good data.",
                },
            )
        job.state = "success" if result["ok"] else "degraded"
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
