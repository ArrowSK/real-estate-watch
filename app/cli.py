import argparse
import json

from app.countries.hu.providers.duna_house import check_provider_policy, collect_duna_house
from app.db import SessionLocal, init_db
from app.jobs import run_daily_collection
from app.services.fx import refresh_mnb_fx
from app.services.health import run_self_checks
from app.services.ksh_local import refresh_ksh_local
from app.services.market import ensure_seed_market_data, refresh_ksh
from app.services.market_intelligence import refresh_observed_market_aggregates
from app.services.self_heal import heal_reference_data
from app.services.transaction_counts import refresh_ksh_transaction_counts


def main() -> int:
    parser = argparse.ArgumentParser(description="Real Estate Watch operations")
    parser.add_argument(
        "command",
        choices=[
            "seed",
            "collect-market",
            "collect-counts",
            "collect-local",
            "collect-fx",
            "collect-observed",
            "aggregate-observed",
            "check-dh-provider",
            "daily",
            "self-check",
            "heal",
        ],
    )
    parser.add_argument(
        "--no-streets",
        action="store_true",
        help="For collect-local, update district rows without fetching street pages.",
    )
    parser.add_argument(
        "--contract-only",
        action="store_true",
        help="For live-provider checks, fetch only the minimum sample needed to verify parsing.",
    )
    args = parser.parse_args()
    init_db()
    with SessionLocal() as db:
        if args.command == "seed":
            result = {"ok": True, "seeded": ensure_seed_market_data(db)}
        elif args.command == "collect-market":
            result = refresh_ksh(db)
        elif args.command == "collect-counts":
            result = refresh_ksh_transaction_counts(db)
        elif args.command == "collect-local":
            result = refresh_ksh_local(
                db,
                include_streets=not args.no_streets,
                force=True,
                contract_only=args.contract_only,
            )
        elif args.command == "collect-fx":
            result = refresh_mnb_fx(db)
        elif args.command == "collect-observed":
            result = collect_duna_house(db, contract_only=args.contract_only)
        elif args.command == "aggregate-observed":
            result = refresh_observed_market_aggregates(db)
        elif args.command == "check-dh-provider":
            result = check_provider_policy(db)
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
