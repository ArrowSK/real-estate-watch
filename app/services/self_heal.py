from sqlalchemy.orm import Session

from app.config import get_settings
from app.services.market import ensure_seed_market_data


def heal_reference_data(db: Session) -> dict:
    settings = get_settings()
    if not settings.self_heal_enabled:
        return {"enabled": False, "actions": []}

    actions: list[str] = []
    inserted = ensure_seed_market_data(db)
    if inserted:
        actions.append(f"restored {inserted} missing bundled KSH reference observations")
    return {"enabled": True, "actions": actions}
