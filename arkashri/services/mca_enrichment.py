from __future__ import annotations

import copy
import re
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from arkashri.config import get_settings
from arkashri.models import Engagement

MCA_MASTER_KEY = "mca_company_master"
CIN_RE = re.compile(r"^[A-Z0-9]{21}$")


class MCAEnrichmentError(ValueError):
    pass


def normalize_cin(cin: str) -> str:
    normalized = str(cin or "").strip().upper()
    if not CIN_RE.fullmatch(normalized):
        raise MCAEnrichmentError("CIN must be a 21-character MCA corporate identification number.")
    return normalized


def normalize_mca_master_data(cin: str, raw_data: dict[str, Any], *, source: str) -> dict[str, Any]:
    data = copy.deepcopy(raw_data or {})
    legal_name = data.get("company_name") or data.get("legal_name") or data.get("name")
    if not legal_name:
        raise MCAEnrichmentError("MCA master data must include company_name/legal_name.")

    directors = data.get("directors") or []
    if not isinstance(directors, list):
        raise MCAEnrichmentError("MCA directors must be a list when provided.")

    charges = data.get("charges") or []
    if not isinstance(charges, list):
        raise MCAEnrichmentError("MCA charges must be a list when provided.")

    return {
        "cin": normalize_cin(data.get("cin") or cin),
        "company_name": str(legal_name).strip(),
        "company_status": str(data.get("company_status") or data.get("status") or "UNKNOWN").strip().upper(),
        "company_category": data.get("company_category") or data.get("category"),
        "company_subcategory": data.get("company_subcategory") or data.get("subcategory"),
        "class_of_company": data.get("class_of_company") or data.get("company_class"),
        "date_of_incorporation": data.get("date_of_incorporation") or data.get("incorporation_date"),
        "registered_office": data.get("registered_office") or data.get("registered_address"),
        "email": data.get("email") or data.get("company_email"),
        "listed_status": data.get("listed_status"),
        "authorized_capital": data.get("authorized_capital"),
        "paid_up_capital": data.get("paid_up_capital") or data.get("paidup_capital"),
        "last_agm_date": data.get("last_agm_date"),
        "last_balance_sheet_date": data.get("last_balance_sheet_date"),
        "directors": directors,
        "charges": charges,
        "source": source,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "raw": data,
    }


async def fetch_mca_master_data(cin: str) -> dict[str, Any]:
    settings = get_settings()
    endpoint = getattr(settings, "mca_master_data_url", None)
    if not endpoint:
        raise MCAEnrichmentError(
            "MCA master data URL is not configured. Provide manual_master_data or set MCA_MASTER_DATA_URL."
        )

    headers: dict[str, str] = {}
    api_key = getattr(settings, "mca_api_key", None)
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    async with httpx.AsyncClient(timeout=getattr(settings, "mca_request_timeout_seconds", 20), follow_redirects=True) as client:
        response = await client.get(endpoint, params={"cin": cin}, headers=headers)
        response.raise_for_status()
        payload = response.json()
    if not isinstance(payload, dict):
        raise MCAEnrichmentError("MCA master data provider returned a non-object response.")
    return payload


async def enrich_engagement_with_mca(
    session: AsyncSession,
    *,
    engagement_id: uuid.UUID,
    tenant_id: str,
    cin: str,
    actor_id: str,
    manual_master_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    engagement = await session.scalar(
        select(Engagement).where(
            Engagement.id == engagement_id,
            Engagement.tenant_id == tenant_id,
        )
    )
    if engagement is None:
        raise MCAEnrichmentError("Engagement not found.")

    normalized_cin = normalize_cin(cin)
    raw_data = manual_master_data if manual_master_data is not None else await fetch_mca_master_data(normalized_cin)
    source = "MANUAL" if manual_master_data is not None else "MCA_API"
    snapshot = normalize_mca_master_data(normalized_cin, raw_data, source=source)

    metadata = copy.deepcopy(engagement.state_metadata or {})
    metadata.setdefault("history", [])
    metadata[MCA_MASTER_KEY] = snapshot
    metadata["history"].append(
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "actor": actor_id,
            "action": "MCA_COMPANY_MASTER_ENRICHED",
            "cin": snapshot["cin"],
            "source": source,
        }
    )
    engagement.state_metadata = metadata
    session.add(engagement)
    await session.commit()
    await session.refresh(engagement)
    return copy.deepcopy(snapshot)


async def get_engagement_mca_snapshot(
    session: AsyncSession,
    *,
    engagement_id: uuid.UUID,
    tenant_id: str,
) -> dict[str, Any]:
    engagement = await session.scalar(
        select(Engagement).where(
            Engagement.id == engagement_id,
            Engagement.tenant_id == tenant_id,
        )
    )
    if engagement is None:
        raise MCAEnrichmentError("Engagement not found.")
    metadata = engagement.state_metadata or {}
    return copy.deepcopy(metadata.get(MCA_MASTER_KEY) or {})
