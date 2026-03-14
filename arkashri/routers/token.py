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

import datetime
from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from arkashri.db import get_session
from arkashri.models import User
from arkashri.services.password import verify_password
from arkashri.services.jwt_service import (
    create_access_token,
    create_refresh_token,
    decode_token,
    decode_refresh_token,
)
from arkashri.dependencies import limiter

router = APIRouter()


# ─── Schemas ──────────────────────────────────────────────────────────────────

class TokenRequest(BaseModel):
    email:    str
    password: str

class TokenResponse(BaseModel):
    access_token:  str
    refresh_token: str
    token_type:    str = "bearer"
    expires_in:    int = 86400        # seconds (24h)
    user: dict

class RefreshRequest(BaseModel):
    refresh_token: str

class VerifyRequest(BaseModel):
    token: str


# ─── POST /token — Login ──────────────────────────────────────────────────────

@router.post("/", response_model=TokenResponse, status_code=status.HTTP_200_OK)
@limiter.limit("5/minute")
async def issue_token(
    request: Request,
    payload: TokenRequest,
    db: AsyncSession = Depends(get_session),
) -> TokenResponse:
    """
    Authenticate with email + password.
    Returns a real HS256 JWT access token + refresh token.
    Compatible with: Postman, API gateways, Auth0 JWT validation middleware.
    """
    email = payload.email.strip().lower()

    user = (await db.scalars(
        select(User).where(User.email == email, User.is_active)
    )).first()

    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Update last_login_at
    user.last_login_at = datetime.datetime.now(datetime.timezone.utc)
    db.add(user)
    await db.commit()

    access_token = create_access_token(
        sub=str(user.id),
        email=user.email,
        role=user.role.value,
        tenant_id=user.tenant_id,
        full_name=user.full_name,
        initials=user.initials,
        user_id=str(user.id),
    )
    refresh_token = create_refresh_token(
        sub=str(user.id),
        user_id=str(user.id),
        tenant_id=user.tenant_id,
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user={
            "id":        str(user.id),
            "email":     user.email,
            "full_name": user.full_name,
            "role":      user.role.value,
            "tenant_id": user.tenant_id,
            "initials":  user.initials,
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
    claims = decode_refresh_token(payload.refresh_token)

    user = (await db.scalars(
        select(User).where(User.id == claims["user_id"], User.is_active)
    )).first()
    if not user:
        raise HTTPException(status_code=401, detail="User account not found or deactivated.")

    access_token = create_access_token(
        sub=str(user.id),
        email=user.email,
        role=user.role.value,
        tenant_id=user.tenant_id,
        full_name=user.full_name,
        initials=user.initials,
        user_id=str(user.id),
    )
    new_refresh = create_refresh_token(
        sub=str(user.id),
        user_id=str(user.id),
        tenant_id=user.tenant_id,
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh,
        user={
            "id":        str(user.id),
            "email":     user.email,
            "full_name": user.full_name,
            "role":      user.role.value,
            "tenant_id": user.tenant_id,
            "initials":  user.initials,
        },
    )


# ─── POST /token/verify ───────────────────────────────────────────────────────

@router.post("/verify")
async def verify_token(payload: VerifyRequest) -> dict:
    """
    Validate a JWT and return its decoded claims.
    Use this from API gateways / health checks to confirm token validity.
    Returns 401 if invalid or expired.
    """
    claims = decode_token(payload.token)
    return {
        "valid":     True,
        "sub":       claims.get("sub"),
        "email":     claims.get("email"),
        "role":      claims.get("role"),
        "tenant_id": claims.get("tenant_id"),
        "exp":       claims.get("exp"),
    }
