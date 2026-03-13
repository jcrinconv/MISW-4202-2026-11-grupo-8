from __future__ import annotations

import pytest

from auth_anomaly.config import Settings
from auth_anomaly.models import AuthEvent
from auth_anomaly.processor import EventProcessor
from auth_anomaly.rules import RepeatedFailureRule


class StubNotifier:
    def __init__(self) -> None:
        self.sent = []

    async def notify(self, decision):  # noqa: D401
        self.sent.append(decision)


@pytest.mark.asyncio
async def test_processor_triggers_rule_and_notifies() -> None:
    settings = Settings()
    settings.notify_enabled = False  # avoid HTTP
    notifier = StubNotifier()
    rules = [RepeatedFailureRule(threshold=2, window_seconds=60)]
    processor = EventProcessor(settings=settings, rules=rules, notifier=notifier)

    event1 = AuthEvent(user="alice", activity="login", status="failed")
    result1 = await processor.handle_event(event1)
    assert not result1.anomalies
    assert result1.notifications == []

    event2 = AuthEvent(user="alice", activity="login", status="failed")
    result2 = await processor.handle_event(event2)

    assert result2.anomalies
    assert result2.anomalies[0].rule == "repeated_failures"
    assert result2.notifications
    assert result2.notifications[0].success is True
