"""HTTP client for notifying the Auth component when an anomaly is detected."""

from __future__ import annotations

from typing import Any, Dict, Optional
import logging

import httpx

from .config import Settings
from .models import AnomalyDecision

logger = logging.getLogger(__name__)


class AuthNotifier:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: Optional[httpx.AsyncClient] = None

    async def startup(self) -> None:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._settings.http_timeout_seconds)

    async def shutdown(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def notify(self, decision: AnomalyDecision) -> Optional[Dict[str, Any]]:
        if not self._settings.notify_enabled:
            logger.info("Auth notification disabled. Would send: %s", decision.json())
            return None
        if self._client is None:
            raise RuntimeError("AuthNotifier is not initialized")

        payload = {
            "user": decision.user,
            "reason": f"{decision.rule}:{decision.reason}",
            "activity": decision.activity,
            "severity": decision.severity,
            "detected_at": decision.detected_at.isoformat(),
            "metadata": decision.metadata,
            "simulation_uuid": decision.simulation_uuid or decision.metadata.get("simulation_uuid"),
        }

        try:
            response = await self._client.post(self._settings.block_user_url, json=payload)
            response.raise_for_status()
            logger.info(
                "Sent anomaly notification for user=%s rule=%s status=%s",
                decision.user,
                decision.rule,
                response.status_code,
            )
            return response.json() if response.content else {"status": response.status_code}
        except httpx.HTTPError as exc:
            logger.error("Failed to notify auth service: %s", exc)
            raise


__all__ = ["AuthNotifier"]
