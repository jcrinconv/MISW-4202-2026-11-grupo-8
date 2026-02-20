from celery import Celery
import json
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

celery_app = Celery(__name__, broker="redis://localhost:6379/0")
celery_app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    broker_transport_options={"visibility_timeout": 3600},
)


@celery_app.task(
    name="registrar_log",
    bind=True,
    autoretry_for=(HTTPError, URLError),
    retry_backoff=True,  # 1s, 2s, 4s, 8s...
    retry_backoff_max=300,  # máximo 5 min entre reintentos
    retry_jitter=True,
    max_retries=12,  # ajustable
)
def registrar_log(self, mensaje):
    payload = json.dumps({"mensaje": mensaje}).encode("utf-8")
    req = Request(
        "http://localhost:5002/monitoreo-logs",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(req, timeout=5) as response:
        response.read()
