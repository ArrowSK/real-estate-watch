from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    app_default_language: str = "en"
    app_timezone: str = "Europe/Budapest"
    app_log_level: str = "INFO"

    database_url: str = "sqlite:///./real_estate_watch.db"

    http_timeout_seconds: float = 20.0
    source_stale_hours: int = 36
    self_heal_enabled: bool = True

    notify_webhook_url: str | None = None
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from: str | None = None
    notify_email_to: str | None = None
    market_notify_change_percent: float = 1.0
    admin_key: str | None = None

    # Official Hungary sources.
    ksh_market_url: str = "https://www.ksh.hu/stadat_files/lak/en/lak0052.html"
    ksh_transactions_url: str = "https://www.ksh.hu/stadat_files/lak/en/lak0053.html"
    ksh_local_base_url: str = "https://www.ksh.hu/s/ingatlanadattar/adattar"
    ksh_local_year: int = 2024
    ksh_local_streets_enabled: bool = True
    ksh_local_refresh_hours: int = 168
    mnb_fx_url: str = "https://www.mnb.hu/arfolyamok"

    # Duna House is an observed asking-market subset, not a complete market feed. Collection
    # always starts with the policy gate in app/countries/hu/providers/duna_house.py.
    duna_house_enabled: bool = True
    duna_house_robots_url: str = "https://dh.hu/robots.txt"
    duna_house_legal_url: str = "https://dh.hu/jogi-nyilatkozat"
    duna_house_sitemap_url: str = (
        "https://newdhapi01.dh.hu/api/getFileItem/sitemap_properties"
    )
    duna_house_daily_page_limit: int = 350
    duna_house_fresh_days: int = 14
    duna_house_request_delay_seconds: float = 0.12
    duna_house_inactive_after_misses: int = 2
    duna_house_min_aggregate_sample: int = 8

    def sqlalchemy_url(self) -> str:
        url = self.database_url.strip()
        if url.startswith("postgres://"):
            return "postgresql+psycopg://" + url.removeprefix("postgres://")
        if url.startswith("postgresql://") and "+psycopg" not in url:
            return "postgresql+psycopg://" + url.removeprefix("postgresql://")
        return url


@lru_cache
def get_settings() -> Settings:
    return Settings()
