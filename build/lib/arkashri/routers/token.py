# pyre-ignore-all-errors
"""
routers/token.py — JWT Authentication Endpoint
===============================================
Issues real HS256 JWTs using python-jose.
Validates against the platform_user table (DB users, not hardcoded dict).

Endpoints:
  POST /token            Login → access + refresh token
  POST /token/refresh    Refresh access token using refresh token
  POST /token/verify     Verify a token is valid (for API gateway health checks)
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status, Request, Header, Query, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from arkashri.config import get_settings
from arkashri.db import get_session
from arkashri.models import User
from arkashri.services.auth_sessions import (
    create_login_session,
    revoke_access_session,
    revoke_refresh_session,
    rotate_refresh_session,
)
from arkashri.services.password import verify_password
from arkashri.services.jwt_service import (
    create_ws_ticket,
    decode_token,
)
from arkashri.dependencies import limiter
from arkashri.dependencies import get_current_user, load_active_user_from_claims, serialize_platform_user

router = APIRouter()


# ─── Schemas ──────────────────────────────────────────────────────────────────

class TokenRequest(BaseModel):
    email:    str
    password: str

class TokenResponse(BaseModel):
    access_token:  str
    refresh_token: str
    token_type:    str = "bearer"
    expires_in:    int
    user: dict

class RefreshRequest(BaseModel):
    refresh_token: str

class LogoutRequest(BaseModel):
    refresh_token: str | None = None

class VerifyRequest(BaseModel):
    token: str


class VerifyResponse(BaseModel):
    valid: bool
    exp: int
    user: dict


class WSTicketResponse(BaseModel):
    ticket: str
    tenant_id: str
    jurisdiction: str
    expires_in: int


# ─── POST /token — Login ──────────────────────────────────────────────────────

@router.post("/", response_model=TokenResponse, status_code=status.HTTP_200_OK)
@limiter.limit("5/minute")
async def issue_token(
    request: Request,
    payload: TokenRequest,
    _tenant_header: str = Header(default="default_tenant", alias="X-Arkashri-Tenant"),
    db: AsyncSession = Depends(get_session),
) -> TokenResponse:
    """
    Authenticate with email + password.
    Returns a real HS256 JWT access token + refresh token.
    Compatible with: Postman, API gateways, Auth0 JWT validation middleware.
    """
    email = payload.email.strip().lower()

    user = (await db.scalars(
        select(User).where(
            User.tenant_id == _tenant_header,
            User.email == email,
            User.is_active.is_(True),
        )
    )).first()

    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    bundle = await create_login_session(db, user=user, request=request)
    await db.commit()

    return TokenResponse(
        access_token=bundle.access_token,
        refresh_token=bundle.refresh_token,
        expires_in=bundle.expires_in,
        user={
            **serialize_platform_user(user),
        },
    )


# ─── POST /token/refresh ──────────────────────────────────────────────────────

@router.post("/refresh", response_model=TokenResponse)
@limiter.limit("10/minute")
async def refresh_token(
    request: Request,
    payload: RefreshRequest,
    db: AsyncSession = Depends(get_session),
) -> TokenResponse:
    """
    Exchange a valid refresh token for a new access + refresh token pair.
    Use when access token is approaching expiry (< 1h remaining).
    """
    user, bundle = await rotate_refresh_session(
        db,
        refresh_token=payload.refresh_token,
        request=request,
    )

    return TokenResponse(
        access_token=bundle.access_token,
        refresh_token=bundle.refresh_token,
        expires_in=bundle.expires_in,
        user={
            **serialize_platform_user(user),
        },
    )


# ─── POST /token/verify ───────────────────────────────────────────────────────

@router.post("/verify", response_model=VerifyResponse)
async def verify_token(
    payload: VerifyRequest,
    db: AsyncSession = Depends(get_session),
) -> dict:
    """
    Validate a JWT and return its decoded claims.
    Use this from API gateways / health checks to confirm token validity.
    Returns 401 if invalid or expired.
    """
    claims = decode_token(payload.token)
    user = await load_active_user_from_claims(db, claims)
    return {
        "valid":     True,
        "exp":       claims.get("exp"),
        "user":      serialize_platform_user(user),
    }


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def logout_token(
    payload: LogoutRequest,
    db: AsyncSession = Depends(get_session),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> Response:
    revoked = False

    if payload.refresh_token:
        revoked = await revoke_refresh_session(
            db,
            refresh_token=payload.refresh_token,
            reason="logout",
        ) or revoked

    if authorization and authorization.startswith("Bearer "):
        try:
            claims = decode_token(authorization.removeprefix("Bearer ").strip())
        except HTTPException:
            claims = None
        if claims is not None:
            revoked = await revoke_access_session(
                db,
                claims=claims,
                reason="logout",
            ) or revoked

    if not revoked:
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/ws-ticket", response_model=WSTicketResponse)
async def issue_ws_ticket(
    jurisdiction: str = Query(default="IN", min_length=2, max_length=20),
    current_user: dict = Depends(get_current_user),
) -> WSTicketResponse:
    normalized_jurisdiction = jurisdiction.strip().upper()
    user_id = str(current_user.get("user_id") or current_user.get("id") or current_user.get("sub"))
    tenant_id = str(current_user["tenant_id"])
    ticket = create_ws_ticket(
        user_id=user_id,
        tenant_id=tenant_id,
        jurisdiction=normalized_jurisdiction,
    )

    return WSTicketResponse(
        ticket=ticket,
        tenant_id=tenant_id,
        jurisdiction=normalized_jurisdiction,
        expires_in=get_settings().ws_ticket_expiry_seconds,
    )
