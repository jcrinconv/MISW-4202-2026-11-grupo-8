from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pytest

from auth_anomaly.rules import (
    RateLimitRule,
    RepeatedFailureRule,
    TokenReplayRule,
    UserHistory,
)
from auth_anomaly.models import AuthEvent


@pytest.mark.asyncio
async def test_repeated_failure_rule_detects_bruteforce() -> None:
    rule = RepeatedFailureRule(threshold=3, window_seconds=120)
    history = UserHistory()
    base_time = datetime.now(timezone.utc)

    for i in range(2):
        event = AuthEvent(
            user="alice",
            activity="login",
            status="FAILED",
            detail=f"attempt {i}",
            occurred_at=base_time - timedelta(seconds=10 * (2 - i)),
        )
        history.append(event, recorded_at=event.occurred_at)
        await rule.evaluate(event, history)

    last_event = AuthEvent(
        user="alice",
        activity="login",
        status="failed",
        detail="attempt 3",
        occurred_at=base_time,
    )
    history.append(last_event, recorded_at=last_event.occurred_at)
    decision = await rule.evaluate(last_event, history)

    assert decision is not None
    assert decision.rule == "repeated_failures"
    assert "3 failures" in decision.reason


@pytest.mark.asyncio
async def test_token_replay_rule_flags_token_used_by_other_user() -> None:
    rule = TokenReplayRule(ttl_seconds=300)
    alice_history = UserHistory()
    bob_history = UserHistory()

    first_event = AuthEvent(
        user="alice",
        activity="login",
        status="success",
        auth_token="jwt-123",
        occurred_at=datetime.now(timezone.utc),
    )
    alice_history.append(first_event)
    assert await rule.evaluate(first_event, alice_history) is None

    second_event = AuthEvent(
        user="bob",
        activity="login",
        status="success",
        auth_token="jwt-123",
        occurred_at=datetime.now(timezone.utc),
    )
    bob_history.append(second_event)
    decision = await rule.evaluate(second_event, bob_history)

    assert decision is not None
    assert decision.rule == "token_replay"
    assert "bob" in decision.reason


@pytest.mark.asyncio
async def test_rate_limit_rule_detects_excessive_activity() -> None:
    rule = RateLimitRule(
        threshold=3,
        window_seconds=60,
        activities=["validate"],
        statuses=["SUCCESS"],
    )
    history = UserHistory()
    base_time = datetime.now(timezone.utc)

    for i in range(2):
        event = AuthEvent(
            user="carlos",
            activity="validate",
            status="success",
            detail=f"call {i}",
            occurred_at=base_time - timedelta(seconds=20 * (2 - i)),
        )
        history.append(event, recorded_at=event.occurred_at)
        assert await rule.evaluate(event, history) is None

    last_event = AuthEvent(
        user="carlos",
        activity="validate",
        status="SUCCESS",
        detail="call 3",
        occurred_at=base_time,
    )
    history.append(last_event, recorded_at=last_event.occurred_at)
    decision = await rule.evaluate(last_event, history)

    assert decision is not None
    assert decision.rule == "rate_limit"
    assert "limit" in decision.reason
