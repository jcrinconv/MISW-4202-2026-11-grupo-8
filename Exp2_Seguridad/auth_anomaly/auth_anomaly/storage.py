"""Persistence layer for AuthAnomaly events and anomalies."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, List, Tuple

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from .models import AnomalyDecision, AuthEvent, NotificationResult, ProcessedEvent


class _EventsBase(DeclarativeBase):
    pass


class _AnomaliesBase(DeclarativeBase):
    pass


class AuthEventRecord(_EventsBase):
    __tablename__ = "auth_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user: Mapped[str] = mapped_column(String(128), index=True)
    activity: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32))
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    auth_token: Mapped[str | None] = mapped_column(String(256), nullable=True)
    auth_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    processing_time_ms: Mapped[int] = mapped_column(Integer)
    anomaly_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class AnomalyRecord(_AnomaliesBase):
    __tablename__ = "auth_anomalies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user: Mapped[str] = mapped_column(String(128), index=True)
    activity: Mapped[str] = mapped_column(String(64), index=True)
    rule: Mapped[str] = mapped_column(String(64))
    severity: Mapped[str] = mapped_column(String(32))
    reason: Mapped[str] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    latency_ms: Mapped[int] = mapped_column(Integer)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    recent_events: Mapped[list | None] = mapped_column(JSON, nullable=True)
    notification_success: Mapped[bool] = mapped_column(Boolean, default=False)
    notification_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


@dataclass
class _Database:
    url: str
    base: type[DeclarativeBase]

    def __post_init__(self) -> None:
        connect_args = {"check_same_thread": False} if self.url.startswith("sqlite") else {}
        self.engine = create_engine(self.url, future=True, connect_args=connect_args)
        self.session_factory = sessionmaker(self.engine, expire_on_commit=False)

    def create_schema(self) -> None:
        self.base.metadata.create_all(self.engine)

    def session(self):  # type: ignore[override]
        return self.session_factory()


class Storage:
    """Coordinates persistence in the events and anomalies databases."""

    def __init__(self, *, events_url: str, anomalies_url: str, create_schema: bool = True) -> None:
        self._events_db = _Database(events_url, _EventsBase)
        self._anomalies_db = _Database(anomalies_url, _AnomaliesBase)
        self._create_schema = create_schema

    async def startup(self) -> None:
        if not self._create_schema:
            return
        await asyncio.to_thread(self._create_all)

    def _create_all(self) -> None:
        self._events_db.create_schema()
        self._anomalies_db.create_schema()

    async def persist(self, *, event: AuthEvent, processed: ProcessedEvent) -> None:
        await asyncio.gather(
            asyncio.to_thread(self._persist_event, event, processed),
            asyncio.to_thread(self._persist_anomalies, processed),
        )

    # ─── Internal helpers ────────────────────────────────────────────────────

    def _persist_event(self, event: AuthEvent, processed: ProcessedEvent) -> None:
        record = AuthEventRecord(
            user=event.user,
            activity=event.activity,
            status=event.status,
            detail=self._serialize_detail(event.detail),
            metadata_json=event.metadata,
            auth_token=event.auth_token,
            auth_id=event.auth_id,
            occurred_at=event.occurred_at,
            received_at=processed.received_at,
            processed_at=processed.processed_at,
            processing_time_ms=processed.processing_time_ms,
            anomaly_count=len(processed.anomalies),
        )
        with self._events_db.session() as session:
            session.add(record)
            session.commit()

    def _persist_anomalies(self, processed: ProcessedEvent) -> None:
        if not processed.anomalies:
            return
        notifications = processed.notifications or []
        padded_notifications: List[NotificationResult] = list(notifications)
        while len(padded_notifications) < len(processed.anomalies):
            decision = processed.anomalies[len(padded_notifications)]
            padded_notifications.append(
                NotificationResult(
                    rule=decision.rule,
                    user=decision.user,
                    activity=decision.activity,
                    detected_at=decision.detected_at,
                    success=False,
                    detail="notification not attempted",
                )
            )

        with self._anomalies_db.session() as session:
            for decision, notification in zip(processed.anomalies, padded_notifications):
                record = AnomalyRecord(
                    user=decision.user,
                    activity=decision.activity,
                    rule=decision.rule,
                    severity=decision.severity,
                    reason=decision.reason,
                    occurred_at=decision.occurred_at,
                    detected_at=decision.detected_at,
                    latency_ms=decision.latency_ms,
                    metadata_json=decision.metadata,
                    recent_events=decision.recent_events,
                    notification_success=notification.success,
                    notification_detail=notification.detail,
                )
                session.add(record)
            session.commit()

    @staticmethod
    def _serialize_detail(detail) -> str | None:
        if detail is None:
            return None
        if isinstance(detail, str):
            return detail
        return repr(detail)


__all__ = ["Storage", "AuthEventRecord", "AnomalyRecord"]
