from typing import Optional
from urllib.parse import quote

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
    API_PUBLIC_BASE_URL: Optional[str] = Field(
        default=None,
        description="Public API base URL including version prefix, e.g. https://example.com/api/v1",
    )

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
    DATABASE_URL: str = Field(
        default="",
        description="Database URL (must be provided via environment in deployed environments)",
    )

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
    MINIO_PRESIGNED_URL_EXPIRY_SECONDS: int = Field(
        default=3600,
        ge=1,
        le=7 * 24 * 60 * 60,
        description="Expiry for presigned MinIO object URLs in seconds",
    )

    IMAGE_MAX_UPLOAD_SIZE_BYTES: int = Field(
        default=5 * 1024 * 1024,
        description="Max accepted image upload size in bytes (default 5MB)",
    )

    # Observability (OpenTelemetry tracing -> OTel Collector -> Tempo)
    OTEL_EXPORTER_OTLP_ENDPOINT: Optional[str] = Field(
        default=None,
        description="OTel Collector OTLP/gRPC endpoint (e.g. otel-collector:4317). "
        "Tracing is disabled entirely when unset, so local dev without the "
        "observability stack running is unaffected.",
    )
    OTEL_SERVICE_NAME: str = Field(
        default="api",
        description="Service name reported on spans from this process. Overridden "
        "per Celery worker role (worker-student/worker-bulk/worker-poller) via "
        "docker-compose.yml so each shows up as a distinct service on a trace.",
    )
    OTEL_TRACES_SAMPLER_RATIO: float = Field(
        default=1.0,
        description="Head-sample ratio (0-1) applied before spans reach the "
        "collector. The collector's tail_sampling policy (observability/"
        "otel-collector-config.yaml) makes the real keep/drop decision; this is "
        "just a cap so a runaway baseline can't flood it.",
    )

    # Grafana <-> Keycloak SSO (Grafana is the only observability service with
    # a published port; gated by a dedicated confidential client in the
    # existing realm instead of a separate credential set)
    GRAFANA_KEYCLOAK_CLIENT_ID: Optional[str] = Field(
        default=None, description="Keycloak client ID used for Grafana SSO"
    )
    GRAFANA_KEYCLOAK_CLIENT_SECRET: Optional[str] = Field(
        default=None, description="Keycloak client secret used for Grafana SSO"
    )

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

    # Judge0 execution limits (global safety caps).
    # Per-problem limits (Question.time_limit_ms / memory_limit_mb) are clamped
    # by these values before being sent to Judge0.
    JUDGE0_MAX_CPU_TIME: float = Field(
        default=15.0,
        description="Maximum CPU time limit (seconds) allowed per testcase execution",
    )
    JUDGE0_MAX_WALL_TIME: float = Field(
        default=20.0,
        description="Maximum wall-clock time limit (seconds) allowed per testcase execution",
    )
    JUDGE0_MAX_MEMORY_KB: int = Field(
        default=512000,
        description="Maximum memory limit (KB) allowed per testcase execution",
    )
    JUDGE0_MIN_MEMORY_KB: int = Field(
        default=65536,
        description=(
            "Minimum memory limit (KB) applied as a floor after problem/default "
            "limits. Judge0's API itself only requires >=2048, but that is far "
            "too little for real runtimes to even start (the JVM alone needs "
            "tens of MB) -- a too-low per-problem value would otherwise make "
            "every submission fail with a false Runtime/Memory Limit Error "
            "before the submitted code ever runs."
        ),
    )
    JUDGE0_STACK_LIMIT_KB: int = Field(
        default=64000, description="Stack size limit (KB) applied to every execution"
    )
    JUDGE0_DEFAULT_CPU_TIME: float = Field(
        default=5.0,
        description="Fallback CPU time limit (seconds) when a problem defines none",
    )
    JUDGE0_DEFAULT_MEMORY_KB: int = Field(
        default=256000,
        description="Fallback memory limit (KB) when a problem defines none",
    )
    JUDGE0_WALL_TIME_FACTOR: float = Field(
        default=2.0,
        description="Wall-time limit = cpu_time_limit * this factor (then capped)",
    )

    # Judge0 batching & backpressure
    JUDGE0_BATCH_SIZE: int = Field(
        default=20,
        description="Number of submissions/tokens per Judge0 batch submit/get call",
    )
    JUDGE0_MAX_INFLIGHT: int = Field(
        default=100,
        description="Global cap on submissions awaiting Judge0 results (backpressure gate)",
    )

    # Evaluation pipeline backpressure
    EVAL_MAX_CONCURRENT_TESTCASES: int = Field(
        default=10,
        description="Max concurrent Judge0 submit calls per submission (fallback path)",
    )
    EVAL_MAX_ACTIVE_TASKS_PER_CONTEST: int = Field(
        default=50,
        description="Max concurrent in-flight submissions per contest for bulk evaluation",
    )
    EVAL_POLL_INTERVAL_SECONDS: float = Field(
        default=1.5, description="Cadence of the Celery Beat result poller (seconds)"
    )
    EVAL_SUBMISSION_DEADLINE_SECONDS: int = Field(
        default=120,
        description="Per-submission deadline; past this the poller force-persists a timeout",
    )
    EVAL_BACKPRESSURE_RETRY_SECONDS: int = Field(
        default=5,
        description="Countdown (seconds) before retrying a submit task blocked by backpressure",
    )
    JUDGE0_TRANSIENT_MAX_RETRIES: int = Field(
        default=8,
        description="Max retries for transient Judge0 failures (timeout/connection/503) "
        "before a submission is given up on and recorded as SYSTEM_ERROR",
    )
    JUDGE0_TRANSIENT_RETRY_MAX_BACKOFF_SECONDS: int = Field(
        default=60,
        description="Cap on the exponential backoff countdown between transient Judge0 retries",
    )

    # Celery worker concurrency (applied via worker launch flags; documented here)
    CELERY_STUDENT_CONCURRENCY: int = Field(
        default=8, description="Worker concurrency for the student_submit queue"
    )
    CELERY_BULK_CONCURRENCY: int = Field(
        default=4,
        description="Worker concurrency for the bulk_contest_evaluation queue",
    )

    # API rate limiting (per authenticated user) for endpoints that fan out to
    # Judge0. These are the only unthrottled surfaces a single student could
    # otherwise hammer to flood the judge queue or run up Judge0 usage.
    RATE_LIMIT_RUN_TIMES: int = Field(
        default=10,
        description="Max practice/sample 'run code' requests per user per RATE_LIMIT_RUN_SECONDS",
    )
    RATE_LIMIT_RUN_SECONDS: int = Field(
        default=10,
        description="Time window (seconds) for RATE_LIMIT_RUN_TIMES",
    )
    RATE_LIMIT_SUBMIT_TIMES: int = Field(
        default=5,
        description="Max contest 'submit code' requests per user per RATE_LIMIT_SUBMIT_SECONDS",
    )
    RATE_LIMIT_SUBMIT_SECONDS: int = Field(
        default=10,
        description="Time window (seconds) for RATE_LIMIT_SUBMIT_TIMES",
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

    @property
    def REDIS_URL(self) -> str:  # noqa: N802
        """Construct Redis URL from individual parameters."""
        if not self.REDIS_HOST:
            return "redis://localhost:6379/0"

        password_part = (
            f":{quote(self.REDIS_PASSWORD, safe='')}@" if self.REDIS_PASSWORD else ""
        )
        port = self.REDIS_PORT or 6379
        db = self.REDIS_DB or 0
        return f"redis://{password_part}{self.REDIS_HOST}:{port}/{db}"


config = Config()
