from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import httpx
import structlog

from arkashri.config import get_settings

logger = structlog.get_logger("services.whatsapp")


@dataclass
class WhatsAppDispatchResult:
    status: str
    provider_message_id: str | None
    error: str | None
    dispatched_at: str

    def to_dict(self) -> dict[str, str | None]:
        return {
            "status": self.status,
            "provider_message_id": self.provider_message_id,
            "error": self.error,
            "dispatched_at": self.dispatched_at,
        }


async def send_whatsapp_message(*, to_phone: str, message: str) -> WhatsAppDispatchResult:
    settings = get_settings()
    now = datetime.now(timezone.utc).isoformat()
    endpoint = settings.whatsapp_webhook_url or settings.sms_webhook_url
    bearer_token = settings.whatsapp_bearer_token or settings.sms_webhook_bearer_token

    if not endpoint:
        logger.warning("whatsapp_webhook_missing", to_phone=to_phone)
        return WhatsAppDispatchResult(
            status="SKIPPED",
            provider_message_id=None,
            error="WhatsApp webhook URL is not configured.",
            dispatched_at=now,
        )

    headers = {"Content-Type": "application/json"}
    if bearer_token:
        headers["Authorization"] = f"Bearer {bearer_token}"

    payload = {
        "channel": "whatsapp",
        "from": settings.whatsapp_from_number,
        "to": to_phone,
        "message": message,
    }

    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            response = await client.post(endpoint, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json() if response.content else {}
        provider_message_id = data.get("message_id") or data.get("id") if isinstance(data, dict) else None
        return WhatsAppDispatchResult(
            status="SENT",
            provider_message_id=provider_message_id,
            error=None,
            dispatched_at=now,
        )
    except Exception as exc:
        logger.warning("whatsapp_dispatch_failed", to_phone=to_phone, error=str(exc))
        return WhatsAppDispatchResult(
            status="FAILED",
            provider_message_id=None,
            error=str(exc),
            dispatched_at=now,
        )
