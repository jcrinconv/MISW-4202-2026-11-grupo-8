from datetime import datetime
from . import db

class ReportWindow(db.Model):
    __tablename__ = "report_windows"

    window_uuid = db.Column(db.String(36), primary_key=True)
    service = db.Column(db.String(64), nullable=False)

    error_status_no_reportado = db.Column(db.Float, nullable=False)  # 0..0.02
    error_status_generado = db.Column(db.Float, nullable=False)      # 0..0.05

    window_from = db.Column(db.DateTime(timezone=True), nullable=False)
    window_to = db.Column(db.DateTime(timezone=True), nullable=False)

    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=datetime.utcnow)

class ReportAudit(db.Model):
    __tablename__ = "report_audit"

    id = db.Column(db.Integer, primary_key=True)
    window_uuid = db.Column(db.String(36), db.ForeignKey("report_windows.window_uuid"), index=True, nullable=False)
    service = db.Column(db.String(64), nullable=False)

    # OK | error:... | OMITTED
    status = db.Column(db.String(255), nullable=False)

    window_from = db.Column(db.DateTime(timezone=True), nullable=False)
    window_to = db.Column(db.DateTime(timezone=True), nullable=False)
    timestamp = db.Column(db.DateTime(timezone=True), nullable=False)

    sent_to_queue = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=datetime.utcnow)
