from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Настройки приложения"""
    
    # API
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    API_PREFIX: str = "/api/v1"
    
    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./deployments.db"
    # Для PostgreSQL: postgresql+asyncpg://user:password@localhost:5432/sdp
    
    # Redis/Celery
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/0"
    
    # File storage
    UPLOAD_DIR: str = "/tmp/sdp_uploads"
    MAX_UPLOAD_SIZE: int = 2 * 1024 * 1024 * 1024  # 2GB
    
    # Tools paths
    TRIVY_PATH: str = "trivy"
    HADOLINT_PATH: str = "hadolint"
    ANSIBLE_BASE_DIR: str = "/app/ansible"
    
    # Security
    SECRET_KEY: str = "change-me-in-production"
    
    class Config:
        env_file = ".env"


settings = Settings()
