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

    ksh_market_url: str = "https://www.ksh.hu/stadat_files/lak/en/lak0052.html"
    ksh_transactions_url: str = "https://www.ksh.hu/stadat_files/lak/en/lak0053.html"
    mnb_fx_url: str = "https://www.mnb.hu/arfolyamok.asmx"

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
