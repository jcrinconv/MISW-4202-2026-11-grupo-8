"""In-memory event processor that orchestrates rules and notifications."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import datetime, timezone
import logging
from typing import Dict, List, Tuple

from .config import Settings
from .models import AuthEvent, ProcessedEvent, AnomalyDecision, NotificationResult
from .rules import UserHistory, BaseRule
from .auth_client import AuthNotifier
from .storage import Storage

logger = logging.getLogger(__name__)


def _history_key(event: AuthEvent) -> str:
    simulation_uuid = event.simulation_uuid or "__default__"
    return f"{event.user}:{simulation_uuid}"


def _notification_key(event: AuthEvent, rule_name: str) -> str:
    return f"{_history_key(event)}:{rule_name}"


class EventProcessor:
    def __init__(
        self,
        *,
        settings: Settings,
        rules: List[BaseRule],
        notifier: AuthNotifier,
        storage: Storage | None = None,
    ) -> None:
        self._settings = settings
        self._rules = rules
        self._notifier = notifier
        self._storage = storage
        self._histories: Dict[str, UserHistory] = defaultdict(UserHistory)
        self._locks: Dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._last_notifications: Dict[str, datetime] = {}
        self._max_window = max([settings.max_history_seconds] + [rule.window_seconds for rule in rules])

    async def handle_event(self, event: AuthEvent) -> ProcessedEvent:
        received_at = datetime.now(timezone.utc)
        anomalies: List[AnomalyDecision] = []
        blocked_event = self._is_blocked_event(event)
        history_key = _history_key(event)

        if not blocked_event:
            lock = self._locks[history_key]
            async with lock:
                history = self._histories[history_key]
                history.append(event, recorded_at=received_at)
                history.prune(self._max_window, received_at)
                for rule in self._rules:
                    try:
                        decision = await rule.evaluate(event, history)
                    except Exception as exc:  # pragma: no cover - logged only
                        logger.exception("Rule %s failed: %s", rule.name, exc)
                        continue
                    if decision:
                        if self._is_duplicate_notification(event, rule.name, rule.window_seconds, decision.detected_at):
                            continue
                        anomalies.append(decision)

        dispatch_outcomes = [] if blocked_event else await self._dispatch(anomalies)
        notifications = [
            NotificationResult(
                user=decision.user,
                activity=decision.activity,
                rule=decision.rule,
                detected_at=decision.detected_at,
                success=success,
                detail=error,
            )
            for decision, success, error in dispatch_outcomes
        ]

        processed_at = datetime.now(timezone.utc)
        processing_time_ms = int((processed_at - received_at).total_seconds() * 1000)
        if processing_time_ms > self._settings.detection_sla_ms:
            logger.warning(
                "Detection latency %sms exceeded SLA %sms for user=%s",
                processing_time_ms,
                self._settings.detection_sla_ms,
                event.user,
            )

        processed_event = ProcessedEvent(
            user=event.user,
            activity=event.activity,
            status=event.status,
            received_at=received_at,
            processed_at=processed_at,
            processing_time_ms=processing_time_ms,
            anomalies=anomalies,
            notifications=notifications,
        )

        if self._storage:
            await self._storage.persist(event=event, processed=processed_event)

        return processed_event

    def _is_duplicate_notification(
        self,
        event: AuthEvent,
        rule_name: str,
        window_seconds: int,
        detected_at: datetime,
    ) -> bool:
        notification_key = _notification_key(event, rule_name)
        last_notification = self._last_notifications.get(notification_key)
        if last_notification and (detected_at - last_notification).total_seconds() < window_seconds:
            return True
        self._last_notifications[notification_key] = detected_at
        self._prune_notifications(detected_at)
        return False

    def _prune_notifications(self, now: datetime) -> None:
        expired = [
            key
            for key, detected_at in self._last_notifications.items()
            if (now - detected_at).total_seconds() > self._max_window
        ]
        for key in expired:
            del self._last_notifications[key]

    @staticmethod
    def _is_blocked_event(event: AuthEvent) -> bool:
        if event.status == "BLOCKED_USER":
            return True
        return event.activity == "login" and event.status == "DENIED"

    async def _dispatch(self, anomalies: List[AnomalyDecision]) -> List[Tuple[AnomalyDecision, bool, str | None]]:
        if not anomalies:
            return []
        tasks = [self._notifier.notify(anomaly) for anomaly in anomalies]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        outcomes: List[Tuple[AnomalyDecision, bool, str | None]] = []
        for decision, result in zip(anomalies, results):
            if isinstance(result, Exception):
                error_message = str(result)
                logger.error("Auth notification failed: %s", error_message)
                outcomes.append((decision, False, error_message))
            else:
                outcomes.append((decision, True, None))
        return outcomes


__all__ = ["EventProcessor"]
