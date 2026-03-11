"""Minimal REST API for ingesting heartbeats and sweeping monitoring windows."""

from __future__ import annotations

from datetime import datetime, timezone
from http import HTTPStatus
from typing import Dict, List, Tuple

from flask import Response, current_app, jsonify, request

# from ..modelos.modelos import (
from monitor.modelos import (
    HeartbeatEvent,
    HeartbeatStatus,
    MonitoringWindow,
    WindowState,
    db,
)

from . import monitor_bp

ISO_FORMATS = ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ")
REQUIRED_FIELDS = [
    "service",
    "status",
    "window_uuid",
    "window_from",
    "window_to",
    "timestamp",
]


@monitor_bp.route("/heartbeats", methods=["POST"])
def ingest_heartbeat() -> Response:
    payload = request.get_json(force=True, silent=True) or {}

    missing = [field for field in REQUIRED_FIELDS if field not in payload or payload[field] in (None, "")]
    if missing:
        return (
            jsonify({"error": "missing required fields", "fields": missing}),
            HTTPStatus.BAD_REQUEST,
        )

    try:
        status_value, error_message = _normalize_status(payload["status"])
    except ValueError as exc:
        return jsonify({"error": str(exc)}), HTTPStatus.BAD_REQUEST

    try:
        window_from = _parse_iso_datetime(payload["window_from"])
        window_to = _parse_iso_datetime(payload["window_to"])
        timestamp = _parse_iso_datetime(payload["timestamp"])
    except ValueError:
        return jsonify({"error": "Invalid datetime format"}), HTTPStatus.BAD_REQUEST

    error_status_no_reportado = payload.get("error_status_no_reportado")
    error_status_generado = payload.get("error_status_generado")

    window = _get_or_create_window(
        window_uuid=str(payload["window_uuid"]),
        service_name=str(payload["service"]),
        window_from=window_from,
        window_to=window_to,
        error_status_no_reportado=error_status_no_reportado,
        error_status_generado=error_status_generado,
    )

    heartbeat = HeartbeatEvent(
        window=window,
        service_name=window.service_name,
        status=status_value,
        error_message=error_message,
        report_timestamp=timestamp,
        window_from=window.window_from,
        window_to=window.window_to,
    )
    db.session.add(heartbeat)

    window.received_reports += 1
    if status_value == HeartbeatStatus.ERROR:
        window.error_reports += 1

    db.session.commit()

    return (
        jsonify({
            "heartbeat": _heartbeat_to_dict(heartbeat),
            "window": _window_to_dict(window),
        }),
        HTTPStatus.ACCEPTED,
    )


@monitor_bp.route("/windows/sweep", methods=["POST"])
def sweep_windows() -> Response:
    payload = request.get_json(force=False, silent=True) or {}
    now = datetime.now(timezone.utc)

    query = MonitoringWindow.query.filter(
        MonitoringWindow.window_to <= now,
        MonitoringWindow.status == WindowState.OPEN,
    )

    if payload.get("window_uuid"):
        query = query.filter_by(window_uuid=payload["window_uuid"])

    closed_windows: List[Dict[str, object]] = []

    for window in query.all():
        missing = window.missing_count()
        if missing > 0:
            _create_missing_heartbeats(window, missing)
            window.error_reports += missing
            window.received_reports += missing
        window.mark_closed(alert=missing > 0)
        closed_windows.append(_window_to_dict(window))

    db.session.commit()

    return jsonify({"closed_windows": closed_windows})


def _get_or_create_window(
    *,
    window_uuid: str,
    service_name: str,
    window_from: datetime,
    window_to: datetime,
    error_status_no_reportado: float | None = None,
    error_status_generado: float | None = None,
) -> MonitoringWindow:
    window = MonitoringWindow.query.filter_by(window_uuid=window_uuid).one_or_none()
    if window:
        if error_status_no_reportado is not None and window.error_status_no_reportado is None:
            window.error_status_no_reportado = float(error_status_no_reportado)
        if error_status_generado is not None and window.error_status_generado is None:
            window.error_status_generado = float(error_status_generado)
        return window

    expected_reports = _calculate_expected_reports(window_from, window_to)
    window = MonitoringWindow(
        window_uuid=window_uuid,
        service_name=service_name,
        window_from=window_from,
        window_to=window_to,
        error_status_no_reportado=float(error_status_no_reportado)
        if error_status_no_reportado is not None
        else None,
        error_status_generado=float(error_status_generado)
        if error_status_generado is not None
        else None,
        expected_reports=expected_reports,
        status=WindowState.OPEN,
    )
    db.session.add(window)
    db.session.flush()
    return window


def _calculate_expected_reports(window_from: datetime, window_to: datetime) -> int:
    interval = int(current_app.config.get("HEARTBEAT_INTERVAL_SECONDS", 10))
    duration = max(0, int((window_to - window_from).total_seconds()))
    expected = duration // interval
    if duration % interval:
        expected += 1
    return max(1, expected)


def _create_missing_heartbeats(window: MonitoringWindow, missing: int) -> None:
    for _ in range(missing):
        db.session.add(
            HeartbeatEvent(
                window=window,
                service_name=window.service_name,
                status=HeartbeatStatus.MISSING,
                error_message="Generated by sweep: heartbeat missing",
                report_timestamp=window.window_to,
                window_from=window.window_from,
                window_to=window.window_to,
            )
        )


def _parse_iso_datetime(value: str) -> datetime:
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        for fmt in ISO_FORMATS:
            try:
                dt = datetime.strptime(value, fmt)
                break
            except ValueError:
                continue
        else:
            raise ValueError("Invalid datetime format")

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt


def _normalize_status(raw_status: str) -> Tuple[HeartbeatStatus, str | None]:
    text = raw_status.strip()
    if not text:
        raise ValueError("status is required")

    upper_text = text.upper()
    if upper_text == "OK":
        return HeartbeatStatus.OK, None

    if upper_text.startswith("ERROR"):
        message = None
        if ":" in text:
            message = text.split(":", 1)[1].strip() or None
        return HeartbeatStatus.ERROR, message

    raise ValueError("status must be 'OK' or start with 'error:'")


def _heartbeat_to_dict(event: HeartbeatEvent) -> Dict[str, object]:
    return {
        "id": event.id,
        "service": event.service_name,
        "status": event.status.value,
        "error_message": event.error_message,
        "timestamp": event.report_timestamp.isoformat(),
        "window_uuid": event.window.window_uuid,
        "window_from": event.window_from.isoformat(),
        "window_to": event.window_to.isoformat(),
        "ingested_at": event.ingested_at.isoformat(),
    }


def _window_to_dict(window: MonitoringWindow) -> Dict[str, object]:
    return {
        "window_uuid": window.window_uuid,
        "service": window.service_name,
        "status": window.status.value,
        "error_status_no_reportado": window.error_status_no_reportado,
        "error_status_generado": window.error_status_generado,
        "expected_reports": window.expected_reports,
        "received_reports": window.received_reports,
        "error_reports": window.error_reports,
        "missing_reports": window.missing_reports,
        "window_from": window.window_from.isoformat(),
        "window_to": window.window_to.isoformat(),
        "created_at": window.created_at.isoformat(),
        "updated_at": window.updated_at.isoformat(),
        "closed_at": window.closed_at.isoformat() if window.closed_at else None,
    }
