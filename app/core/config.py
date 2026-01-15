from typing import Optional

from dotenv import load_dotenv
from pydantic import Field, validator
from pydantic_settings import BaseSettings

load_dotenv()


class Config(BaseSettings):
    """Configuration class using Pydantic BaseSettings for validation and environment variable management."""

    # Project Configurations
    PROJECT_NAME: str = Field(
        default="Amrita ICPC Coding Platform - Backend",
        env="PROJECT_NAME",
        description="Name of the project",
    )
    PROJECT_DESCRIPTION: str = Field(
        default="A backend tool for Amrita ICPC Coding Platform",
        env="PROJECT_DESCRIPTION",
        description="Description of the project",
    )
    VERSION: str = Field(
        default="1.0.0", env="VERSION", description="Version of the application"
    )

    # Environment Configuration
    ENVIRONMENT: str = Field(
        default="development",
        env="ENVIRONMENT",
        description="Environment of the application",
    )

    # API Configurations
    API_HOST: str = Field(default="127.0.0.1", env="API_HOST", description="API host")
    API_PORT: int = Field(default=8000, env="API_PORT", description="API port")
    API_PREFIX: str = Field(default="/api", env="API_PREFIX", description="API prefix")

    # Database Configuration
    DATABASE_NAME: Optional[str] = Field(
        default=None, env="DATABASE_NAME", description="Database name"
    )
    DATABASE_USERNAME: Optional[str] = Field(
        default=None, env="DATABASE_USERNAME", description="Database username"
    )
    DATABASE_PASSWORD: Optional[str] = Field(
        default=None, env="DATABASE_PASSWORD", description="Database password"
    )
    DATABASE_HOST: str = Field(
        default="localhost", env="DATABASE_HOST", description="Database host"
    )
    DATABASE_PORT: Optional[int] = Field(
        default=5432, env="DATABASE_PORT", description="Database port"
    )
    DATABASE_POOL_SIZE: int = Field(
        default=5, env="DATABASE_POOL_SIZE", description="Database pool size"
    )
    DATABASE_MAX_OVERFLOW: int = Field(
        default=10, env="DATABASE_MAX_OVERFLOW", description="Database max overflow"
    )

    # Redis configuration
    REDIS_HOST: Optional[str] = Field(
        default=None, env="REDIS_HOST", description="Redis host"
    )
    REDIS_PORT: Optional[int] = Field(
        default=6379, env="REDIS_PORT", description="Redis port"
    )
    REDIS_PASSWORD: Optional[str] = Field(
        default=None, env="REDIS_PASSWORD", description="Redis password"
    )
    REDIS_DB: Optional[int] = Field(
        default=0, env="REDIS_DB", description="Redis database"
    )

    # Log Configuration
    LOG_LEVEL: str = Field(default="INFO", env="LOG_LEVEL", description="Log level")
    LOG_FORMAT: str = Field(
        default="{asctime} {levelname} {message}",
        env="LOG_FORMAT",
        description="Log format",
    )
    LOG_DIR: Optional[str] = Field(
        default=None, env="LOG_DIR", description="Log directory"
    )
    USE_RICH_LOGGING: bool = Field(
        default=True, env="USE_RICH_LOGGING", description="Use Rich logging"
    )

    # Judge0 Configuration
    JUDGE0_API_KEY: Optional[str] = Field(
        default=None, env="JUDGE0_API_KEY", description="Judge0 API key"
    )
    JUDGE0_API_URL: Optional[str] = Field(
        default="https://api.judge0.com",
        env="JUDGE0_API_URL",
        description="Judge0 API URL",
    )
    JUDGE0_API_TIMEOUT: Optional[int] = Field(
        default=30, env="JUDGE0_API_TIMEOUT", description="Judge0 API timeout"
    )

    # Keycloak Configuration
    KEYCLOAK_SERVER_URL: str = Field(
        default="http://localhost:8080",
        env="KEYCLOAK_SERVER_URL",
        description="Keycloak Server URL",
    )
    KEYCLOAK_REALM: str = Field(
        default="master", env="KEYCLOAK_REALM", description="Keycloak Realm"
    )
    KEYCLOAK_CLIENT_ID: str = Field(
        default="amrita-icpc-backend",
        env="KEYCLOAK_CLIENT_ID",
        description="Keycloak Client ID",
    )
    KEYCLOAK_CLIENT_SECRET: Optional[str] = Field(
        default=None, env="KEYCLOAK_CLIENT_SECRET", description="Keycloak Client Secret"
    )

    @validator("LOG_LEVEL")
    def validate_log_level(cls, value):
        if value not in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
            raise ValueError("Invalid log level")
        return value

    @validator("ENVIRONMENT")
    def validate_environment(cls, value):
        if value not in ["development", "staging", "production"]:
            raise ValueError("Invalid environment")
        return value


config = Config()
