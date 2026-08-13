import argparse
import json

from app.db import SessionLocal, init_db
from app.jobs import run_daily_collection
from app.services.fx import refresh_mnb_fx
from app.services.health import run_self_checks
from app.services.market import ensure_seed_market_data, refresh_ksh
from app.services.self_heal import heal_reference_data


def main() -> int:
    parser = argparse.ArgumentParser(description="Real Estate Watch operations")
    parser.add_argument(
        "command",
        choices=["seed", "collect-market", "collect-fx", "daily", "self-check", "heal"],
    )
    args = parser.parse_args()
    init_db()
    with SessionLocal() as db:
        if args.command == "seed":
            result = {"ok": True, "seeded": ensure_seed_market_data(db)}
        elif args.command == "collect-market":
            result = refresh_ksh(db)
        elif args.command == "collect-fx":
            result = refresh_mnb_fx(db)
        elif args.command == "daily":
            result = run_daily_collection(db)
        elif args.command == "heal":
            result = heal_reference_data(db)
        else:
            checks = run_self_checks(db)
            result = {"ok": all(x["ok"] or x.get("soft") for x in checks), "checks": checks}
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0 if result.get("ok", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
