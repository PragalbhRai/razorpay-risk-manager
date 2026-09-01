from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    redis_url: str


settings = Settings()