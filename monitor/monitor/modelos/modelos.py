"""Simplified models for the heartbeat monitor."""

from __future__ import annotations

import enum
from datetime import datetime, timezone

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class HeartbeatStatus(enum.Enum):
    OK = "ok"
    ERROR = "error"
    MISSING = "missing"


class WindowState(enum.Enum):
    OPEN = "open"
    CLOSED = "closed"
    ALERT = "alert"


class MonitoringWindow(db.Model):
    __tablename__ = "monitoring_windows"
    __table_args__ = (db.UniqueConstraint("window_uuid", name="uq_window_uuid"),)

    id = db.Column(db.Integer, primary_key=True)
    window_uuid = db.Column(db.String(64), nullable=False)
    service_name = db.Column(db.String(120), nullable=False)
    window_from = db.Column(db.DateTime(timezone=True), nullable=False)
    window_to = db.Column(db.DateTime(timezone=True), nullable=False)
    status = db.Column(db.Enum(WindowState), default=WindowState.OPEN, nullable=False)
    error_status_no_reportado = db.Column(db.Float)
    error_status_generado = db.Column(db.Float)
    expected_reports = db.Column(db.Integer, nullable=False, default=0)
    received_reports = db.Column(db.Integer, default=0, nullable=False)
    error_reports = db.Column(db.Integer, default=0, nullable=False)
    missing_reports = db.Column(db.Integer, default=0, nullable=False)
    closed_at = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    heartbeats = db.relationship(
        "HeartbeatEvent", back_populates="window", cascade="all, delete-orphan"
    )

    def mark_closed(self, alert: bool = False) -> None:
        self.status = WindowState.ALERT if alert else WindowState.CLOSED
        self.closed_at = utcnow()

    def missing_count(self) -> int:
        missing = max(0, self.expected_reports - self.received_reports)
        self.missing_reports = missing
        return missing


class HeartbeatEvent(db.Model):
    __tablename__ = "heartbeat_events"
    __table_args__ = (
        db.Index("ix_window_timestamp", "window_id", "report_timestamp"),
    )

    id = db.Column(db.Integer, primary_key=True)
    window_id = db.Column(db.Integer, db.ForeignKey("monitoring_windows.id"), nullable=False)
    service_name = db.Column(db.String(120), nullable=False)
    status = db.Column(db.Enum(HeartbeatStatus), nullable=False)
    error_message = db.Column(db.Text)
    report_timestamp = db.Column(db.DateTime(timezone=True), nullable=False)
    window_from = db.Column(db.DateTime(timezone=True), nullable=False)
    window_to = db.Column(db.DateTime(timezone=True), nullable=False)
    ingested_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    window = db.relationship("MonitoringWindow", back_populates="heartbeats")
