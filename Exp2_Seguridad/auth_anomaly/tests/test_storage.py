from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from auth_anomaly.models import AnomalyDecision, AuthEvent, NotificationResult, ProcessedEvent
from auth_anomaly.storage import Storage


@pytest.mark.asyncio
async def test_storage_persists_events_and_anomalies(tmp_path: Path) -> None:
    events_db = tmp_path / "events.db"
    anomalies_db = tmp_path / "anomalies.db"
    storage = Storage(events_url=f"sqlite:///{events_db}", anomalies_url=f"sqlite:///{anomalies_db}")
    await storage.startup()

    event = AuthEvent(user="alice", activity="login", status="failed")
    anomaly = AnomalyDecision(
        user="alice",
        activity="login",
        rule="repeated_failures",
        severity="high",
        reason="failures",
        occurred_at=event.occurred_at,
        detected_at=datetime.now(timezone.utc),
        latency_ms=1500,
    )
    processed = ProcessedEvent(
        user=event.user,
        activity=event.activity,
        status=event.status,
        received_at=datetime.now(timezone.utc),
        processed_at=datetime.now(timezone.utc),
        processing_time_ms=1200,
        anomalies=[anomaly],
        notifications=[
            NotificationResult(
                user="alice",
                activity="login",
                rule="repeated_failures",
                detected_at=anomaly.detected_at,
                success=True,
            )
        ],
    )

    await storage.persist(event=event, processed=processed)

    engine_events = create_engine(f"sqlite:///{events_db}", future=True)
    with engine_events.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM auth_events"))
        assert count.scalar_one() == 1

    engine_anomalies = create_engine(f"sqlite:///{anomalies_db}", future=True)
    with engine_anomalies.connect() as conn:
        row = conn.execute(text("SELECT rule, notification_success FROM auth_anomalies"))
        data = row.fetchone()
        assert data is not None
        assert data.rule == "repeated_failures"
        assert data.notification_success == 1
