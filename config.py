from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    groq_api_key: str
    tavily_api_key: str = ""
    
    mysql_host: str = "localhost"
    mysql_user: str = "root"
    mysql_password: str = ""
    mysql_database: str = "hospital_demo"

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()