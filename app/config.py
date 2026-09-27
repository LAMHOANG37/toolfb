from pathlib import Path
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    app_env: str = "development"
    database_url: str = "sqlite:///./newsroom.db"
    admin_username: str = "admin"
    admin_password: SecretStr = SecretStr("")
    secret_key: SecretStr = SecretStr("")
    cookie_secure: bool = False
    timezone: str = "Asia/Ho_Chi_Minh"
    llm_provider: str = "gemini"
    llm_model: str = ""
    gemini_api_key: SecretStr = SecretStr("")
    openai_api_key: SecretStr = SecretStr("")
    facebook_page_id: str = ""
    facebook_page_access_token: SecretStr = SecretStr("")
    facebook_graph_api_version: str = ""
    facebook_dry_run: bool = True
    auto_publish: bool = False
    scheduler_enabled: bool = True
    scan_interval_minutes: int = Field(default=0, ge=0)
    card_font_path: str = ""
    model_config = SettingsConfigDict(env_file=ROOT / ".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
