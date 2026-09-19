from functools import lru_cache
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator, model_validator


class Settings(BaseSettings):
    # Application
    APP_NAME: str = "BYC AI Command & Control Platform"
    APP_ENV: str = "development"
    DEBUG: bool = True
    PORT: int = 8000
    HOST: str = "0.0.0.0"
    API_V1_STR: str = "/api/v1"

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/main_crowd_ai"
    DATABASE_SYNC_URL: str = "postgresql://postgres:postgres@localhost:5432/main_crowd_ai"
    DB_POOL_SIZE: int = 40
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_TIMEOUT: int = 15

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # JWT Authentication
    JWT_SECRET_KEY: str = "byc_super_secret_jwt_key_khairatabad_2026_production_change_me"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Internal AI Service API Key
    AI_SERVICE_API_KEY: str = "byc_ai_internal_service_token_2026"

    # CORS
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:5174,http://127.0.0.1:5173,http://127.0.0.1:5174"

    # Media Storage
    MEDIA_ROOT: str = "media"
    STORAGE_TYPE: str = "local"

    # Feature Flags
    FRS_ENABLED: bool = True
    AI_ENABLED: bool = True
    RTSP_ENABLED: bool = False
    PREDICTIONS_ENABLED: bool = True

    # FRS Production Thresholds
    FRS_MATCH_THRESHOLD: float = 0.72
    FRS_DET_THRESHOLD: float = 0.50
    FRS_MIN_FACE_SIZE: int = 60
    FRS_MIN_SHARPNESS: float = 45.0
    FRS_MAX_YAW_ANGLE: float = 35.0

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    @model_validator(mode="after")
    def validate_production_security(self) -> "Settings":
        if self.APP_ENV == "production" and "change_me" in self.JWT_SECRET_KEY:
            import secrets, logging
            self.JWT_SECRET_KEY = secrets.token_hex(32)
            logging.getLogger("uvicorn").critical(
                "[SECURITY] Default JWT_SECRET_KEY was detected in production! "
                "Generated a secure random key to prevent token forgery. "
                "Ensure JWT_SECRET_KEY is explicitly defined in your production .env"
            )
        return self

    @property
    def cors_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
