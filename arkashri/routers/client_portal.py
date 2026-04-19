# pyre-ignore-all-errors
import secrets
import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, EmailStr

from arkashri.dependencies import get_session, require_api_client
from arkashri.models import ClientRole
from arkashri.services.security import AuthContext
from arkashri.services.email import send_email
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
    engagement = await session.scalar(select(Engagement).where(Engagement.id == engagement_id))
    if not engagement:
        raise HTTPException(status_code=404, detail="Engagement not found")

    token = secrets.token_urlsafe(32)
    expires_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=payload.expires_in_days)
    
    access = ClientPortalAccess(
        engagement_id=engagement_id,
        client_email=payload.client_email,
        token=token,
        expires_at=expires_at
    )
    session.add(access)
    await session.commit()
    
    return {
        "status": "success",
        "engagement_id": str(engagement_id),
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
        
    if access.expires_at < datetime.datetime.now(datetime.timezone.utc):
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
        ]
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
