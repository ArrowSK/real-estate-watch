from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import MarketSnapshot
from app.services.market import ensure_seed_market_data


def heal_reference_data(db: Session) -> dict:
    settings = get_settings()
    if not settings.self_heal_enabled:
        return {"enabled": False, "actions": []}

    actions: list[str] = []
    market_count = db.scalar(select(func.count()).select_from(MarketSnapshot)) or 0
    if market_count == 0:
        inserted = ensure_seed_market_data(db)
        actions.append(f"restored {inserted} bundled KSH reference observations")
    return {"enabled": True, "actions": actions}
