from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / "data"
AGENT_SYSTEM_DIR = PROJECT_ROOT / ".workbuddy" / "system"
AGENT_SKILLS_DIR = AGENT_SYSTEM_DIR / "skills"
SCHEMAS_DIR = PROJECT_ROOT / "schemas"
CONFIG_DIR = PROJECT_ROOT / "config"
TEMPLATES_DIR = PROJECT_ROOT / "templates"


class Settings(BaseSettings):
    app_secret_key: str = "change-me-in-production"
    database_url: str = f"sqlite:///{DATA_DIR / 'app.db'}"
    senseaudio_base_url: str = "https://api.senseaudio.cn"
    senseaudio_chat_endpoint: str = "/v1/chat/completions"
    senseaudio_model: str = "senseaudio-s2"
    access_token_expire_minutes: int = 60 * 24 * 7

    model_config = SettingsConfigDict(env_file=str(PROJECT_ROOT / ".env"), env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return Settings()
