import json

import httpx
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import NotificationEvent


def send_webhook(db: Session, subject_key: str, payload: dict) -> dict:
    settings = get_settings()
    if not settings.notify_webhook_url:
        return {"ok": True, "skipped": True, "reason": "NOTIFY_WEBHOOK_URL is not configured"}

    event = NotificationEvent(
        channel="webhook",
        subject_key=subject_key,
        payload=json.dumps(payload, ensure_ascii=False),
        state="pending",
    )
    db.add(event)
    db.commit()
    try:
        with httpx.Client(timeout=settings.http_timeout_seconds) as client:
            response = client.post(settings.notify_webhook_url, json=payload)
            response.raise_for_status()
        event.state = "sent"
        db.commit()
        return {"ok": True}
    except Exception as exc:
        event.state = "failed"
        event.error = str(exc)[:2000]
        db.commit()
        return {"ok": False, "error": str(exc)}
