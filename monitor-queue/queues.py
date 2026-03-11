"""
monitor-queue: Redis Stream consumer.

Reads heartbeat payloads published by payments services from the Redis stream
'reports' and forwards them to the monitor's /api/monitor/heartbeats endpoint.
Retries with exponential back-off on transient HTTP/network errors.
"""

import json
import logging
import os
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import redis

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

REDIS_URL      = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
MONITOR_URL    = os.getenv("MONITOR_URL", "http://localhost:5001/api/monitor/heartbeats")
STREAM_NAME    = os.getenv("STREAM_NAME", "reports")
CONSUMER_GROUP = os.getenv("CONSUMER_GROUP", "monitor-queue-group")
CONSUMER_NAME  = os.getenv("CONSUMER_NAME", "worker-1")
BLOCK_MS       = int(os.getenv("BLOCK_MS", 5000))
MAX_RETRIES    = int(os.getenv("MAX_RETRIES", 12))


def _forward(payload_bytes: bytes, retries: int = 0) -> None:
    req = Request(
        MONITOR_URL,
        data=payload_bytes,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=10) as resp:
            resp.read()
    except (HTTPError, URLError) as exc:
        if retries >= MAX_RETRIES:
            log.error("Max retries reached, dropping message: %s", exc)
            return
        wait = min(2 ** retries, 300) + (0.1 * retries)
        log.warning("Forward failed (%s), retry %d in %.1fs", exc, retries + 1, wait)
        time.sleep(wait)
        _forward(payload_bytes, retries + 1)


def _ensure_group(r: redis.Redis) -> None:
    try:
        r.xgroup_create(STREAM_NAME, CONSUMER_GROUP, id="0", mkstream=True)
        log.info("Created consumer group '%s' on stream '%s'", CONSUMER_GROUP, STREAM_NAME)
    except redis.exceptions.ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise


def run() -> None:
    r = redis.from_url(REDIS_URL, decode_responses=True)
    _ensure_group(r)
    log.info("Listening on stream '%s' as '%s/%s' → %s", STREAM_NAME, CONSUMER_GROUP, CONSUMER_NAME, MONITOR_URL)

    while True:
        try:
            results = r.xreadgroup(
                CONSUMER_GROUP,
                CONSUMER_NAME,
                {STREAM_NAME: ">"},
                count=10,
                block=BLOCK_MS,
            )
        except redis.exceptions.ConnectionError as exc:
            log.error("Redis connection error: %s — retrying in 5s", exc)
            time.sleep(5)
            continue

        if not results:
            continue

        for _stream, messages in results:
            for msg_id, fields in messages:
                raw = fields.get("payload", "{}")
                try:
                    payload_obj = json.loads(raw)
                    payload_bytes = json.dumps(payload_obj).encode("utf-8")
                    _forward(payload_bytes)
                    r.xack(STREAM_NAME, CONSUMER_GROUP, msg_id)
                    log.info("ACK %s  service=%s  status=%s", msg_id, payload_obj.get("service"), payload_obj.get("status"))
                except Exception as exc:
                    log.error("Failed to process message %s: %s", msg_id, exc)


if __name__ == "__main__":
    run()
