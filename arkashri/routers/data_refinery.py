# pyre-ignore-all-errors
from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from arkashri.db import get_session
from arkashri.dependencies import AuthContext, require_api_client
from arkashri.models import ClientRole
from arkashri.services.data_refinery import (
    DataRefineryCriticalIssuesError,
    DataRefineryError,
    RefinerySourceType,
    build_excel_refinery_preview,
    build_pdf_bank_statement_intake,
    extract_bank_pdf_with_ocr,
    build_refinery_preview,
    ingest_refined_csv,
)

router = APIRouter(prefix="/data-refinery", tags=["Audit Data Refinery"])


class DataRefineryPreviewOut(BaseModel):
    source_type: str
    source_file_hash: str
    headers: list[str]
    suggested_mapping: dict[str, str]
    total_rows: int
    audit_ready_rows: int
    readiness_score: int
    can_ingest: bool
    issues: list[dict[str, Any]]
    normalized_preview: list[dict[str, Any]]
    category_breakdown: dict[str, int]
    risk_flag_breakdown: dict[str, int]
    quality_dimensions: dict[str, Any]
    column_profiles: dict[str, dict[str, Any]]
    cleaning_suggestions: list[dict[str, str]]


class DataRefineryIngestOut(BaseModel):
    batch_id: str
    engagement_id: str
    source_type: str
    source_file_hash: str
    records_submitted: int
    records_ingested: int
    duplicate_refs: list[str]
    issues: list[dict[str, Any]]
    category_breakdown: dict[str, int]
    risk_flag_breakdown: dict[str, int]


class ExcelRefineryPreviewOut(BaseModel):
    source_type: str
    source_file_hash: str
    sheet_count: int
    total_rows: int
    audit_ready_rows: int
    readiness_score: int
    can_ingest: bool
    sheets: list[dict[str, Any]]


class PdfBankStatementIntakeOut(BaseModel):
    source_type: str
    source_file_hash: str
    status: str
    ocr_provider: str | None = None
    can_ingest: bool
    recommended_action: str
    human_review_required: bool


def _parse_mapping(column_mapping_json: str | None) -> dict[str, str] | None:
    if not column_mapping_json:
        return None
    try:
        parsed = json.loads(column_mapping_json)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="column_mapping_json must be valid JSON.") from exc
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=400, detail="column_mapping_json must decode to an object.")
    return {str(key): str(value) for key, value in parsed.items() if value is not None}


@router.post("/preview", response_model=DataRefineryPreviewOut)
async def preview_raw_csv(
    file: UploadFile = File(...),
    source_type: RefinerySourceType = Form(default="generic_ledger"),
    default_currency: str = Form(default="INR"),
    column_mapping_json: str | None = Form(default=None),
    _auth: AuthContext = Depends(
        require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR, ClientRole.REVIEWER})
    ),
) -> DataRefineryPreviewOut:
    try:
        preview = build_refinery_preview(
            await file.read(),
            source_type=source_type,
            column_mapping=_parse_mapping(column_mapping_json),
            default_currency=default_currency,
        )
    except DataRefineryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return DataRefineryPreviewOut(**preview)


@router.post("/preview-excel", response_model=ExcelRefineryPreviewOut)
async def preview_raw_excel_workbook(
    file: UploadFile = File(...),
    source_type: RefinerySourceType = Form(default="generic_ledger"),
    default_currency: str = Form(default="INR"),
    _auth: AuthContext = Depends(
        require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR, ClientRole.REVIEWER})
    ),
) -> ExcelRefineryPreviewOut:
    try:
        preview = build_excel_refinery_preview(
            await file.read(),
            source_type=source_type,
            default_currency=default_currency,
        )
    except DataRefineryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ExcelRefineryPreviewOut(**preview)


@router.post("/preview-bank-pdf", response_model=PdfBankStatementIntakeOut)
async def preview_bank_statement_pdf(
    file: UploadFile = File(...),
    _auth: AuthContext = Depends(
        require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR, ClientRole.REVIEWER})
    ),
) -> PdfBankStatementIntakeOut:
    try:
        intake = build_pdf_bank_statement_intake(await file.read())
    except DataRefineryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return PdfBankStatementIntakeOut(**intake)


@router.post("/extract-bank-pdf", response_model=dict[str, Any])
async def extract_bank_statement_pdf(
    file: UploadFile = File(...),
    _auth: AuthContext = Depends(
        require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR, ClientRole.REVIEWER})
    ),
) -> dict[str, Any]:
    try:
        return await extract_bank_pdf_with_ocr(await file.read())
    except DataRefineryError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc


@router.post(
    "/engagements/{engagement_id}/ingest-csv",
    response_model=DataRefineryIngestOut,
    status_code=status.HTTP_201_CREATED,
)
async def ingest_raw_csv_to_audit_ready_transactions(
    engagement_id: str,
    file: UploadFile = File(...),
    source_type: RefinerySourceType = Form(default="generic_ledger"),
    default_currency: str = Form(default="INR"),
    column_mapping_json: str | None = Form(default=None),
    session: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR})),
) -> DataRefineryIngestOut:
    try:
        eid = uuid.UUID(engagement_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid engagement_id UUID") from exc

    try:
        result = await ingest_refined_csv(
            session,
            tenant_id=auth.tenant_id,
            engagement_id=eid,
            csv_bytes=await file.read(),
            source_type=source_type,
            column_mapping=_parse_mapping(column_mapping_json),
            default_currency=default_currency,
        )
    except DataRefineryError as exc:
        detail = str(exc)
        status_code = 409 if isinstance(exc, DataRefineryCriticalIssuesError) else 400
        if "not found" in detail.lower():
            status_code = 404
        elif "sealed engagement" in detail.lower():
            status_code = 409
        raise HTTPException(status_code=status_code, detail=detail) from exc
    return DataRefineryIngestOut(**result)
