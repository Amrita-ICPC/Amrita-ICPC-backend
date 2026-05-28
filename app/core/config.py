from typing import Optional

from dotenv import load_dotenv
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings

load_dotenv()


class Config(BaseSettings):
    """Configuration class using Pydantic BaseSettings for validation and environment variable management."""

    # Project Configurations
    PROJECT_NAME: str = Field(
        default="Amrita ICPC Coding Platform - Backend",
        description="Name of the project",
    )
    PROJECT_DESCRIPTION: str = Field(
        default="A backend tool for Amrita ICPC Coding Platform",
        description="Description of the project",
    )
    VERSION: str = Field(default="1.0.0", description="Version of the application")

    # Environment Configuration
    ENVIRONMENT: str = Field(
        default="production",
        description="Environment of the application",
    )
    MIGRATIONS_ENABLED: bool = Field(
        default=False,
        description="Whether migrations are enabled (true) or schema sync is used (false)",
    )

    # API Configurations
    API_HOST: str = Field(default="127.0.0.1", description="API host")
    API_PORT: int = Field(default=8000, description="API port")
    API_PREFIX: str = Field(default="/api", description="API prefix")

    # Database Configuration
    DATABASE_NAME: Optional[str] = Field(default=None, description="Database name")
    DATABASE_USERNAME: Optional[str] = Field(
        default=None, description="Database username"
    )
    DATABASE_PASSWORD: Optional[str] = Field(
        default=None, description="Database password"
    )
    DATABASE_HOST: str = Field(default="localhost", description="Database host")
    DATABASE_PORT: Optional[int] = Field(default=5432, description="Database port")
    DATABASE_POOL_SIZE: int = Field(default=5, description="Database pool size")
    DATABASE_MAX_OVERFLOW: int = Field(default=10, description="Database max overflow")
    DATABASE_URL: str = Field(default="postgresql+psycopg2://postgres:postgres@localhost:5432/postgres", description="Database URL")

    # Redis configuration
    REDIS_HOST: Optional[str] = Field(default=None, description="Redis host")
    REDIS_PORT: Optional[int] = Field(default=6379, description="Redis port")
    REDIS_PASSWORD: Optional[str] = Field(default=None, description="Redis password")
    REDIS_DB: Optional[int] = Field(default=0, description="Redis database")

    CACHE_ENABLED: Optional[bool] = Field(default=True, description="Cache enabled")

    # MinIO configuration
    MINIO_HOST: str = Field(default="localhost", description="MinIO host")
    MINIO_PORT: int = Field(default=9000, description="MinIO API port")
    MINIO_CONSOLE_PORT: int = Field(default=9001, description="MinIO console port")
    MINIO_ACCESS_KEY: Optional[str] = Field(
        default=None, description="MinIO access key"
    )
    MINIO_SECRET_KEY: Optional[str] = Field(
        default=None, description="MinIO secret key"
    )
    MINIO_BUCKET_NAME: str = Field(
        default="amrita-icpc", description="Default MinIO bucket name"
    )
    MINIO_SECURE: bool = Field(default=False, description="Use HTTPS for MinIO")

    # Log Configuration
    LOG_LEVEL: str = Field(default="INFO", description="Log level")
    LOG_FORMAT: str = Field(
        default="{asctime} {levelname} {message}",
        description="Log format",
    )
    LOG_DIR: Optional[str] = Field(default=None, description="Log directory")
    USE_RICH_LOGGING: bool = Field(default=True, description="Use Rich logging")

    # Judge0 Configuration
    JUDGE0_API_KEY: Optional[str] = Field(default=None, description="Judge0 API key")
    JUDGE0_API_URL: Optional[str] = Field(
        default="https://api.judge0.com",
        description="Judge0 API URL",
    )
    JUDGE0_API_TIMEOUT: Optional[int] = Field(
        default=30, description="Judge0 API timeout"
    )

    # Keycloak Configuration
    KEYCLOAK_SERVER_URL: str = Field(
        default="http://localhost:8080",
        description="Keycloak Server URL",
    )
    KEYCLOAK_REALM: str = Field(default="master", description="Keycloak Realm")
    KEYCLOAK_CLIENT_ID: str = Field(
        default="amrita-icpc-backend",
        description="Keycloak Client ID",
    )
    KEYCLOAK_CLIENT_SECRET: Optional[str] = Field(
        default=None, description="Keycloak Client Secret"
    )

    KEYCLOAK_USERS_SYNC_CLIENT_ID: str = Field(
        default="amrita-icpc-backend",
        description="Keycloak Users Sync Client ID",
    )

    KEYCLOAK_USERS_SYNC_CLIENT_SECRET: Optional[str] = Field(
        default=None,
        description="Keycloak Users Sync Client Secret",
    )

    @field_validator("LOG_LEVEL")
    def validate_log_level(cls, value):
        if value not in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
            raise ValueError("Invalid log level")
        return value

    @field_validator("ENVIRONMENT")
    def validate_environment(cls, value):
        if value not in ["development", "staging", "production"]:
            raise ValueError("Invalid environment")
        return value


config = Config()
