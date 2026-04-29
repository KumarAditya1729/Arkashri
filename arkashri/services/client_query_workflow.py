from __future__ import annotations

import copy
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from arkashri.models import Engagement

WORKFLOW_KEY = "client_portal_workflow"


class ClientWorkflowError(ValueError):
    pass


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_workflow_bucket(engagement: Engagement) -> dict[str, Any]:
    metadata = copy.deepcopy(engagement.state_metadata or {})
    metadata.setdefault("history", [])
    metadata.setdefault(
        WORKFLOW_KEY,
        {
            "queries": [],
            "approvals": [],
        },
    )
    return metadata


async def _load_engagement(
    session: AsyncSession,
    *,
    engagement_id: uuid.UUID | str,
    tenant_id: str | None = None,
) -> Engagement:
    if not isinstance(engagement_id, uuid.UUID):
        try:
            engagement_id = uuid.UUID(str(engagement_id))
        except ValueError as exc:
            raise ClientWorkflowError("Invalid engagement_id UUID.") from exc
    stmt = select(Engagement).where(Engagement.id == engagement_id)
    if tenant_id is not None:
        stmt = stmt.where(Engagement.tenant_id == tenant_id)
    engagement = await session.scalar(stmt)
    if engagement is None:
        raise ClientWorkflowError("Engagement not found.")
    return engagement


async def create_client_query(
    session: AsyncSession,
    *,
    engagement_id: uuid.UUID,
    tenant_id: str,
    actor_id: str,
    title: str,
    question: str,
    priority: str,
    due_at: str | None,
    requested_documents: list[str],
    client_phone: str | None = None,
    portal_url: str | None = None,
) -> dict[str, Any]:
    engagement = await _load_engagement(session, engagement_id=engagement_id, tenant_id=tenant_id)
    metadata = _ensure_workflow_bucket(engagement)
    workflow = metadata[WORKFLOW_KEY]

    query = {
        "id": str(uuid.uuid4()),
        "title": title,
        "question": question,
        "priority": priority,
        "status": "OPEN",
        "due_at": due_at,
        "requested_documents": requested_documents,
        "client_phone": client_phone,
        "portal_url": portal_url,
        "notifications": [],
        "created_at": _now_iso(),
        "created_by": actor_id,
        "client_response": None,
        "responded_at": None,
        "responded_by_email": None,
        "internal_notes": None,
        "closed_at": None,
        "closed_by": None,
    }
    workflow["queries"].append(query)
    metadata["history"].append(
        {
            "timestamp": _now_iso(),
            "actor": actor_id,
            "action": "CLIENT_QUERY_CREATED",
            "query_id": query["id"],
        }
    )
    engagement.state_metadata = metadata
    session.add(engagement)
    await session.commit()
    await session.refresh(engagement)
    return query


async def update_client_query(
    session: AsyncSession,
    *,
    engagement_id: uuid.UUID,
    tenant_id: str,
    query_id: str,
    actor_id: str,
    status: str | None = None,
    internal_notes: str | None = None,
) -> dict[str, Any]:
    engagement = await _load_engagement(session, engagement_id=engagement_id, tenant_id=tenant_id)
    metadata = _ensure_workflow_bucket(engagement)
    workflow = metadata[WORKFLOW_KEY]

    for query in workflow["queries"]:
        if query["id"] != query_id:
            continue
        if status is not None:
            query["status"] = status
            if status == "CLOSED":
                query["closed_at"] = _now_iso()
                query["closed_by"] = actor_id
        if internal_notes is not None:
            query["internal_notes"] = internal_notes
        metadata["history"].append(
            {
                "timestamp": _now_iso(),
                "actor": actor_id,
                "action": "CLIENT_QUERY_UPDATED",
                "query_id": query_id,
                "status": query["status"],
            }
        )
        engagement.state_metadata = metadata
        session.add(engagement)
        await session.commit()
        await session.refresh(engagement)
        return query

    raise ClientWorkflowError("Client query not found.")


async def respond_to_client_query(
    session: AsyncSession,
    *,
    engagement_id: uuid.UUID,
    query_id: str,
    client_email: str,
    response_text: str,
) -> dict[str, Any]:
    engagement = await _load_engagement(session, engagement_id=engagement_id)
    metadata = _ensure_workflow_bucket(engagement)
    workflow = metadata[WORKFLOW_KEY]

    for query in workflow["queries"]:
        if query["id"] != query_id:
            continue
        query["client_response"] = response_text
        query["responded_at"] = _now_iso()
        query["responded_by_email"] = client_email
        query["status"] = "CLIENT_RESPONDED"
        metadata["history"].append(
            {
                "timestamp": _now_iso(),
                "actor": client_email,
                "action": "CLIENT_QUERY_RESPONDED",
                "query_id": query_id,
            }
        )
        engagement.state_metadata = metadata
        session.add(engagement)
        await session.commit()
        await session.refresh(engagement)
        return query

    raise ClientWorkflowError("Client query not found.")


async def create_client_approval(
    session: AsyncSession,
    *,
    engagement_id: uuid.UUID,
    tenant_id: str,
    actor_id: str,
    title: str,
    summary: str,
    approval_type: str,
    due_at: str | None,
    client_phone: str | None = None,
    portal_url: str | None = None,
) -> dict[str, Any]:
    engagement = await _load_engagement(session, engagement_id=engagement_id, tenant_id=tenant_id)
    metadata = _ensure_workflow_bucket(engagement)
    workflow = metadata[WORKFLOW_KEY]

    approval = {
        "id": str(uuid.uuid4()),
        "title": title,
        "summary": summary,
        "approval_type": approval_type,
        "status": "PENDING",
        "due_at": due_at,
        "client_phone": client_phone,
        "portal_url": portal_url,
        "notifications": [],
        "created_at": _now_iso(),
        "created_by": actor_id,
        "decision": None,
        "decision_notes": None,
        "responded_at": None,
        "responded_by_email": None,
    }
    workflow["approvals"].append(approval)
    metadata["history"].append(
        {
            "timestamp": _now_iso(),
            "actor": actor_id,
            "action": "CLIENT_APPROVAL_CREATED",
            "approval_id": approval["id"],
        }
    )
    engagement.state_metadata = metadata
    session.add(engagement)
    await session.commit()
    await session.refresh(engagement)
    return approval


async def action_client_approval(
    session: AsyncSession,
    *,
    engagement_id: uuid.UUID,
    approval_id: str,
    client_email: str,
    decision: str,
    decision_notes: str | None,
) -> dict[str, Any]:
    if decision not in {"APPROVED", "REJECTED"}:
        raise ClientWorkflowError("Unsupported client approval decision.")

    engagement = await _load_engagement(session, engagement_id=engagement_id)
    metadata = _ensure_workflow_bucket(engagement)
    workflow = metadata[WORKFLOW_KEY]

    for approval in workflow["approvals"]:
        if approval["id"] != approval_id:
            continue
        approval["status"] = decision
        approval["decision"] = decision
        approval["decision_notes"] = decision_notes
        approval["responded_at"] = _now_iso()
        approval["responded_by_email"] = client_email
        metadata["history"].append(
            {
                "timestamp": _now_iso(),
                "actor": client_email,
                "action": "CLIENT_APPROVAL_ACTIONED",
                "approval_id": approval_id,
                "decision": decision,
            }
        )
        engagement.state_metadata = metadata
        session.add(engagement)
        await session.commit()
        await session.refresh(engagement)
        return approval

    raise ClientWorkflowError("Client approval request not found.")


async def record_client_workflow_notification(
    session: AsyncSession,
    *,
    engagement_id: uuid.UUID,
    tenant_id: str,
    item_type: str,
    item_id: str,
    channel: str,
    result: dict[str, Any],
) -> None:
    engagement = await _load_engagement(session, engagement_id=engagement_id, tenant_id=tenant_id)
    metadata = _ensure_workflow_bucket(engagement)
    workflow = metadata[WORKFLOW_KEY]
    bucket_name = "queries" if item_type == "query" else "approvals"

    for item in workflow[bucket_name]:
        if item["id"] != item_id:
            continue
        item.setdefault("notifications", [])
        item["notifications"].append(
            {
                "channel": channel,
                **result,
            }
        )
        metadata["history"].append(
            {
                "timestamp": _now_iso(),
                "actor": "system",
                "action": "CLIENT_NOTIFICATION_RECORDED",
                "item_type": item_type,
                "item_id": item_id,
                "channel": channel,
                "status": result.get("status"),
            }
        )
        engagement.state_metadata = metadata
        session.add(engagement)
        await session.commit()
        return

    raise ClientWorkflowError("Client workflow item not found.")


async def get_client_portal_workflow(
    session: AsyncSession,
    *,
    engagement_id: uuid.UUID,
    tenant_id: str | None = None,
) -> dict[str, Any]:
    engagement = await _load_engagement(session, engagement_id=engagement_id, tenant_id=tenant_id)
    workflow = copy.deepcopy((engagement.state_metadata or {}).get(WORKFLOW_KEY) or {"queries": [], "approvals": []})
    workflow["open_query_count"] = sum(1 for item in workflow["queries"] if item["status"] in {"OPEN", "CLIENT_RESPONDED"})
    workflow["pending_approval_count"] = sum(1 for item in workflow["approvals"] if item["status"] == "PENDING")
    return workflow
