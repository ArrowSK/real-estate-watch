from __future__ import annotations

import json
import smtplib
from email.message import EmailMessage

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import NotificationEvent
from app.services.http import request_with_retry


def _record(db: Session, channel: str, subject_key: str, payload: dict) -> NotificationEvent:
    event = NotificationEvent(
        channel=channel,
        subject_key=subject_key,
        payload=json.dumps(payload, ensure_ascii=False),
        state="pending",
    )
    db.add(event)
    db.commit()
    return event


def _finish(db: Session, event: NotificationEvent, *, error: str | None = None) -> None:
    event.state = "failed" if error else "sent"
    event.error = error[:2000] if error else None
    db.commit()


def notification_text(subject_key: str, payload: dict, language: str = "en") -> tuple[str, str]:
    hu = language == "hu"
    if subject_key == "market_change":
        title = "Piaci referencia változás" if hu else "Market benchmark changed"
        lines = [title]
        for change in payload.get("changes", []):
            area = change.get("area", "?")
            market = change.get("market", "?").replace("_", " ")
            before = change.get("from") or ["?", 0]
            after = change.get("to") or ["?", 0]
            pct = float(change.get("change_percent", 0))
            lines.append(
                f"{area} · {market}: {before[0]} {float(before[1]):,.0f} → "
                f"{after[0]} {float(after[1]):,.0f} HUF/m² ({pct:+.1f}%)"
            )
        return title, "\n".join(lines)
    if subject_key == "source_degraded":
        title = "Adatforrás hiba" if hu else "Data source degraded"
        body = (
            "Egy adatforrás frissítése sikertelen volt. Az alkalmazás megtartotta az utolsó "
            "ellenőrzött adatokat. A részletek a Diagnosztika oldalon láthatók."
            if hu
            else "A data source refresh failed. The application kept the last verified data. "
            "See Diagnostics for details."
        )
        return title, body
    title = subject_key.replace("_", " ").title()
    return title, json.dumps(payload, ensure_ascii=False, indent=2, default=str)


def send_webhook(db: Session, subject_key: str, payload: dict) -> dict:
    settings = get_settings()
    if not settings.notify_webhook_url:
        return {"ok": True, "skipped": True, "reason": "NOTIFY_WEBHOOK_URL is not configured"}

    event = _record(db, "webhook", subject_key, payload)
    try:
        request_with_retry(
            "POST",
            settings.notify_webhook_url,
            timeout=settings.http_timeout_seconds,
            json=payload,
        )
        _finish(db, event)
        return {"ok": True}
    except Exception as exc:
        # Webhook URLs often contain credentials. Do not persist the raw exception URL.
        _finish(db, event, error=f"Webhook delivery failed: {type(exc).__name__}")
        return {"ok": False, "error": "Webhook delivery failed"}


def send_telegram(db: Session, subject_key: str, payload: dict) -> dict:
    settings = get_settings()
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        return {"ok": True, "skipped": True, "reason": "Telegram is not configured"}

    event = _record(db, "telegram", subject_key, payload)
    _, text = notification_text(subject_key, payload, settings.app_default_language)
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    try:
        request_with_retry(
            "POST",
            url,
            timeout=settings.http_timeout_seconds,
            json={"chat_id": settings.telegram_chat_id, "text": text, "disable_web_page_preview": True},
        )
        _finish(db, event)
        return {"ok": True}
    except Exception as exc:
        # Never store an exception containing the bot-token URL.
        _finish(db, event, error=f"Telegram delivery failed: {type(exc).__name__}")
        return {"ok": False, "error": "Telegram delivery failed"}


def send_email(db: Session, subject_key: str, payload: dict) -> dict:
    settings = get_settings()
    if not settings.smtp_host or not settings.smtp_from or not settings.notify_email_to:
        return {"ok": True, "skipped": True, "reason": "Email is not configured"}

    event = _record(db, "email", subject_key, payload)
    subject, body = notification_text(subject_key, payload, settings.app_default_language)
    message = EmailMessage()
    message["Subject"] = f"Real Estate Watch · {subject}"
    message["From"] = settings.smtp_from
    message["To"] = settings.notify_email_to
    message.set_content(body)

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=settings.http_timeout_seconds) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.ehlo()
            if settings.smtp_username:
                smtp.login(settings.smtp_username, settings.smtp_password or "")
            smtp.send_message(message)
        _finish(db, event)
        return {"ok": True}
    except Exception as exc:
        _finish(db, event, error=f"Email delivery failed: {type(exc).__name__}")
        return {"ok": False, "error": "Email delivery failed"}


def send_notifications(db: Session, subject_key: str, payload: dict) -> dict:
    """Send through every configured channel without one channel blocking the others."""
    results = {
        "webhook": send_webhook(db, subject_key, payload),
        "telegram": send_telegram(db, subject_key, payload),
        "email": send_email(db, subject_key, payload),
    }
    attempted = [value for value in results.values() if not value.get("skipped")]
    return {
        "ok": all(value.get("ok", False) for value in attempted) if attempted else True,
        "channels": results,
    }
