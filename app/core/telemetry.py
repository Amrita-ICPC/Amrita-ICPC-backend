"""OpenTelemetry tracing setup: SDK/exporter wiring, auto-instrumentation, and
trace-id log correlation.

Mirrors the app/core/clients/*.py init_*() pattern, but split into a few
narrow entry points instead of one init_telemetry() because each targets a
different object that's only available at a different point in startup:

- setup_telemetry(): process-wide SDK setup + instrumentations that patch a
  library globally (httpx, redis, logging). Call once per process, as early
  as possible -- FastAPI's lifespan for the api process, Celery's
  worker_process_init signal for each worker role (see
  app/core/clients/celery.py).
- instrument_fastapi_app(): needs the FastAPI app instance (api process only).
- instrument_sqlalchemy_engine(): needs the SQLAlchemy engine instance.
  Called once at import time in app/core/clients/database.py, which every
  process (api + all Celery roles) imports, so this covers all of them.

Spans/logs ship via OTLP to the OpenTelemetry Collector
(observability/otel-collector-config.yaml), which owns the actual sampling
decision (tail_sampling: all errors/slow spans, a probabilistic slice of the
rest). OTEL_TRACES_SAMPLER_RATIO here is a head-sample cap so a runaway
baseline can't flood the collector before it gets to decide.
"""

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased

from app.core.config import config
from app.core.logger import logger

_telemetry_initialized = False
_sqlalchemy_instrumented = False


def setup_telemetry(service_name: str) -> None:
    """Configure the OTel SDK for this process and instrument httpx/redis/logging.

    Idempotent and a no-op if OTEL_EXPORTER_OTLP_ENDPOINT isn't configured, so
    it's safe to call unconditionally in every process without breaking local
    dev setups that don't run the observability stack.
    """
    global _telemetry_initialized
    if _telemetry_initialized:
        return

    if not config.OTEL_EXPORTER_OTLP_ENDPOINT:
        logger.warning(
            "OTEL_EXPORTER_OTLP_ENDPOINT not set; tracing disabled for this process"
        )
        return

    resource = Resource.create({SERVICE_NAME: service_name})
    sampler = ParentBased(TraceIdRatioBased(config.OTEL_TRACES_SAMPLER_RATIO))
    provider = TracerProvider(resource=resource, sampler=sampler)
    provider.add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(endpoint=config.OTEL_EXPORTER_OTLP_ENDPOINT, insecure=True)
        )
    )
    trace.set_tracer_provider(provider)

    HTTPXClientInstrumentor().instrument()
    RedisInstrumentor().instrument()
    # set_logging_format=False: attaches otelTraceID/otelSpanID to log records
    # without forcing a global format string -- app/core/logger.py's handlers
    # opt into rendering them individually.
    LoggingInstrumentor().instrument(set_logging_format=False)

    _telemetry_initialized = True
    logger.info(f"OpenTelemetry tracing initialized for service={service_name}")


def instrument_fastapi_app(app) -> None:
    """Instrument the FastAPI app for inbound request spans.

    Call once, after the app object exists. A no-op if tracing is disabled.
    """
    if not config.OTEL_EXPORTER_OTLP_ENDPOINT:
        return

    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    FastAPIInstrumentor.instrument_app(
        app, excluded_urls="metrics,docs,openapi.json,redoc"
    )


def instrument_sqlalchemy_engine(engine) -> None:
    """Instrument a SQLAlchemy engine (sync or async) for query spans.

    Registers engine-level event hooks that resolve the tracer lazily at
    query time, so this is safe to call before setup_telemetry() has run in
    this process (e.g. at database.py's module import time).
    """
    global _sqlalchemy_instrumented
    if _sqlalchemy_instrumented or not config.OTEL_EXPORTER_OTLP_ENDPOINT:
        return

    sync_engine = getattr(engine, "sync_engine", engine)
    SQLAlchemyInstrumentor().instrument(engine=sync_engine)
    _sqlalchemy_instrumented = True


def instrument_celery() -> None:
    """Instrument Celery so task spans join the trace started by the request
    that dispatched them (context propagates through task headers).

    Call once per worker process, from worker_process_init (see
    app/core/clients/celery.py) -- after setup_telemetry() so the exporter
    for this worker role is already configured.
    """
    if not config.OTEL_EXPORTER_OTLP_ENDPOINT:
        return

    from opentelemetry.instrumentation.celery import CeleryInstrumentor

    CeleryInstrumentor().instrument()
