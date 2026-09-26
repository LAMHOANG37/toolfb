from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    app_env: str = "development"
    database_url: str = "sqlite:///./newsroom.db"
    
    # LLM
    llm_provider: str = "gemini"
    gemini_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    
    # Facebook
    facebook_page_id: Optional[str] = None
    facebook_page_access_token: Optional[str] = None
    facebook_graph_api_version: str = "v20.0"
    facebook_dry_run: bool = True
    
    # Editor Settings
    auto_publish: bool = False

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

settings = Settings()
