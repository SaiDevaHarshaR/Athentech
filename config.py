from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    groq_api_key: str
    tavily_api_key: str = ""

    # --- LLM provider selection ---
    # Defaults to "groq" so nothing changes unless you explicitly set this.
    # Set LLM_PROVIDER=openai or LLM_PROVIDER=anthropic in .env to switch.
    llm_provider: str = "groq"
    llm_model: str = ""  # optional override; blank = provider's default model below
    openai_api_key: str = ""
    anthropic_api_key: str = ""

    # MSSQL Settings
    mssql_server: str = "192.168.0.163,1433"
    mssql_database: str = "H022-KonnectLIS_Test"
    mssql_user: str = "sa"
    mssql_password: str = ""

    # --- Admin auth ---
    # Set these in .env. Generate admin_password_hash with auth/generate_admin_hash.py
    admin_username: str = "admin"
    admin_password_hash: str = ""  # sha256 hex digest of the admin password
    admin_secret_key: str = ""     # random long string, used to sign session tokens

    # --- CORS ---
    # Comma-separated list of origins allowed to call this API.
    # Add your production website origin(s) here, e.g.:
    # "https://athentech.in,https://www.athentech.in,http://127.0.0.1:5500"
    allowed_origins: str = "http://127.0.0.1:5500,http://localhost:5500,http://127.0.0.1:5501,http://localhost:5501"

    class Config:
        env_file = ".env"
        extra = "ignore"          # ← This is important

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


settings = Settings()