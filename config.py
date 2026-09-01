from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    groq_api_key: str
    tavily_api_key: str = ""

    # MSSQL Settings
    mssql_server: str = "192.168.0.163,1433"
    mssql_database: str = "H022-KonnectLIS_Test"
    mssql_user: str = "sa"
    mssql_password: str = ""

    class Config:
        env_file = ".env"
        extra = "ignore"          # ← This is important

settings = Settings()