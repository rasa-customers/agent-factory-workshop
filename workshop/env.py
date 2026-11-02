"""Workshop settings, read from .env (and .env.local for overrides)."""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", ".env.local"), extra="ignore")

    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    rasa_license: str | None = None
    deepgram_api_key: str | None = None
    factory_model: str = "gpt-5.2"
    dashboard_url: str = "http://localhost:8600"
    public_host: str = "localhost"


def load_settings() -> Settings:
    return Settings()


def check_settings(s: Settings) -> list[str]:
    problems: list[str] = []
    if not s.openai_api_key:
        problems.append("OPENAI_API_KEY is not set — copy your workshop key from the portal into .env.")
    if not s.openai_base_url.rstrip("/").endswith("/v1"):
        problems.append(f"OPENAI_BASE_URL should end with /v1 (got {s.openai_base_url!r}).")
    if not s.rasa_license:
        problems.append("RASA_LICENSE is not set — get a free developer license (link on the portal) and add it to .env.")
    return problems


def export_settings(settings: "Settings | None" = None) -> None:
    """Put settings (from .env/.env.local and defaults) into os.environ so child processes —
    rasa, which expands ${FACTORY_MODEL} etc. in YAML — see them. Never overrides what's already set."""
    import os
    s = settings or load_settings()
    for k, v in s.model_dump().items():
        if v is not None and k.upper() not in os.environ:
            os.environ[k.upper()] = str(v)
    from dotenv import dotenv_values  # extra keys (e.g. the *_PUBLIC_URLs a cloud machine gets) pass through too
    for name in (".env", ".env.local"):
        for k, v in dotenv_values(name).items():
            if v is not None and k not in os.environ:
                os.environ[k] = v
