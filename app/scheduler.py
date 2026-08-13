"""Small local scheduler for Docker users.

Railway should use its native Cron Jobs instead. This process exists only for environments
where a host scheduler is inconvenient. It sleeps between runs and does no polling work.
"""

import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.config import get_settings
from app.db import SessionLocal, init_db
from app.jobs import run_daily_collection


def seconds_until_next_run(hour: int = 4, minute: int = 15) -> float:
    tz = ZoneInfo(get_settings().app_timezone)
    now = datetime.now(tz)
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return max((target - now).total_seconds(), 1.0)


def main() -> None:
    init_db()
    while True:
        time.sleep(seconds_until_next_run())
        with SessionLocal() as db:
            run_daily_collection(db)


if __name__ == "__main__":
    main()
