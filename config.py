from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    groq_api_key: str
    tavily_api_key: str
    mysql_host: str 
    mysql_user: str 
    mysql_password: str
    mysql_database: str 

    class Config:
        env_file = ".env"

settings = Settings()