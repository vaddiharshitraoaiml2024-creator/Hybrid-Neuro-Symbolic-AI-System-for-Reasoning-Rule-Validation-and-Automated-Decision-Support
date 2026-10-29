from pydantic_settings import BaseSettings, SettingsConfigDict
class Settings(BaseSettings):
    app_secret: str = "change-me"
    database_path: str = "./data/app.sqlite3"
    frontend_url: str = "http://localhost:5173"
    cookie_secure: bool = False
    max_upload_mb: int = 10
    ai_api_key: str = ""
    ai_base_url: str = "https://api.openai.com/v1"
    ai_model: str = "gpt-4o-mini"
    github_client_id: str = ""
    github_client_secret: str = ""
    github_callback_url: str = "http://localhost:8000/api/github/callback"
    github_api_url: str = "https://api.github.com"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
settings = Settings()
