# pyre-ignore-all-errors
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from arkashri.db import get_session
from arkashri.dependencies import AuthContext, require_api_client
from arkashri.models import ClientRole
from arkashri.services.bank_ingestion import (
    BankIngestionError,
    BankIngestionResult,
    ingest_bank_records,
    parse_bank_csv,
)

router = APIRouter()


class BankAPIIngestionRequest(BaseModel):
    jurisdiction: str = Field(default="IN", min_length=2, max_length=20)
    default_currency: str = Field(default="INR", min_length=3, max_length=3)
    records: list[dict] = Field(..., min_length=1, max_length=5000)


class BankIngestionOut(BaseModel):
    source: str
    records_submitted: int
    records_ingested: int
    records_failed: int
    duplicate_refs: list[str]


def _serialize_result(result: BankIngestionResult, *, source: str) -> BankIngestionOut:
    return BankIngestionOut(
        source=source,
        records_submitted=result.records_submitted,
        records_ingested=result.records_ingested,
        records_failed=result.records_failed,
        duplicate_refs=result.duplicate_refs,
    )


@router.post(
    "/bank/ingestions/csv",
    response_model=BankIngestionOut,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest bank transactions from a CSV upload",
)
async def ingest_bank_csv(
    file: UploadFile = File(...),
    jurisdiction: str = Form(default="IN"),
    default_currency: str = Form(default="INR"),
    column_mapping_json: str | None = Form(default=None),
    session: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR})),
) -> BankIngestionOut:
    try:
        csv_bytes = await file.read()
        mapping = json.loads(column_mapping_json) if column_mapping_json else None
        if mapping is not None and not isinstance(mapping, dict):
            raise BankIngestionError("column_mapping_json must decode to an object.")
        records = parse_bank_csv(csv_bytes, column_mapping=mapping)
        result = await ingest_bank_records(
            session,
            tenant_id=auth.tenant_id,
            jurisdiction=jurisdiction,
            records=records,
            source="CSV_UPLOAD",
            default_currency=default_currency,
        )
        return _serialize_result(result, source="CSV_UPLOAD")
    except (BankIngestionError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/bank/ingestions/api",
    response_model=BankIngestionOut,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest bank transactions received from an external banking API",
)
async def ingest_bank_api_payload(
    payload: BankAPIIngestionRequest,
    session: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR})),
) -> BankIngestionOut:
    try:
        result = await ingest_bank_records(
            session,
            tenant_id=auth.tenant_id,
            jurisdiction=payload.jurisdiction,
            records=payload.records,
            source="BANK_API",
            default_currency=payload.default_currency,
        )
        return _serialize_result(result, source="BANK_API")
    except BankIngestionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
