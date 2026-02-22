import os, json, random, time, threading
from uuid import uuid4
from datetime import timezone, timedelta
from redis import Redis

from .models import ReportWindow, ReportAudit

def iso_z(dt):
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

def get_redis():
    return Redis.from_url(os.environ["REDIS_REPORTS_URL"], decode_responses=True)

def _run_window(window_uuid: str):
    # Crea un app context independiente para el hilo
    from app import create_app, db

    app = create_app()
    r = get_redis()

    with app.app_context():
        w = db.session.get(ReportWindow, window_uuid)
        if not w:
            return

        # --- Pre-compute deterministic slot schedule ---
        total_ticks = int((w.window_to - w.window_from).total_seconds() // 10) + 1
        n_errors_raw = round(w.error_status_generado * total_ticks)
        n_omitted    = max(1, round(w.error_status_no_reportado * total_ticks))  # siempre al menos 1 omitido

        # Asegura que quede espacio para el omitido y no se generen negativos
        n_errors = min(n_errors_raw, max(0, total_ticks - n_omitted))
        n_ok     = max(0, total_ticks - n_errors - n_omitted)

        slots = ["error"] * n_errors + ["no_reported"] * n_omitted + ["ok"] * n_ok
        random.shuffle(slots)

        tick = w.window_from
        for slot in slots:
            if slot == "no_reported":
                audit_status   = "no_reported"
                payload_status = "ok"   # no se enviará
                sent           = False
            elif slot == "error":
                payload_status = f"error:simulated_error_{uuid4()}"
                audit_status   = payload_status
                sent           = True
            else:
                payload_status = "ok"
                audit_status   = "ok"
                sent           = True

            payload = {
                "service":     w.service,
                "status":      payload_status,
                "window_uuid": w.window_uuid,
                "window_from": iso_z(w.window_from),
                "window_to":   iso_z(w.window_to),
                "timestamp":   iso_z(tick),
            }

            # Auditoría SIEMPRE
            audit = ReportAudit(
                window_uuid=w.window_uuid,
                service=w.service,
                status=audit_status,
                window_from=w.window_from,
                window_to=w.window_to,
                timestamp=tick,
                sent_to_queue=sent,
            )
            db.session.add(audit)
            db.session.commit()

            # Publicar solo si no fue omitido
            if sent:
                r.xadd("reports", {"payload": json.dumps(payload)})

            time.sleep(10)
            tick = tick + timedelta(seconds=10)

def start_window_async(window_uuid: str):
    t = threading.Thread(target=_run_window, args=(window_uuid,), daemon=True)
    t.start()
