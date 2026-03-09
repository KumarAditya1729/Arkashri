from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from arkashri.db import get_session
from arkashri.models import ClientRole, ApiClient
from arkashri.schemas import (
    ApiClientBootstrapRequest,
    ApiClientCreateRequest,
    ApiClientCreateResponse,
    ApiClientOut,
)
from arkashri.services.security import AuthContext, create_api_client_key
from arkashri.dependencies import require_api_client

router = APIRouter()

@router.post("/bootstrap-admin", response_model=ApiClientCreateResponse, status_code=status.HTTP_201_CREATED)
async def bootstrap_admin_key(
    payload: ApiClientBootstrapRequest,
    bootstrap_token: str | None = Header(default=None, alias="X-Arkashri-Bootstrap-Token"),
    session: AsyncSession = Depends(get_session),
) -> ApiClientCreateResponse:
    from arkashri.config import get_settings
    settings = get_settings()

    if not settings.bootstrap_admin_token:
        raise HTTPException(status_code=403, detail="Bootstrap disabled (token not configured)")
    if bootstrap_token != settings.bootstrap_admin_token:
        raise HTTPException(status_code=401, detail="Invalid bootstrap token")

    client, raw_key = await create_api_client_key(session, name=payload.name, role=ClientRole.ADMIN)
    await session.commit()
    return ApiClientCreateResponse(client=ApiClientOut.model_validate(client), api_key=raw_key)


@router.post("/api-clients", response_model=ApiClientCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_api_client(
    payload: ApiClientCreateRequest,
    session: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN})),
) -> ApiClientCreateResponse:
    client, raw_key = await create_api_client_key(session, name=payload.name, role=payload.role)
    await session.commit()
    return ApiClientCreateResponse(client=ApiClientOut.model_validate(client), api_key=raw_key)


@router.get("/api-clients", response_model=list[ApiClientOut])
async def list_api_clients(
    session: AsyncSession = Depends(get_session),
    _auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN})),
) -> list[ApiClient]:
    from sqlalchemy import select
    return list(await session.scalars(select(ApiClient).order_by(ApiClient.created_at.desc())))


@router.post("/api-clients/{client_id}/deactivate", response_model=dict)
async def deactivate_api_client(
    client_id: int,
    session: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN})),
) -> dict:
    from sqlalchemy import select, update
    client = await session.scalar(select(ApiClient).where(ApiClient.id == client_id))
    if client is None:
        raise HTTPException(status_code=404, detail="API Client not found")
    if client.id == auth.client_id:
        raise HTTPException(status_code=400, detail="Cannot deactivate own API key")

    await session.execute(update(ApiClient).where(ApiClient.id == client_id).values(is_active=False))
    await session.commit()
    return {"status": "deactivated", "client_id": client_id}
