# pyre-ignore-all-errors
from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from arkashri.db import get_session
from arkashri.dependencies import AuthContext, require_api_client
from arkashri.models import ClientRole
from arkashri.services.books_health import (
    BooksHealthError,
    list_books_health_checks,
    run_books_health_check,
)

router = APIRouter(prefix="/readiness", tags=["Books Health & 7-Day Sprint"])


class BooksHealthRunRequest(BaseModel):
    create_client_queries: bool = False


class BooksHealthRunOut(BaseModel):
    engagement_id: str
    tenant_id: str
    checked_at: str
    readiness_score: int
    seven_day_sprint_status: str
    critical_blocker_count: int
    high_risk_item_count: int
    client_query_count_created: int
    categories: dict[str, Any]
    issues: list[dict[str, Any]]
    created_queries: list[dict[str, Any]]
    next_actions: list[str]


class BooksHealthListOut(BaseModel):
    health_checks: list[dict[str, Any]]


def _parse_engagement_id(engagement_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(engagement_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid engagement_id UUID") from exc


@router.post(
    "/engagements/{engagement_id}/books-health",
    response_model=BooksHealthRunOut,
    status_code=status.HTTP_201_CREATED,
)
async def run_engagement_books_health(
    engagement_id: str,
    payload: BooksHealthRunRequest,
    session: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR, ClientRole.REVIEWER})),
) -> BooksHealthRunOut:
    try:
        result = await run_books_health_check(
            session,
            engagement_id=_parse_engagement_id(engagement_id),
            tenant_id=auth.tenant_id,
            actor_id=auth.client_name,
            create_queries=payload.create_client_queries,
        )
    except BooksHealthError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail.lower() else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc
    return BooksHealthRunOut(**result)


@router.get(
    "/engagements/{engagement_id}/books-health",
    response_model=BooksHealthListOut,
)
async def list_engagement_books_health(
    engagement_id: str,
    session: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(
        require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR, ClientRole.REVIEWER, ClientRole.READ_ONLY})
    ),
) -> BooksHealthListOut:
    try:
        health_checks = await list_books_health_checks(
            session,
            engagement_id=_parse_engagement_id(engagement_id),
            tenant_id=auth.tenant_id,
        )
    except BooksHealthError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return BooksHealthListOut(health_checks=health_checks)
