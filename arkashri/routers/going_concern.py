# pyre-ignore-all-errors
"""
routers/going_concern.py — SA 570 Going Concern Assessment API
==============================================================
Endpoints:
  POST /going-concern/{engagement_id}/assess
    → Runs full GC assessment with Altman Z, Piotroski F, LLM evaluation
    → Auto-flags ProfessionalJudgment if risk is HIGH or MEDIUM

  POST /going-concern/{engagement_id}/full-analysis
    → All of the above PLUS:
       - GC Risk Score (0–100) with explainability waterfall
       - Ohlson O-Score + Shumway predictive bankruptcy probabilities
       - 12-month cash flow simulation with monthly runway projection
       - Best / Base / Worst case scenario analysis
       - Industry benchmarking vs 12-sector peer database
"""
import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from arkashri.dependencies import get_session, require_api_client, AuthContext
from arkashri.models import Engagement, ClientRole
from arkashri.services.going_concern import (
    GoingConcernFinancials,
    compute_altman_z_score,
    compute_piotroski_f_score,
    compute_liquidity_solvency,
    compute_cash_flow_analysis,
    run_going_concern_assessment,
    going_concern_result_to_dict,
)
from arkashri.services.gc_advanced import (
    compute_gc_risk_score,
    compute_bankruptcy_prediction,
    simulate_12_month_cash_flow,
    run_scenario_analysis,
    benchmark_against_industry,
    advanced_gc_to_dict,
)

router = APIRouter(prefix="/v1/going-concern", tags=["Going Concern (SA 570)"])


class GoingConcernRequest(BaseModel):
    """Input financials for SA 570 Going Concern Assessment."""

    # Balance sheet
    total_assets: float | None = Field(None, description="Total assets")
    total_liabilities: float | None = Field(None, description="Total liabilities")
    current_assets: float | None = Field(None, description="Current assets")
    current_liabilities: float | None = Field(None, description="Current liabilities")
    inventory: float | None = Field(None, description="Inventory (for quick ratio)")
    cash_and_equivalents: float | None = Field(None, description="Cash and cash equivalents")
    retained_earnings: float | None = Field(None, description="Retained earnings (cumulative)")
    market_value_equity: float | None = Field(None, description="Market value of equity (or book value if private)")
    book_value_equity: float | None = Field(None, description="Book value of equity")
    total_debt: float | None = Field(None, description="Total debt (short + long term)")
    long_term_debt: float | None = Field(None, description="Long term debt only")

    # P&L
    revenue: float | None = Field(None, description="Total revenue / sales")
    ebit: float | None = Field(None, description="Earnings before interest and tax")
    net_income: float | None = Field(None, description="Net income / profit after tax")
    net_income_prior_year: float | None = Field(None, description="Prior year net income")
    interest_expense: float | None = Field(None, description="Interest expense")
    gross_profit: float | None = Field(None, description="Gross profit current year")
    gross_profit_prior_year: float | None = Field(None, description="Gross profit prior year")

    # Cash flow
    operating_cash_flow: float | None = Field(None, description="Operating cash flow (CFO) current year")
    operating_cash_flow_prior_year: float | None = Field(None, description="CFO prior year")
    operating_cash_flow_2_years_ago: float | None = Field(None, description="CFO two years ago")
    capital_expenditure: float | None = Field(None, description="Capital expenditure (absolute value)")

    # Derived
    roa_prior: float | None = Field(None, description="Return on assets prior year")
    asset_turnover_prior: float | None = Field(None, description="Asset turnover ratio prior year")
    shares_outstanding: float | None = Field(None, description="Shares outstanding (for dilution check)")

    # Qualitative
    management_going_concern_plan: str | None = Field(
        None,
        description="Management's stated plan to address going concern uncertainty (SA 570 Para 12)"
    )
    known_covenant_breaches: str | None = Field(
        None, description="Details of any loan covenant breaches"
    )
    significant_external_events: str | None = Field(
        None, description="Material external events affecting viability (loss of key customer, market collapse, litigation)"
    )
    industry_sector: str | None = Field(None, description="Industry sector (e.g. Manufacturing, NBFC, IT Services)")
    years_in_operation: int | None = Field(None, description="Years the entity has been in operation")

    # Options
    auto_flag_judgment: bool = Field(
        default=True,
        description="If True, creates a ProfessionalJudgment record when GC risk is HIGH or MEDIUM"
    )


@router.post("/{engagement_id}/assess")
async def assess_going_concern(
    engagement_id: str,
    payload: GoingConcernRequest,
    session: AsyncSession = Depends(get_session),
    _auth: AuthContext = Depends(
        require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR})
    ),
) -> dict:
    """
    Run a full SA 570 Going Concern assessment for an engagement.

    Computes:
    - Altman Z'-Score (non-manufacturing revised)
    - Piotroski F-Score (9-point financial health)
    - Liquidity ratios (current, quick, cash)
    - Solvency ratios (interest coverage, D/E)
    - Cash flow burn analysis (3-year OCF trend)
    - GPT-4o SA 570 structured evaluation
    - Auto-creates ProfessionalJudgment gate if HIGH or MEDIUM risk

    Requires ADMIN or OPERATOR role.
    """
    try:
        eng_id = uuid.UUID(engagement_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid engagement_id UUID format.")

    engagement = await session.scalar(
        select(Engagement).where(Engagement.id == eng_id)
    )
    if not engagement:
        raise HTTPException(status_code=404, detail=f"Engagement {engagement_id} not found.")

    if engagement.tenant_id != _auth.tenant_id:
        raise HTTPException(status_code=403, detail="Access denied: engagement belongs to a different tenant.")

    financials = GoingConcernFinancials(
        total_assets=payload.total_assets,
        total_liabilities=payload.total_liabilities,
        current_assets=payload.current_assets,
        current_liabilities=payload.current_liabilities,
        inventory=payload.inventory,
        cash_and_equivalents=payload.cash_and_equivalents,
        retained_earnings=payload.retained_earnings,
        market_value_equity=payload.market_value_equity,
        book_value_equity=payload.book_value_equity,
        total_debt=payload.total_debt,
        long_term_debt=payload.long_term_debt,
        revenue=payload.revenue,
        ebit=payload.ebit,
        net_income=payload.net_income,
        net_income_prior_year=payload.net_income_prior_year,
        interest_expense=payload.interest_expense,
        gross_profit=payload.gross_profit,
        gross_profit_prior_year=payload.gross_profit_prior_year,
        operating_cash_flow=payload.operating_cash_flow,
        operating_cash_flow_prior_year=payload.operating_cash_flow_prior_year,
        operating_cash_flow_2_years_ago=payload.operating_cash_flow_2_years_ago,
        capital_expenditure=payload.capital_expenditure,
        roa_prior=payload.roa_prior,
        asset_turnover_prior=payload.asset_turnover_prior,
        shares_outstanding=payload.shares_outstanding,
        management_going_concern_plan=payload.management_going_concern_plan,
        known_covenant_breaches=payload.known_covenant_breaches,
        significant_external_events=payload.significant_external_events,
        industry_sector=payload.industry_sector,
        years_in_operation=payload.years_in_operation,
    )

    result = await run_going_concern_assessment(
        session=session,
        engagement_id=eng_id,
        tenant_id=engagement.tenant_id,
        financials=financials,
        auto_flag_judgment=payload.auto_flag_judgment,
    )

    return {
        "status": "success",
        "engagement_id": engagement_id,
        "client_name": engagement.client_name,
        "assessment": going_concern_result_to_dict(result),
        "action_required": (
            "Professional judgment sign-off required before sealing. "
            "Navigate to POST /v1/judgments/{judgment_id}/sign-off with ICAI Reg No."
            if result.judgment_flagged else
            "No mandatory judgment required. GC risk is LOW."
        ),
    }


@router.post("/{engagement_id}/full-analysis")
async def full_gc_analysis(
    engagement_id: str,
    payload: GoingConcernRequest,
    session: AsyncSession = Depends(get_session),
    _auth: AuthContext = Depends(
        require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR})
    ),
) -> dict:
    """
    Full Next-Level Going Concern Analysis — all 7 modules in one call.

    Runs SA 570 base assessment PLUS:
    1. GC Risk Score (0–100) with explainability waterfall per component
    2. Ohlson O-Score (1980) — logistic bankruptcy probability
    3. Shumway Hazard Model (2001) — P(bankrupt 1yr), P(bankrupt 2yr)
    4. 12-month cash flow simulation with monthly runway
    5. Scenario analysis: BEST / BASE / WORST with break-even revenue shock
    6. Industry benchmarking vs 12-sector peer database

    Requires ADMIN or OPERATOR role.
    """
    try:
        eng_id = uuid.UUID(engagement_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid engagement_id UUID format.")

    engagement = await session.scalar(
        select(Engagement).where(Engagement.id == eng_id)
    )
    if not engagement:
        raise HTTPException(status_code=404, detail=f"Engagement {engagement_id} not found.")
    if engagement.tenant_id != _auth.tenant_id:
        raise HTTPException(status_code=403, detail="Access denied: engagement belongs to a different tenant.")

    financials = GoingConcernFinancials(
        total_assets=payload.total_assets,
        total_liabilities=payload.total_liabilities,
        current_assets=payload.current_assets,
        current_liabilities=payload.current_liabilities,
        inventory=payload.inventory,
        cash_and_equivalents=payload.cash_and_equivalents,
        retained_earnings=payload.retained_earnings,
        market_value_equity=payload.market_value_equity,
        book_value_equity=payload.book_value_equity,
        total_debt=payload.total_debt,
        long_term_debt=payload.long_term_debt,
        revenue=payload.revenue,
        ebit=payload.ebit,
        net_income=payload.net_income,
        net_income_prior_year=payload.net_income_prior_year,
        interest_expense=payload.interest_expense,
        gross_profit=payload.gross_profit,
        gross_profit_prior_year=payload.gross_profit_prior_year,
        operating_cash_flow=payload.operating_cash_flow,
        operating_cash_flow_prior_year=payload.operating_cash_flow_prior_year,
        operating_cash_flow_2_years_ago=payload.operating_cash_flow_2_years_ago,
        capital_expenditure=payload.capital_expenditure,
        roa_prior=payload.roa_prior,
        asset_turnover_prior=payload.asset_turnover_prior,
        shares_outstanding=payload.shares_outstanding,
        management_going_concern_plan=payload.management_going_concern_plan,
        known_covenant_breaches=payload.known_covenant_breaches,
        significant_external_events=payload.significant_external_events,
        industry_sector=payload.industry_sector,
        years_in_operation=payload.years_in_operation,
    )

    # ── Run base SA 570 assessment (LLM + judgment gate) ─────────────────────
    base_result = await run_going_concern_assessment(
        session=session,
        engagement_id=eng_id,
        tenant_id=engagement.tenant_id,
        financials=financials,
        auto_flag_judgment=payload.auto_flag_judgment,
    )

    # ── Run advanced modules (pure / synchronous) ─────────────────────────────
    altman    = compute_altman_z_score(financials)
    piotroski = compute_piotroski_f_score(financials)
    liquidity = compute_liquidity_solvency(financials)
    cash_flow = compute_cash_flow_analysis(financials)

    gc_score   = compute_gc_risk_score(financials, altman, piotroski, liquidity, cash_flow)
    bankruptcy = compute_bankruptcy_prediction(financials)
    simulation = simulate_12_month_cash_flow(financials)
    scenarios  = run_scenario_analysis(financials)
    benchmarks = benchmark_against_industry(financials, liquidity, altman, piotroski)

    advanced = advanced_gc_to_dict(gc_score, bankruptcy, simulation, scenarios, benchmarks)

    return {
        "status": "success",
        "engagement_id": engagement_id,
        "client_name": engagement.client_name,
        "executive_summary": {
            "gc_risk":           base_result.gc_risk,
            "gc_score":          gc_score.composite_score,
            "risk_band":         gc_score.risk_band,
            "p_bankrupt_1yr":    bankruptcy.p_bankrupt_1yr,
            "default_risk":      bankruptcy.default_risk,
            "cash_runway":       simulation.runway_label,
            "industry_position": benchmarks.overall_position,
            "stress_resilience": scenarios.stress_resilience,
            "disclosure_required": base_result.disclosure_required,
            "judgment_flagged":  base_result.judgment_flagged,
            "judgment_id":       base_result.judgment_id,
            "key_driver":        gc_score.key_driver,
            "audit_action":      gc_score.audit_action,
        },
        "base_assessment": going_concern_result_to_dict(base_result),
        "advanced": advanced,
        "action_required": (
            "Professional judgment sign-off required before sealing. "
            f"Navigate to POST /v1/judgments/{base_result.judgment_id}/sign-off with ICAI Reg No."
            if base_result.judgment_flagged else
            "No mandatory judgment required. GC risk is LOW."
        ),
    }
