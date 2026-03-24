from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ENVIRONMENT: str = "development"
    SECRET_KEY: str = "dev-secret-key-change-in-production"
    LOG_LEVEL: str = "INFO"

    DATABASE_URL: str = "sqlite:///./columbia_events.db"

    GEOCODIO_API_KEY: str = ""
    SENTRY_DSN: str = ""

    # Scraper defaults
    DEFAULT_SCRAPE_INTERVAL_HOURS: int = 6
    SCRAPER_REQUEST_DELAY_SECONDS: float = 1.0
    SCRAPER_USER_AGENT: str = (
        "Columbia-Events-Aggregator/1.0 (+https://events.columbia.edu)"
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
