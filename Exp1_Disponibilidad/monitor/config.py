"""Application configuration for the simplified heartbeat monitor."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, Type


@dataclass
class Config:
    """Base configuration shared across environments."""

    SQLALCHEMY_DATABASE_URI: str = os.getenv(
        "DATABASE_URL", "mysql+pymysql://monitor:monitor@monitor-db/monitor"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS: bool = False

    HEARTBEAT_INTERVAL_SECONDS: int = int(os.getenv("HEARTBEAT_INTERVAL_SECONDS", 10))
    DEFAULT_WINDOW_DURATION_SECONDS: int = int(
        os.getenv("WINDOW_DURATION_SECONDS", 300)
    )

    # Feature flags
    CREATE_SCHEMA_ON_STARTUP: bool = os.getenv(
        "CREATE_SCHEMA_ON_STARTUP", "true"
    ).lower() in {"1", "true", "yes"}


@dataclass
class DevelopmentConfig(Config):
    DEBUG: bool = True
    SQLALCHEMY_DATABASE_URI: str = os.getenv(
        "DEV_DATABASE_URL", "sqlite:///monitor_dev.db"
    )


@dataclass
class TestingConfig(Config):
    TESTING: bool = True
    SQLALCHEMY_DATABASE_URI: str = "sqlite:///:memory:"
    CREATE_SCHEMA_ON_STARTUP: bool = True


@dataclass
class ProductionConfig(Config):
    DEBUG: bool = False


config_by_name: Dict[str, Type[Config]] = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}
