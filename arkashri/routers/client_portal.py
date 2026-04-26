# pyre-ignore-all-errors
import secrets
import datetime
import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, EmailStr, Field

from arkashri.dependencies import get_session, require_api_client
from arkashri.models import ClientRole
from arkashri.services.security import AuthContext
from arkashri.services.email import send_email
from arkashri.services.client_query_workflow import (
    ClientWorkflowError,
    action_client_approval,
    create_client_approval,
    create_client_query,
    get_client_portal_workflow,
    record_client_workflow_notification,
    respond_to_client_query,
    update_client_query,
)
from arkashri.services.whatsapp import send_whatsapp_message
from arkashri.models import (
    Engagement, 
    ClientPortalAccess, 
    ClientPortalNotificationSubscription,
    AuditRun, 
    ProfessionalJudgment,
)

router = APIRouter(prefix="/v1/portal", tags=["Client Portal"])

# ─── 1. Internal API: Generate Access Token ───────────────────────────────────

class PortalAccessRequest(BaseModel):
    client_email: EmailStr
    expires_in_days: int = 30

@router.post("/engagements/{engagement_id}/access")
async def generate_portal_access(
    engagement_id: str,
    payload: PortalAccessRequest,
    session: AsyncSession = Depends(get_session),
    _auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR}))
) -> dict:
    """
    (Internal) Generates a secure, time-limited token for the client to view their audit.
    """
    try:
        eid = uuid.UUID(engagement_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid engagement_id UUID")

    engagement = await session.scalar(select(Engagement).where(Engagement.id == eid))
    if not engagement:
        raise HTTPException(status_code=404, detail="Engagement not found")

    token = secrets.token_urlsafe(32)
    expires_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=payload.expires_in_days)
    
    access = ClientPortalAccess(
        engagement_id=eid,
        client_email=payload.client_email,
        token=token,
        expires_at=expires_at
    )
    session.add(access)
    await session.commit()
    
    return {
        "status": "success",
        "engagement_id": str(eid),
        "client_email": access.client_email,
        "token": token,
        "expires_at": expires_at.isoformat(),
        "portal_url": f"/portal/{token}" # Example relative URL
    }


# ─── Dependency for Client Tokens ─────────────────────────────────────────────

async def verify_portal_token(
    token: str,
    session: AsyncSession = Depends(get_session)
) -> ClientPortalAccess:
    if not token:
        raise HTTPException(status_code=401, detail="Portal token missing")
        
    access = await session.scalar(select(ClientPortalAccess).where(ClientPortalAccess.token == token))
    
    if not access:
        raise HTTPException(status_code=401, detail="Invalid portal token")

    expires_at = access.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=datetime.timezone.utc)

    if expires_at < datetime.datetime.now(datetime.timezone.utc):
        raise HTTPException(status_code=401, detail="Portal token expired")
        
    # Update last accessed
    access.last_accessed = datetime.datetime.now(datetime.timezone.utc)
    session.add(access)
    await session.commit()
    await session.refresh(access)
    
    return access


# ─── 2. Client API: View Dashboard ────────────────────────────────────────────

@router.get("/dashboard")
async def get_portal_dashboard(
    token: str, # Passed as a query param for simplicity in the URL
    session: AsyncSession = Depends(get_session)
) -> dict:
    """
    (External) Read-only view for the audited client. Returns general status but NO internal risk scores.
    """
    access = await verify_portal_token(token, session)
    
    engagement = await session.scalar(select(Engagement).where(Engagement.id == access.engagement_id))
    if not engagement:
        raise HTTPException(status_code=404, detail="Engagement associated with this token is missing")

    # Fetch high-level runs to show active workflows
    runs = (await session.scalars(
        select(AuditRun)
        .where(AuditRun.tenant_id == engagement.tenant_id) # Using tenant_id here, but normally would map to engagement
        .order_by(AuditRun.created_at.desc())
        .limit(5)
    )).all()
    
    # Check for pending judgments that might require client input, but don't expose ai_confidence
    judgments = (await session.scalars(
        select(ProfessionalJudgment)
        .where(ProfessionalJudgment.engagement_id == engagement.id)
    )).all()
    workflow = await get_client_portal_workflow(session, engagement_id=engagement.id)

    return {
        "client_name": engagement.client_name,
        "engagement_type": engagement.engagement_type.value,
        "status": engagement.status.value,
        "sealed": bool(engagement.sealed_at),
        "sealed_at": engagement.sealed_at.isoformat() if engagement.sealed_at else None,
        "kyc_cleared": engagement.kyc_cleared,
        "independence_cleared": engagement.independence_cleared,
        "recent_activity": [
            {
                "workflow": run.workflow_id,
                "status": run.status.value,
                "started_at": run.started_at.isoformat() if run.started_at else None,
            } for run in runs
        ],
        "estimates_under_review": [
            {
                "area": j.area,
                "status": j.status.value
            } for j in judgments
        ],
        "client_requests": {
            "open_queries": workflow["open_query_count"],
            "pending_approvals": workflow["pending_approval_count"],
        },
    }


# ─── 3. Client API: Timeline ──────────────────────────────────────────────────

@router.get("/timeline")
async def get_portal_timeline(
    token: str,
    session: AsyncSession = Depends(get_session)
) -> dict:
    """
    (External) A linear timeline of the audit's progress.
    """
    access = await verify_portal_token(token, session)
    engagement = await session.scalar(select(Engagement).where(Engagement.id == access.engagement_id))

    timeline = []
    
    # 1. Start
    timeline.append({
        "event": "Audit Engagement Created",
        "timestamp": engagement.created_at.isoformat(),
        "type": "MILESTONE"
    })
    
    # 2. KYC / Independence
    if engagement.kyc_cleared:
        timeline.append({
            "event": "KYC Verified",
            "timestamp": engagement.updated_at.isoformat(), # Rough approx
            "type": "COMPLIANCE"
        })
        
    # 3. Seal (End)
    if engagement.sealed_at:
        timeline.append({
            "event": "Audit Cryptographically Sealed",
            "timestamp": engagement.sealed_at.isoformat(),
            "type": "COMPLETION",
            "hash": engagement.seal_hash
        })
        
    timeline.sort(key=lambda x: x["timestamp"])

    return {
        "engagement_id": str(engagement.id),
        "timeline": timeline
    }


# ─── 4. Client API: Subscribe to Notifications ────────────────────────────────

class SubscribeRequest(BaseModel):
    email: EmailStr


class ClientQueryCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    question: str = Field(min_length=1, max_length=4000)
    priority: str = Field(default="MEDIUM", min_length=1, max_length=32)
    due_at: str | None = None
    requested_documents: list[str] = Field(default_factory=list)
    client_phone: str | None = Field(default=None, max_length=32)
    portal_url: str | None = Field(default=None, max_length=1000)
    notify_whatsapp: bool = True


class ClientQueryUpdateRequest(BaseModel):
    status: str | None = None
    internal_notes: str | None = Field(default=None, max_length=4000)


class ClientQueryResponseRequest(BaseModel):
    response_text: str = Field(min_length=1, max_length=4000)


class ClientApprovalCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    summary: str = Field(min_length=1, max_length=4000)
    approval_type: str = Field(default="CLIENT_CONFIRMATION", min_length=1, max_length=64)
    due_at: str | None = None
    client_phone: str | None = Field(default=None, max_length=32)
    portal_url: str | None = Field(default=None, max_length=1000)
    notify_whatsapp: bool = True


class ClientApprovalActionRequest(BaseModel):
    decision: str = Field(min_length=1, max_length=32)
    decision_notes: str | None = Field(default=None, max_length=4000)

@router.post("/notifications/subscribe")
async def subscribe_to_milestones(
    token: str,
    payload: SubscribeRequest,
    session: AsyncSession = Depends(get_session)
) -> dict:
    """
    (External) Allows a client to subscribe to email alerts for major audit milestones.
    """
    access = await verify_portal_token(token, session)

    if payload.email.lower() != access.client_email.lower():
        raise HTTPException(status_code=400, detail="Subscription email must match the portal access email")

    subscription = await session.scalar(
        select(ClientPortalNotificationSubscription).where(
            ClientPortalNotificationSubscription.engagement_id == access.engagement_id,
            ClientPortalNotificationSubscription.email == payload.email,
        )
    )
    now = datetime.datetime.now(datetime.timezone.utc)
    created = False
    if subscription is None:
        subscription = ClientPortalNotificationSubscription(
            engagement_id=access.engagement_id,
            email=payload.email,
            is_active=True,
            confirmed_at=now,
        )
        session.add(subscription)
        created = True
    else:
        subscription.is_active = True
        subscription.confirmed_at = now
        session.add(subscription)

    await session.commit()

    email_dispatched = await send_email(
        to_addresses=[payload.email],
        subject="Arkashri portal milestone notifications enabled",
        body_text=(
            "Milestone notifications have been enabled for your engagement portal access. "
            "You will receive updates when major audit milestones are recorded."
        ),
    )

    return {
        "status": "success",
        "subscription_created": created,
        "email_delivery_configured": email_dispatched,
        "message": f"Milestone notifications are active for {payload.email}.",
    }


@router.post("/engagements/{engagement_id}/queries")
async def create_portal_query(
    engagement_id: str,
    payload: ClientQueryCreateRequest,
    session: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR, ClientRole.REVIEWER})),
) -> dict:
    try:
        query = await create_client_query(
            session,
            engagement_id=engagement_id,
            tenant_id=auth.tenant_id,
            actor_id=auth.client_name,
            title=payload.title,
            question=payload.question,
            priority=payload.priority.upper(),
            due_at=payload.due_at,
            requested_documents=payload.requested_documents,
            client_phone=payload.client_phone,
            portal_url=payload.portal_url,
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail.lower() else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc
    if payload.notify_whatsapp and payload.client_phone:
        message = (
            f"Arkashri audit query for {query['title']}: {query['question']}"
            + (f" Portal: {payload.portal_url}" if payload.portal_url else "")
        )
        result = await send_whatsapp_message(to_phone=payload.client_phone, message=message)
        notification = {"channel": "WHATSAPP", **result.to_dict()}
        await record_client_workflow_notification(
            session,
            engagement_id=engagement_id,
            tenant_id=auth.tenant_id,
            item_type="query",
            item_id=query["id"],
            channel="WHATSAPP",
            result=result.to_dict(),
        )
        query.setdefault("notifications", []).append(notification)
    return {"engagement_id": str(engagement_id), "query": query}


@router.get("/engagements/{engagement_id}/workflow")
async def get_internal_portal_workflow(
    engagement_id: str,
    session: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR, ClientRole.REVIEWER, ClientRole.READ_ONLY})),
) -> dict:
    try:
        workflow = await get_client_portal_workflow(
            session,
            engagement_id=engagement_id,
            tenant_id=auth.tenant_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"engagement_id": str(engagement_id), "workflow": workflow}


@router.patch("/engagements/{engagement_id}/queries/{query_id}")
async def update_portal_query(
    engagement_id: str,
    query_id: str,
    payload: ClientQueryUpdateRequest,
    session: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR, ClientRole.REVIEWER})),
) -> dict:
    try:
        query = await update_client_query(
            session,
            engagement_id=engagement_id,
            tenant_id=auth.tenant_id,
            query_id=query_id,
            actor_id=auth.client_name,
            status=payload.status,
            internal_notes=payload.internal_notes,
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail.lower() else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc
    return {"engagement_id": str(engagement_id), "query": query}


@router.post("/engagements/{engagement_id}/approvals")
async def create_portal_approval(
    engagement_id: str,
    payload: ClientApprovalCreateRequest,
    session: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR, ClientRole.REVIEWER})),
) -> dict:
    try:
        approval = await create_client_approval(
            session,
            engagement_id=engagement_id,
            tenant_id=auth.tenant_id,
            actor_id=auth.client_name,
            title=payload.title,
            summary=payload.summary,
            approval_type=payload.approval_type,
            due_at=payload.due_at,
            client_phone=payload.client_phone,
            portal_url=payload.portal_url,
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail.lower() else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc
    if payload.notify_whatsapp and payload.client_phone:
        message = (
            f"Arkashri approval request: {approval['title']}. {approval['summary']}"
            + (f" Portal: {payload.portal_url}" if payload.portal_url else "")
        )
        result = await send_whatsapp_message(to_phone=payload.client_phone, message=message)
        notification = {"channel": "WHATSAPP", **result.to_dict()}
        await record_client_workflow_notification(
            session,
            engagement_id=engagement_id,
            tenant_id=auth.tenant_id,
            item_type="approval",
            item_id=approval["id"],
            channel="WHATSAPP",
            result=result.to_dict(),
        )
        approval.setdefault("notifications", []).append(notification)
    return {"engagement_id": str(engagement_id), "approval": approval}


@router.get("/requests")
async def get_portal_requests(
    token: str,
    session: AsyncSession = Depends(get_session),
) -> dict:
    access = await verify_portal_token(token, session)
    workflow = await get_client_portal_workflow(session, engagement_id=access.engagement_id)
    return {
        "engagement_id": str(access.engagement_id),
        "client_email": access.client_email,
        "queries": workflow["queries"],
        "approvals": workflow["approvals"],
        "open_query_count": workflow["open_query_count"],
        "pending_approval_count": workflow["pending_approval_count"],
    }


@router.post("/queries/{query_id}/respond")
async def respond_portal_query(
    query_id: str,
    payload: ClientQueryResponseRequest,
    token: str,
    session: AsyncSession = Depends(get_session),
) -> dict:
    access = await verify_portal_token(token, session)
    try:
        query = await respond_to_client_query(
            session,
            engagement_id=access.engagement_id,
            query_id=query_id,
            client_email=access.client_email,
            response_text=payload.response_text,
        )
    except ClientWorkflowError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"engagement_id": str(access.engagement_id), "query": query}


@router.post("/approvals/{approval_id}/act")
async def act_portal_approval(
    approval_id: str,
    payload: ClientApprovalActionRequest,
    token: str,
    session: AsyncSession = Depends(get_session),
) -> dict:
    access = await verify_portal_token(token, session)
    try:
        approval = await action_client_approval(
            session,
            engagement_id=access.engagement_id,
            approval_id=approval_id,
            client_email=access.client_email,
            decision=payload.decision.upper(),
            decision_notes=payload.decision_notes,
        )
    except ClientWorkflowError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail.lower() else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc
    return {"engagement_id": str(access.engagement_id), "approval": approval}
