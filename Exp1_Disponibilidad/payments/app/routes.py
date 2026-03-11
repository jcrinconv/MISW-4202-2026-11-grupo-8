import os
import random
from uuid import uuid4
from datetime import datetime, timezone, timedelta
from flask import Blueprint, current_app, request, jsonify

from . import db
from .models import ReportWindow, ReportAudit
from .runner import start_window_async

bp = Blueprint("payments", __name__)

@bp.get("/health")
def health():
    return {"ok": True, "service": os.getenv("SERVICE_NAME", "payments-1")}

@bp.post("/report-windows")
def create_window():
    service      = current_app.config["SERVICE_NAME"]
    err_gen      = round(random.uniform(0.0, 0.30), 4)   # 0%..30%
    err_norep    = round(random.uniform(0.0, 0.15), 4)   # 0%..15%
    duration_sec = random.randint(60, 180)               # 1..3 min

    # Snap to the next 10-second boundary, drop sub-second precision
    now = datetime.now(timezone.utc).replace(microsecond=0)
    remainder = now.second % 10
    if remainder != 0:
        now = now + timedelta(seconds=(10 - remainder))

    w_uuid = str(uuid4())

    w = ReportWindow(
        window_uuid=w_uuid,
        service=service,
        error_status_generado=err_gen,
        error_status_no_reportado=err_norep,
        window_from=now,
        window_to=now + timedelta(seconds=duration_sec),
    )
    db.session.add(w)
    db.session.commit()

    # Arranca en background (sin worker)
    start_window_async(w_uuid)

    return jsonify({
        "ok": True,
        "window_uuid": w_uuid,
        "service": service,
        "error_status_generado": err_gen,
        "error_status_no_reportado": err_norep,
        "duration_sec": duration_sec,
        "window_from": now.isoformat().replace("+00:00", "Z"),
        "window_to": (now + timedelta(seconds=duration_sec)).isoformat().replace("+00:00", "Z"),
        "tick_seconds": 10,
    }), 202

@bp.get("/report-windows/<window_uuid>/stats")
def window_stats(window_uuid: str):
    total       = ReportAudit.query.filter_by(window_uuid=window_uuid).count()
    sent        = ReportAudit.query.filter_by(window_uuid=window_uuid, sent_to_queue=True).count()
    no_reported = ReportAudit.query.filter_by(window_uuid=window_uuid, status="no_reported").count()
    ok          = ReportAudit.query.filter_by(window_uuid=window_uuid, status="ok").count()
    err         = ReportAudit.query.filter(
        ReportAudit.window_uuid == window_uuid,
        ReportAudit.status.like("error:%")
    ).count()

    return {
        "ok": True,
        "window_uuid": window_uuid,
        "audit_total": total,
        "sent_to_queue": sent,
        "no_reported": no_reported,
        "ok_count": ok,
        "error_count": err,
    }
