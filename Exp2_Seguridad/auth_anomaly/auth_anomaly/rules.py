"""Business rules used to detect suspicious authentication behaviour."""

from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
import asyncio
from typing import Deque, Dict, Iterable, List, Optional, Sequence

from .models import AnomalyDecision, AuthEvent


@dataclass(slots=True)
class HistoryEvent:
    event: AuthEvent
    recorded_at: datetime

    def as_dict(self) -> Dict[str, str]:
        return {
            "activity": self.event.activity,
            "status": self.event.status,
            "occurred_at": self.event.occurred_at.isoformat(),
        }


def _prune(events: Deque[HistoryEvent], max_age_seconds: int, now: datetime) -> None:
    while events and (now - events[0].recorded_at).total_seconds() > max_age_seconds:
        events.popleft()


@dataclass(slots=True)
class UserHistory:
    events: Deque[HistoryEvent] = field(default_factory=deque)

    def append(self, event: AuthEvent, *, recorded_at: Optional[datetime] = None) -> None:
        self.events.append(
            HistoryEvent(event=event, recorded_at=recorded_at or datetime.now(timezone.utc))
        )

    def prune(self, max_age_seconds: int, now: Optional[datetime] = None) -> None:
        _prune(self.events, max_age_seconds=max_age_seconds, now=now or datetime.now(timezone.utc))

    def recent(self, window_seconds: int, now: Optional[datetime] = None) -> List[HistoryEvent]:
        now = now or datetime.now(timezone.utc)
        _prune(self.events, max_age_seconds=window_seconds, now=now)
        return list(self.events)


class BaseRule:
    name: str
    severity: str = "medium"
    window_seconds: int = 60

    async def evaluate(self, event: AuthEvent, history: UserHistory) -> Optional[AnomalyDecision]:  # noqa: D401
        raise NotImplementedError

    def _decision(
        self,
        *,
        event: AuthEvent,
        reason: str,
        detected_at: datetime,
        latency_ms: int,
        history: Iterable[HistoryEvent],
    ) -> AnomalyDecision:
        return AnomalyDecision(
            user=event.user,
            activity=event.activity,
            rule=self.name,
            severity=self.severity,
            reason=reason,
            occurred_at=event.occurred_at,
            detected_at=detected_at,
            latency_ms=latency_ms,
            simulation_uuid=event.simulation_uuid,
            metadata=event.metadata or {},
            recent_events=[h.as_dict() for h in history],
        )


class RepeatedFailureRule(BaseRule):
    name = "repeated_failures"

    def __init__(self, *, threshold: int, window_seconds: int) -> None:
        self.threshold = threshold
        self.window_seconds = window_seconds
        self.severity = "high"

    async def evaluate(self, event: AuthEvent, history: UserHistory) -> Optional[AnomalyDecision]:
        if event.status not in {"FAILED", "DENIED", "INVALID", "UNAUTHORIZED"}:
            return None

        now = datetime.now(timezone.utc)
        events = history.recent(self.window_seconds, now)
        failure_count = sum(
            1
            for item in events
            if item.event.status in {"FAILED", "DENIED", "INVALID", "UNAUTHORIZED"}
            and item.event.activity == event.activity
        )
        if failure_count < self.threshold:
            return None

        latency = int((now - event.occurred_at).total_seconds() * 1000)
        return self._decision(
            event=event,
            reason=f"{failure_count} failures for {event.activity} in {self.window_seconds}s",
            detected_at=now,
            latency_ms=max(latency, 0),
            history=events,
        )


class MultiIpBruteforceRule(BaseRule):
    name = "multi_ip_bruteforce"

    def __init__(self, *, unique_threshold: int, window_seconds: int) -> None:
        self.window_seconds = window_seconds
        self.unique_threshold = unique_threshold
        self.severity = "critical"

    async def evaluate(self, event: AuthEvent, history: UserHistory) -> Optional[AnomalyDecision]:
        ip = (event.metadata or {}).get("ip")
        if not ip:
            return None
        if event.status not in {"FAILED", "DENIED", "INVALID", "UNAUTHORIZED"}:
            return None

        now = datetime.now(timezone.utc)
        events = history.recent(self.window_seconds, now)
        ips = [item.event.metadata.get("ip") for item in events if item.event.metadata and item.event.metadata.get("ip")]
        unique_ips = len(set(ips))
        if unique_ips < self.unique_threshold:
            return None

        counts = Counter(ips)
        top_ip = counts.most_common(1)[0][0]
        latency = int((now - event.occurred_at).total_seconds() * 1000)
        return self._decision(
            event=event,
            reason=(
                f"{unique_ips} source IPs failed for user within {self.window_seconds}s."
                f" Most active IP: {top_ip}"
            ),
            detected_at=now,
            latency_ms=max(latency, 0),
            history=events,
        )


class TokenReplayRule(BaseRule):
    name = "token_replay"

    def __init__(self, *, ttl_seconds: int) -> None:
        self.ttl_seconds = ttl_seconds
        self._token_usage: Dict[str, HistoryEvent] = {}
        self._lock = asyncio.Lock()
        self.window_seconds = ttl_seconds
        self.severity = "critical"

    async def evaluate(self, event: AuthEvent, history: UserHistory) -> Optional[AnomalyDecision]:
        token = event.auth_token
        if not token:
            return None

        now = datetime.now(timezone.utc)
        await self._purge(now)

        async with self._lock:
            previous = self._token_usage.get(token)
            latency = int((now - event.occurred_at).total_seconds() * 1000)
            if previous and previous.event.user != event.user:
                reason = (
                    f"Token {token} reused by {event.user} after {previous.event.user} within {self.ttl_seconds}s"
                )
                decision = self._decision(
                    event=event,
                    reason=reason,
                    detected_at=now,
                    latency_ms=max(latency, 0),
                    history=[previous, HistoryEvent(event=event, recorded_at=now)],
                )
                self._token_usage[token] = HistoryEvent(event=event, recorded_at=now)
                return decision

            self._token_usage[token] = HistoryEvent(event=event, recorded_at=now)
            return None

    async def _purge(self, now: datetime) -> None:
        async with self._lock:
            expired = [token for token, info in self._token_usage.items() if (now - info.recorded_at).total_seconds() > self.ttl_seconds]
            for token in expired:
                del self._token_usage[token]


class RateLimitRule(BaseRule):
    name = "rate_limit"

    def __init__(
        self,
        *,
        threshold: int,
        window_seconds: int,
        activities: Sequence[str],
        statuses: Sequence[str],
    ) -> None:
        self.threshold = threshold
        self.window_seconds = window_seconds
        self.activities = {activity.lower() for activity in activities}
        self.statuses = {status.upper() for status in statuses} if statuses else set()
        self.severity = "high"

    async def evaluate(self, event: AuthEvent, history: UserHistory) -> Optional[AnomalyDecision]:
        if event.activity not in self.activities:
            return None
        if self.statuses and event.status not in self.statuses:
            return None

        now = datetime.now(timezone.utc)
        events = history.recent(self.window_seconds, now)
        matching = [
            item
            for item in events
            if item.event.activity == event.activity and (not self.statuses or item.event.status in self.statuses)
        ]
        if len(matching) < self.threshold:
            return None

        latency = int((now - event.occurred_at).total_seconds() * 1000)
        return self._decision(
            event=event,
            reason=(
                f"{len(matching)} {event.activity} requests in {self.window_seconds}s "
                f"(limit {self.threshold})"
            ),
            detected_at=now,
            latency_ms=max(latency, 0),
            history=matching,
        )


__all__ = [
    "BaseRule",
    "UserHistory",
    "HistoryEvent",
    "RepeatedFailureRule",
    "MultiIpBruteforceRule",
    "TokenReplayRule",
    "RateLimitRule",
]
