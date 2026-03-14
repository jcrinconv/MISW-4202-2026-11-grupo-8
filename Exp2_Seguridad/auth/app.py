import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import quote_plus

import jwt
import redis
from flask import Flask, request
from flask_cors import CORS
from flask_restful import Api, Resource
from sqlalchemy import Boolean, DateTime, Integer, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, scoped_session, sessionmaker
from werkzeug.security import check_password_hash, generate_password_hash


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(50), default="user")
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    token_version: Mapped[int] = mapped_column(Integer, default=1)
    blocked_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    blocked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class AuthAudit(Base):
    __tablename__ = "auth_audit"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    activity: Mapped[str] = mapped_column(String(50), index=True)
    status: Mapped[str] = mapped_column(String(50), index=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    auth_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    simulation_uuid: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


def build_mysql_url() -> str:
    user = os.getenv("AUTH_DB_USER", "audit_user")
    password = quote_plus(os.getenv("AUTH_DB_PASSWORD", "secure_audit_pass_2024"))
    host = os.getenv("AUTH_DB_HOST", "mysql")
    port = os.getenv("AUTH_DB_PORT", "3306")
    database = os.getenv("AUTH_DB_NAME", "security_audit")
    return f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}"


DB_URL = os.getenv("AUTH_DB_URL") or build_mysql_url()
JWT_SECRET = os.getenv("JWT_SECRET", "change-me")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "60"))
REDIS_URL = os.getenv("CELERY_BROKER_URL", os.getenv("REDIS_URL", "redis://redis:6379/0"))
STREAM_NAME = os.getenv("STREAM_NAME", "reports")
PORT = int(os.getenv("PORT", "8080"))
SEED_USERS = os.getenv("AUTH_SEED_USERS", "user1:user1:user,user2:user2:user,user3:user3:user,user4:user4:user,user5:user5:user")

connect_args = {"check_same_thread": False} if DB_URL.startswith("sqlite") else {}
engine = create_engine(DB_URL, future=True, connect_args=connect_args)
SessionLocal = scoped_session(sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False))
Base.metadata.create_all(engine)

try:
    redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    redis_client.ping()
except Exception:
    redis_client = None


app = Flask(__name__)
CORS(app, origins="*")
api = Api(app)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def get_session():
    return SessionLocal()


def get_json_body() -> dict:
    body = request.get_json(silent=True)
    return body if isinstance(body, dict) else {}


def get_client_ip(body: dict | None = None) -> str:
    if body and isinstance(body.get("metadata"), dict) and body["metadata"].get("ip"):
        return str(body["metadata"]["ip"])
    header_ip = request.headers.get("X-Client-IP", "")
    if header_ip:
        return header_ip.split(",")[0].strip()
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or "unknown"


def get_client_metadata(body: dict | None = None) -> dict:
    metadata = {}
    if body and isinstance(body.get("metadata"), dict):
        metadata.update(body["metadata"])
    header_geo = request.headers.get("X-Geo")
    header_device = request.headers.get("X-Device-Id")
    header_ip = request.headers.get("X-Client-IP")
    simulation_header = request.headers.get("X-Simulation-UUID")
    if header_geo and not metadata.get("geo"):
        metadata["geo"] = header_geo
    if header_device and not metadata.get("device_id"):
        metadata["device_id"] = header_device
    if header_ip and not metadata.get("ip"):
        metadata["ip"] = header_ip
    if simulation_header and not metadata.get("simulation_uuid"):
        metadata["simulation_uuid"] = simulation_header
    metadata.setdefault("ip", get_client_ip(body))
    metadata.setdefault("user_agent", request.headers.get("User-Agent", "unknown"))
    return metadata


def extract_token() -> str | None:
    body = get_json_body()
    if isinstance(body.get("X-Auth-Token"), str) and body.get("X-Auth-Token"):
        return body.get("X-Auth-Token")
    header_token = request.headers.get("X-Auth-Token")
    if header_token:
        return header_token
    authorization = request.headers.get("Authorization", "")
    if authorization.lower().startswith("bearer "):
        return authorization.split(" ", 1)[1].strip()
    return None


def record_audit(user: str | None, activity: str, status: str, detail: str | None = None, metadata: dict | None = None, auth_id: str | None = None, simulation_uuid: str | None = None) -> None:
    session = get_session()
    try:
        entry = AuthAudit(
            user=user,
            activity=activity,
            status=status,
            detail=detail,
            metadata_json=json.dumps(metadata or {}),
            auth_id=auth_id,
            simulation_uuid=simulation_uuid,
            occurred_at=now_utc(),
        )
        session.add(entry)
        session.commit()
    finally:
        session.close()


def publish_event(user: str, activity: str, status: str, detail: str, metadata: dict | None = None, auth_token: str | None = None, auth_id: str | None = None, simulation_uuid: str | None = None) -> None:
    if redis_client is None:
        return
    payload = {
        "user": user,
        "activity": activity,
        "status": status,
        "detail": detail,
        "metadata": metadata or {},
        "auth_token": auth_token,
        "auth_id": auth_id,
        "simulation_uuid": simulation_uuid,
        "occurred_at": now_utc().isoformat(),
    }
    try:
        redis_client.xadd(STREAM_NAME, {"payload": json.dumps(payload)})
    except Exception:
        return


def issue_token(user: User) -> tuple[str, str]:
    auth_id = str(uuid.uuid4())
    issued_at = now_utc()
    payload = {
        "sub": str(user.id),
        "user": user.username,
        "role": user.role,
        "ver": user.token_version,
        "jti": auth_id,
        "iat": int(issued_at.timestamp()),
        "exp": int((issued_at + timedelta(minutes=JWT_EXPIRE_MINUTES)).timestamp()),
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return token, auth_id


def seed_users() -> None:
    session = get_session()
    try:
        for row in [item.strip() for item in SEED_USERS.split(",") if item.strip()]:
            parts = row.split(":")
            if len(parts) < 3:
                continue
            username, password, role = parts[0], parts[1], parts[2]
            existing = session.scalar(select(User).where(User.username == username))
            if existing is None:
                session.add(
                    User(
                        username=username,
                        password_hash=generate_password_hash(password),
                        role=role,
                        token_version=1,
                        is_blocked=False,
                    )
                )
        session.commit()
    finally:
        session.close()


def validate_token_value(token: str) -> tuple[dict | None, dict | None, tuple[dict, int] | None]:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        return None, None, ({"message": "Token expirado", "valid": False, "reason": "expired_token"}, 401)
    except jwt.InvalidTokenError:
        return None, None, ({"message": "Token inválido", "valid": False, "reason": "invalid_token"}, 401)

    username = payload.get("user")
    version = payload.get("ver")
    if not username:
        return None, None, ({"message": "Token inválido", "valid": False, "reason": "invalid_payload"}, 401)

    session = get_session()
    try:
        user = session.scalar(select(User).where(User.username == username))
        if user is None:
            return None, None, ({"message": "Usuario no encontrado", "valid": False, "reason": "user_not_found"}, 404)
        if user.is_blocked:
            return None, None, ({"message": "Usuario bloqueado", "valid": False, "reason": "blocked_user"}, 403)
        if int(version or 0) != int(user.token_version):
            return None, None, ({"message": "Sesión revocada", "valid": False, "reason": "revoked_session"}, 401)
        user_data = {
            "id": user.id,
            "username": user.username,
            "role": user["role"],
            "token_version": user.token_version,
        }
        return user_data, payload, None
    finally:
        session.close()



class Health(Resource):
    def get(self):
        return {
            "status": "ok",
            "service": "auth",
            "stream": STREAM_NAME,
            "redis": redis_client is not None,
        }, 200


class Login(Resource):
    def post(self):
        body = get_json_body()
        username = str(body.get("user", "")).strip()
        password = str(body.get("pass", ""))
        metadata = get_client_metadata(body)
        simulation_uuid = metadata.get("simulation_uuid")

        if not username or not password:
            record_audit(username or None, "login", "FAILED", "Credenciales incompletas", metadata, simulation_uuid=simulation_uuid)
            publish_event(username or "unknown", "login", "FAILED", "missing_credentials", metadata, simulation_uuid=simulation_uuid)
            return {"message": "Debe enviar user y pass"}, 400

        session = get_session()
        try:
            user = session.scalar(select(User).where(User.username == username))
            if user is None or not check_password_hash(user.password_hash, password):
                record_audit(username, "login", "FAILED", "Credenciales inválidas", metadata, simulation_uuid=simulation_uuid)
                publish_event(username, "login", "FAILED", "invalid_credentials", metadata, simulation_uuid=simulation_uuid)
                return {"message": "Credenciales inválidas"}, 401
            if user.is_blocked:
                record_audit(username, "login", "DENIED", user.blocked_reason or "Usuario bloqueado", metadata, simulation_uuid=simulation_uuid)
                publish_event(username, "login", "DENIED", user.blocked_reason or "blocked_user", metadata, simulation_uuid=simulation_uuid)
                return {"message": "Usuario bloqueado", "reason": user.blocked_reason}, 403

            token, auth_id = issue_token(user)
            record_audit(username, "login", "SUCCESS", "Autenticación exitosa", metadata, auth_id, simulation_uuid=simulation_uuid)
            publish_event(username, "login", "SUCCESS", "login_success", metadata, token, auth_id, simulation_uuid=simulation_uuid)
            return {
                "message": "Inicio de sesión exitoso",
                "token": token,
                "user": user.username,
                "role": user.role,
                "auth_id": auth_id,
            }, 200
        finally:
            session.close()


class Validate(Resource):
    def post(self):
        body = get_json_body()
        token = extract_token()
        metadata = get_client_metadata(body)
        simulation_uuid = metadata.get("simulation_uuid") or request.headers.get("X-Simulation-UUID")

        if not token:
            record_audit(None, "validate", "FAILED", "Token faltante", metadata, simulation_uuid=simulation_uuid)
            publish_event("unknown", "validate", "FAILED", "missing_token", metadata, simulation_uuid=simulation_uuid)
            return {"message": "Token faltante", "valid": False, "reason": "missing_token"}, 400

        user, payload, error = validate_token_value(token)
        if error is not None:
            error_body, status_code = error
            event_user = "unknown"
            try:
                decoded_unverified = jwt.decode(token, options={"verify_signature": False})
                event_user = decoded_unverified.get("user", "unknown")
            except Exception:
                event_user = "unknown"
            record_audit(event_user, "validate", error_body.get("reason", "FAILED").upper(), error_body.get("message"), metadata, simulation_uuid=simulation_uuid)
            publish_event(event_user, "validate", error_body.get("reason", "FAILED").upper(), error_body.get("message", "validate_error"), metadata, token, simulation_uuid=simulation_uuid)
            return error_body, status_code

        record_audit(user["username"], "validate", "SUCCESS", "Token válido", metadata, payload.get("jti"), simulation_uuid=simulation_uuid)
        publish_event(user["username"], "validate", "SUCCESS", "token_valid", metadata, token, payload.get("jti"), simulation_uuid=simulation_uuid)
        return {
            "valid": True,
            "message": "Token válido",
            "user": user["username"],
            "role": user["role"],
            "auth_id": payload.get("jti"),
        }, 200


class BlockUser(Resource):
    def post(self):
        body = get_json_body()
        username = str(body.get("user", "")).strip()
        reason = str(body.get("reason", "Anomalía detectada")).strip()
        metadata = get_client_metadata(body)
        metadata["severity"] = body.get("severity")
        metadata["activity"] = body.get("activity")
        metadata["detected_at"] = body.get("detected_at")
        simulation_uuid = body.get("simulation_uuid") or metadata.get("simulation_uuid")

        if not username:
            return {"message": "Debe enviar user"}, 400

        session = get_session()
        try:
            user = session.scalar(select(User).where(User.username == username))
            if user is None:
                record_audit(username, "block-user", "FAILED", "Usuario no encontrado", metadata, simulation_uuid=simulation_uuid)
                publish_event(username, "block-user", "FAILED", "user_not_found", metadata, simulation_uuid=simulation_uuid)
                return {"message": "Usuario no encontrado"}, 404

            if not user.is_blocked:
                user.is_blocked = True
                user.token_version = int(user.token_version) + 1
                user.blocked_reason = reason
                user.blocked_at = now_utc()
                session.add(user)
                session.commit()
                record_audit(username, "block-user", "SUCCESS", reason, metadata, simulation_uuid=simulation_uuid)
                publish_event(username, "block-user", "SUCCESS", reason, metadata, simulation_uuid=simulation_uuid)
                return {
                    "message": "Usuario bloqueado",
                    "user": username,
                    "reason": reason,
                    "token_version": user.token_version,
                }, 200

            record_audit(username, "block-user", "SUCCESS", user.blocked_reason or reason, metadata, simulation_uuid=simulation_uuid)
            publish_event(username, "block-user", "SUCCESS", user.blocked_reason or reason, metadata, simulation_uuid=simulation_uuid)
            return {
                "message": "Usuario ya estaba bloqueado",
                "user": username,
                "reason": user.blocked_reason or reason,
                "token_version": user.token_version,
            }, 200
        finally:
            session.close()


class UnblockUsers(Resource):
    def post(self):
        body = get_json_body()
        metadata = get_client_metadata(body)
        simulation_uuid = body.get("simulation_uuid") or metadata.get("simulation_uuid")
        raw_users = body.get("users") or ([] if not body.get("user") else [body.get("user")])
        users: list[str] | None = None

        if raw_users:
            if isinstance(raw_users, str):
                users = [raw_users]
            elif isinstance(raw_users, list) and all(isinstance(u, str) for u in raw_users):
                users = raw_users
            else:
                return {"message": "El campo users debe ser una lista de strings"}, 400

        session = get_session()
        try:
            if users:
                query = select(User).where(User.username.in_(users))
            else:
                query = select(User).where(User.is_blocked.is_(True))

            matched = session.scalars(query).all()
            if not matched:
                record_audit(None, "unblock-user", "SUCCESS", "No hay usuarios bloqueados", metadata, simulation_uuid=simulation_uuid)
                publish_event("system", "unblock-user", "SUCCESS", "no_blocked_users", metadata, simulation_uuid=simulation_uuid)
                return {"message": "No hay usuarios bloqueados", "count": 0, "users": []}, 200

            unblocked: list[str] = []
            for user in matched:
                if user.is_blocked:
                    user.is_blocked = False
                    user.blocked_reason = None
                    user.blocked_at = None
                    user.token_version = int(user.token_version) + 1
                    session.add(user)
                    unblocked.append(user.username)
                    record_audit(user.username, "unblock-user", "SUCCESS", "Usuario desbloqueado", metadata, simulation_uuid=simulation_uuid)
                    publish_event(user.username, "unblock-user", "SUCCESS", "user_unblocked", metadata, simulation_uuid=simulation_uuid)

            session.commit()
            return {
                "message": "Usuarios desbloqueados",
                "count": len(unblocked),
                "users": unblocked,
            }, 200
        except Exception as exc:
            session.rollback()
            record_audit(None, "unblock-user", "FAILED", str(exc), metadata, simulation_uuid=simulation_uuid)
            publish_event("system", "unblock-user", "FAILED", "unblock_error", metadata, simulation_uuid=simulation_uuid)
            return {"message": "Error desbloqueando usuarios", "detail": str(exc)}, 500
        finally:
            session.close()


api.add_resource(Health, "/health")
api.add_resource(Login, "/login")
api.add_resource(Validate, "/validate")
api.add_resource(BlockUser, "/block-user")
api.add_resource(UnblockUsers, "/unblock-users")

seed_users()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, debug=False)
