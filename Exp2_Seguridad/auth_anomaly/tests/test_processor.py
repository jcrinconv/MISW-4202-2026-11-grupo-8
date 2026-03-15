from __future__ import annotations

import pytest

from auth_anomaly.config import Settings
from auth_anomaly.models import AuthEvent
from auth_anomaly.processor import EventProcessor
from auth_anomaly.rules import RateLimitRule, RepeatedFailureRule


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


@pytest.mark.asyncio
async def test_processor_isolates_history_by_simulation_uuid() -> None:
    settings = Settings()
    settings.notify_enabled = False
    notifier = StubNotifier()
    rules = [RepeatedFailureRule(threshold=2, window_seconds=60)]
    processor = EventProcessor(settings=settings, rules=rules, notifier=notifier)

    event1 = AuthEvent(user="alice", activity="login", status="failed", simulation_uuid="sim-1")
    result1 = await processor.handle_event(event1)
    assert not result1.anomalies

    event2 = AuthEvent(user="alice", activity="login", status="failed", simulation_uuid="sim-2")
    result2 = await processor.handle_event(event2)
    assert not result2.anomalies
    assert result2.notifications == []


@pytest.mark.asyncio
async def test_processor_suppresses_duplicate_rule_notifications_within_window() -> None:
    settings = Settings()
    settings.notify_enabled = False
    notifier = StubNotifier()
    rules = [RateLimitRule(threshold=2, window_seconds=60, activities=["validate"], statuses=["SUCCESS"])]
    processor = EventProcessor(settings=settings, rules=rules, notifier=notifier)

    event1 = AuthEvent(user="alice", activity="validate", status="success", simulation_uuid="sim-1")
    result1 = await processor.handle_event(event1)
    assert not result1.anomalies

    event2 = AuthEvent(user="alice", activity="validate", status="success", simulation_uuid="sim-1")
    result2 = await processor.handle_event(event2)
    assert len(result2.anomalies) == 1
    assert result2.anomalies[0].rule == "rate_limit"

    event3 = AuthEvent(user="alice", activity="validate", status="success", simulation_uuid="sim-1")
    result3 = await processor.handle_event(event3)
    assert result3.anomalies == []
    assert result3.notifications == []
