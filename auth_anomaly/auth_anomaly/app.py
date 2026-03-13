"""FastAPI application for the AuthAnomaly component."""

from __future__ import annotations

from typing import List
import logging

from fastapi import Depends, FastAPI

from .auth_client import AuthNotifier
from .config import Settings, load_settings
from .models import AuthEvent, ProcessedEvent
from .processor import EventProcessor
from .rules import (
    BaseRule,
    MultiIpBruteforceRule,
    RepeatedFailureRule,
    RateLimitRule,
    TokenReplayRule,
)
from .storage import Storage

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def build_rules(settings: Settings) -> List[BaseRule]:
    return [
        RepeatedFailureRule(
            threshold=settings.failure_threshold,
            window_seconds=settings.failure_window_seconds,
        ),
        MultiIpBruteforceRule(
            unique_threshold=settings.multi_ip_threshold,
            window_seconds=settings.multi_ip_window_seconds,
        ),
        TokenReplayRule(ttl_seconds=settings.token_replay_ttl_seconds),
        RateLimitRule(
            threshold=settings.ratelimit_threshold,
            window_seconds=settings.ratelimit_window_seconds,
            activities=settings.ratelimit_activities,
            statuses=settings.ratelimit_statuses,
        ),
    ]


def create_app() -> FastAPI:
    settings = load_settings()
    notifier = AuthNotifier(settings)
    rules = build_rules(settings)
    storage = Storage(
        events_url=settings.events_db_url,
        anomalies_url=settings.anomalies_db_url,
        create_schema=settings.create_schema_on_startup,
    )
    processor = EventProcessor(settings=settings, rules=rules, notifier=notifier, storage=storage)

    app = FastAPI(
        title="AuthAnomaly",
        version="0.1.0",
        description="Detecta anomalías en eventos de autenticación y avisa al componente Auth.",
    )

    @app.on_event("startup")
    async def startup() -> None:  # noqa: D401
        await notifier.startup()
        await storage.startup()
        logger.info("AuthAnomaly iniciado con %s reglas", len(rules))

    @app.on_event("shutdown")
    async def shutdown() -> None:  # noqa: D401
        await notifier.shutdown()

    def get_processor() -> EventProcessor:
        return processor

    def get_rules() -> List[BaseRule]:
        return rules

    @app.get("/health")
    async def health() -> dict:
        return {
            "status": "ok",
            "rules": len(rules),
            "sla_ms": settings.detection_sla_ms,
            "notify_enabled": settings.notify_enabled,
        }

    @app.get("/rules")
    async def list_rules(rule_list: List[BaseRule] = Depends(get_rules)) -> List[dict]:
        return [
            {
                "name": rule.name,
                "severity": getattr(rule, "severity", "medium"),
                "window_seconds": getattr(rule, "window_seconds", settings.failure_window_seconds),
            }
            for rule in rule_list
        ]

    @app.post("/auth-event", response_model=ProcessedEvent, status_code=202)
    async def ingest_event(
        event: AuthEvent,
        processor_dep: EventProcessor = Depends(get_processor),
    ) -> ProcessedEvent:
        result = await processor_dep.handle_event(event)
        return result

    return app


app = create_app()


__all__ = ["app", "create_app", "build_rules"]
