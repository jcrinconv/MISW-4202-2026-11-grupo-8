import json
import os
from datetime import datetime, timezone

from flask import Flask, request
from flask_cors import CORS
from flask_restful import Api, Resource
from sqlalchemy import DateTime, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, scoped_session, sessionmaker


class Base(DeclarativeBase):
    pass


class ReservaEvent(Base):
    __tablename__ = "reserva_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    method: Mapped[str] = mapped_column(String(10))
    path: Mapped[str] = mapped_column(String(255))
    x_auth_token: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    simulation_uuid: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    headers_json: Mapped[str] = mapped_column(Text)
    query_json: Mapped[str] = mapped_column(Text)
    body_json: Mapped[str] = mapped_column(Text)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


DB_URL = os.getenv("RESERVAS_DB_URL", "sqlite:///reservas.db")
PORT = int(os.getenv("PORT", "8080"))

connect_args = {"check_same_thread": False} if DB_URL.startswith("sqlite") else {}
engine = create_engine(DB_URL, future=True, connect_args=connect_args)
SessionLocal = scoped_session(
    sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
)
Base.metadata.create_all(engine)

app = Flask(__name__)
CORS(app, origins="*")
api = Api(app)


def persist_request() -> tuple[int | None, str | None]:
    session = SessionLocal()
    try:
        body = request.get_json(silent=True) or {}
        simulation_uuid = (
            request.headers.get("X-Simulation-UUID")
            or body.get("simulation_uuid")
        )
        entry = ReservaEvent(
            method=request.method,
            path=request.path,
            x_auth_token=request.headers.get("X-Auth-Token"),
            simulation_uuid=simulation_uuid,
            headers_json=json.dumps(dict(request.headers)),
            query_json=json.dumps(request.args.to_dict(flat=False)),
            body_json=json.dumps(body),
            received_at=datetime.now(timezone.utc),
        )
        session.add(entry)
        session.commit()
        return entry.id, None
    except Exception as exc:
        session.rollback()
        return None, str(exc)
    finally:
        session.close()


class Health(Resource):
    def get(self):
        return {"status": "ok", "service": "reservas-mock"}, 200


class ReservasMock(Resource):
    def post(self):
        event_id, error = persist_request()
        return {
            "message": "Reserva recibida",
            "saved": error is None,
            "event_id": event_id,
            "error": error,
        }, 200


api.add_resource(Health, "/health")
api.add_resource(ReservasMock, "/reservas")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
