"""Runtime configuration helpers for the AuthAnomaly service."""

from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Optional, Tuple


def _bool(value: Optional[str], *, default: bool = True) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _resolve_data_dir() -> str:
    base = os.getenv("AUTH_DATA_DIR")
    path = base or os.path.join(os.getcwd(), "auth_anomaly_data")
    os.makedirs(path, exist_ok=True)
    return path


def _csv(value: Optional[str], *, default: str, transform) -> Tuple[str, ...]:
    raw = value if value is not None else default
    parts = [item.strip() for item in raw.split(",") if item.strip()]
    return tuple(transform(item) for item in parts)


@dataclass(slots=True)
class Settings:
    """Strongly typed configuration surface."""

    auth_service_base_url: str = os.getenv("AUTH_SERVICE_BASE_URL", "http://auth:5000")
    block_user_endpoint: str = os.getenv("AUTH_BLOCK_ENDPOINT", "/block-user")
    notify_enabled: bool = _bool(os.getenv("AUTH_NOTIFY_ENABLED"), default=True)
    data_dir: str = _resolve_data_dir()
    events_db_url: str = os.getenv("AUTH_EVENTS_DB_URL") or f"sqlite:///{os.path.join(_resolve_data_dir(), 'auth_events.db')}"
    anomalies_db_url: str = os.getenv("AUTH_ANOMALIES_DB_URL") or f"sqlite:///{os.path.join(_resolve_data_dir(), 'auth_anomalies.db')}"
    create_schema_on_startup: bool = _bool(os.getenv("AUTH_CREATE_SCHEMA_ON_STARTUP"), default=True)

    # Rule tuning
    failure_threshold: int = int(os.getenv("AUTH_FAILURE_THRESHOLD", "3"))
    failure_window_seconds: int = int(os.getenv("AUTH_FAILURE_WINDOW_SECONDS", "60"))
    multi_ip_threshold: int = int(os.getenv("AUTH_MULTI_IP_THRESHOLD", "3"))
    multi_ip_window_seconds: int = int(os.getenv("AUTH_MULTI_IP_WINDOW_SECONDS", "90"))
    token_replay_ttl_seconds: int = int(os.getenv("AUTH_TOKEN_REPLAY_TTL_SECONDS", "180"))
    ratelimit_threshold: int = int(os.getenv("AUTH_RATELIMIT_THRESHOLD", "30"))
    ratelimit_window_seconds: int = int(os.getenv("AUTH_RATELIMIT_WINDOW_SECONDS", "60"))
    ratelimit_activities: Tuple[str, ...] = _csv(
        os.getenv("AUTH_RATELIMIT_ACTIVITIES"),
        default="validate",
        transform=lambda value: value.lower(),
    )
    ratelimit_statuses: Tuple[str, ...] = _csv(
        os.getenv("AUTH_RATELIMIT_STATUSES"),
        default="success",
        transform=lambda value: value.upper(),
    )

    # Runtime controls
    http_timeout_seconds: float = float(os.getenv("AUTH_HTTP_TIMEOUT_SECONDS", "1.5"))
    max_history_seconds: int = int(os.getenv("AUTH_MAX_HISTORY_SECONDS", "600"))
    detection_sla_ms: int = int(os.getenv("AUTH_DETECTION_SLA_MS", "2000"))

    @property
    def block_user_url(self) -> str:
        return f"{self.auth_service_base_url.rstrip('/')}{self.block_user_endpoint}"  # noqa: E501


def load_settings() -> Settings:
    return Settings()


__all__ = ["Settings", "load_settings"]
