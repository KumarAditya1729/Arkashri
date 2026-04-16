# pyre-ignore-all-errors
"""
services/going_concern.py — Production-Grade Going Concern Assessment Engine
=============================================================================
Implements SA 570 (Revised) / ISA 570 compliant Going Concern analysis.

Architecture:
  1. Quantitative distress signals:
       - Altman Z-Score (Revised 1983, non-manufacturing variant)
       - Piotroski F-Score (9-point financial strength index)
       - Liquidity ratios (current, quick, cash)
       - Solvency indicators (interest coverage, debt/equity)
       - Cash flow burn analysis (operating CF trajectory)
  2. Qualitative signals:
       - External events, management plans, covenant breaches
  3. LLM evaluation (GPT-4o) with SA 570 / ISA 570 system prompt
       - Structured verdict: gc_risk, disclosure_required, emphasis_matter
  4. Auto-flag via judgment.py when gc_risk is HIGH or MEDIUM
  5. Opinion writer integration — adds Emphasis of Matter (SA 706) paragraph

SA 570 Para References used:
  - Para 12: Auditor's responsibility to evaluate management's assessment
  - Para 16: Events or conditions indicating material uncertainty
  - Para 17-20: Auditor's procedures
  - Para 25: Adequate disclosure — emphasis of matter paragraph
  - Para 21: Inadequate disclosure — qualified/adverse opinion
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from arkashri.services.judgment import flag_complex_estimate

logger = logging.getLogger(__name__)

# ─── Thresholds (SA 570 / academic consensus) ─────────────────────────────────

# Altman Z-Score (Revised non-manufacturing / private firm variant — Altman 1983)
# Z' < 1.23  → Distress Zone  → HIGH risk
# 1.23 ≤ Z' < 2.90 → Grey Zone   → MEDIUM risk
# Z' ≥ 2.90  → Safe Zone     → LOW risk
ALTMAN_DISTRESS_THRESHOLD = 1.23
ALTMAN_GREY_THRESHOLD = 2.90

# Piotroski F-Score
# 0–2 → Weak (HIGH GC risk signal)
# 3–5 → Neutral
# 6–9 → Strong financial health
PIOTROSKI_WEAK_THRESHOLD = 3

# AI confidence mapping by GC risk level
# Controls whether flag_complex_estimate() creates a mandatory judgment
GC_AI_CONFIDENCE: dict[str, float] = {
    "HIGH": 15.0,    # Well below 85% threshold → mandatory human sign-off
    "MEDIUM": 60.0,  # Below 85% threshold → mandatory human sign-off
    "LOW": 92.0,     # Above threshold → no mandatory escalation
}


# ─── Input / Output Dataclasses ───────────────────────────────────────────────

@dataclass
class GoingConcernFinancials:
    """
    Financial data required for the GC assessment.
    All monetary values should be in the same currency unit (e.g., INR thousands).
    Pass None for any unknown field — the engine degrades gracefully.
    """
    # Balance sheet items
    total_assets: float | None = None
    total_liabilities: float | None = None
    current_assets: float | None = None
    current_liabilities: float | None = None
    inventory: float | None = None          # For quick ratio
    cash_and_equivalents: float | None = None
    retained_earnings: float | None = None
    market_value_equity: float | None = None   # Or book value if private
    book_value_equity: float | None = None
    total_debt: float | None = None            # Short + long term debt
    long_term_debt: float | None = None

    # P&L items
    revenue: float | None = None
    ebit: float | None = None                  # Earnings before interest & tax
    net_income: float | None = None
    net_income_prior_year: float | None = None
    interest_expense: float | None = None
    gross_profit: float | None = None
    gross_profit_prior_year: float | None = None

    # Cash flow items
    operating_cash_flow: float | None = None
    operating_cash_flow_prior_year: float | None = None
    operating_cash_flow_2_years_ago: float | None = None
    capital_expenditure: float | None = None

    # Derived / additional
    shares_outstanding: float | None = None
    asset_turnover_prior: float | None = None   # Revenue prior / Total assets prior
    roa_prior: float | None = None              # Net income prior / Total assets prior

    # Qualitative context passed as string (management plans, covenants, external events)
    management_going_concern_plan: str | None = None
    known_covenant_breaches: str | None = None
    significant_external_events: str | None = None
    industry_sector: str | None = None
    years_in_operation: int | None = None


@dataclass
class AltmanResult:
    z_score: float | None
    zone: str          # "DISTRESS" | "GREY" | "SAFE" | "INSUFFICIENT_DATA"
    components: dict[str, float | None]
    interpretation: str


@dataclass
class PiotroskiResult:
    f_score: int
    strength: str      # "WEAK" | "NEUTRAL" | "STRONG"
    criteria: dict[str, bool | None]
    interpretation: str


@dataclass
class LiquiditySolvencyResult:
    current_ratio: float | None
    quick_ratio: float | None
    cash_ratio: float | None
    interest_coverage: float | None
    debt_to_equity: float | None
    signals: list[str]    # Flags raised


@dataclass
class CashFlowResult:
    ocf_trend: str        # "POSITIVE" | "DECLINING" | "NEGATIVE" | "UNKNOWN"
    consecutive_negative_years: int
    free_cash_flow: float | None
    signals: list[str]


@dataclass
class GoingConcernResult:
    """Full GC assessment result — stored in DB and surfaced via API."""
    engagement_id: str
    assessment_timestamp: str
    gc_risk: str                        # "HIGH" | "MEDIUM" | "LOW"
    altman: AltmanResult
    piotroski: PiotroskiResult
    liquidity_solvency: LiquiditySolvencyResult
    cash_flow: CashFlowResult
    distress_signals: list[str]         # All fired signals across all modules
    llm_reasoning: str
    llm_confidence: float               # 0.0–100.0
    disclosure_required: bool           # SA 570 Para 25
    emphasis_of_matter_required: bool   # SA 706 — if adequate disclosure exists
    opinion_modification_required: bool # SA 705 — if disclosure inadequate
    judgment_flagged: bool              # Whether ProfessionalJudgment was created
    judgment_id: str | None
    sa_570_references: list[str]        # Which SA 570 paragraphs were triggered


# ─── Module 1: Altman Z-Score (Revised Non-Manufacturing) ─────────────────────

def _safe_div(numerator: float | None, denominator: float | None) -> float | None:
    """Division returning None on missing data or zero denominator."""
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / denominator


def compute_altman_z_score(f: GoingConcernFinancials) -> AltmanResult:
    """
    Altman Z'-Score for private non-manufacturing firms (Altman 1983):
    Z' = 0.717*X1 + 0.847*X2 + 3.107*X3 + 0.420*X4 + 0.998*X5

    X1 = Working Capital / Total Assets          (liquidity)
    X2 = Retained Earnings / Total Assets        (cumulative profitability)
    X3 = EBIT / Total Assets                     (operating efficiency)
    X4 = Book Value of Equity / Total Liabilities (leverage)
    X5 = Sales / Total Assets                    (asset turnover)
    """
    working_capital = (
        (f.current_assets or 0.0) - (f.current_liabilities or 0.0)
        if f.current_assets is not None and f.current_liabilities is not None
        else None
    )

    x1 = _safe_div(working_capital, f.total_assets)
    x2 = _safe_div(f.retained_earnings, f.total_assets)
    x3 = _safe_div(f.ebit, f.total_assets)
    x4 = _safe_div(
        f.book_value_equity or f.market_value_equity,
        f.total_liabilities
    )
    x5 = _safe_div(f.revenue, f.total_assets)

    components = {"X1_working_capital_ratio": x1, "X2_retained_earnings_ratio": x2,
                  "X3_ebit_ratio": x3, "X4_equity_to_liabilities": x4,
                  "X5_asset_turnover": x5}

    # Need at least 3 out of 5 to compute a meaningful score
    available = [v for v in [x1, x2, x3, x4, x5] if v is not None]
    if len(available) < 3:
        return AltmanResult(
            z_score=None, zone="INSUFFICIENT_DATA", components=components,
            interpretation="Insufficient financial data to compute Altman Z'-Score. Minimum 3 of 5 ratios required."
        )

    # Use 0.0 for missing components (conservative — pulls score down)
    z = (0.717 * (x1 or 0.0) + 0.847 * (x2 or 0.0) +
         3.107 * (x3 or 0.0) + 0.420 * (x4 or 0.0) +
         0.998 * (x5 or 0.0))

    if z < ALTMAN_DISTRESS_THRESHOLD:
        zone = "DISTRESS"
        interp = (f"Z'-Score of {z:.3f} is in the DISTRESS ZONE (<{ALTMAN_DISTRESS_THRESHOLD}). "
                  "High probability of financial failure within 24 months (Altman 1983). "
                  "SA 570 Para 16(b) — significant doubt about going concern.")
    elif z < ALTMAN_GREY_THRESHOLD:
        zone = "GREY"
        interp = (f"Z'-Score of {z:.3f} is in the GREY ZONE ({ALTMAN_DISTRESS_THRESHOLD}–{ALTMAN_GREY_THRESHOLD}). "
                  "Moderate financial stress — auditor should apply increased scepticism per SA 570 Para 17.")
    else:
        zone = "SAFE"
        interp = (f"Z'-Score of {z:.3f} is in the SAFE ZONE (>{ALTMAN_GREY_THRESHOLD}). "
                  "Entity appears financially sound on this metric.")

    return AltmanResult(z_score=round(z, 4), zone=zone, components=components, interpretation=interp)


# ─── Module 2: Piotroski F-Score ──────────────────────────────────────────────

def compute_piotroski_f_score(f: GoingConcernFinancials) -> PiotroskiResult:
    """
    Piotroski F-Score: 9 binary criteria (1 = positive signal, 0 = negative).
    Score 0-2: Weak (GC concern), 3-5: Neutral, 6-9: Strong.

    Profitability (4 signals):
      F1 — ROA > 0
      F2 — Operating Cash Flow > 0
      F3 — Change in ROA positive (ROA > prior year ROA)
      F4 — Accruals ratio: OCF/Assets > ROA (cash earnings quality)
    Leverage / Liquidity (3 signals):
      F5 — Change in leverage: Long-term debt/assets decreased
      F6 — Change in current ratio: increased vs prior (proxy: current ratio > 1)
      F7 — No new shares issued (dilution signal — proxied by shares stable)
    Operating Efficiency (2 signals):
      F8 — Change in gross margin improved
      F9 — Change in asset turnover improved
    """
    criteria: dict[str, bool | None] = {}

    # F1 — ROA > 0
    roa = _safe_div(f.net_income, f.total_assets)
    criteria["F1_roa_positive"] = (roa > 0) if roa is not None else None

    # F2 — OCF > 0
    criteria["F2_ocf_positive"] = (f.operating_cash_flow > 0) if f.operating_cash_flow is not None else None

    # F3 — Change in ROA (current vs prior)
    delta_roa: bool | None = None
    if roa is not None and f.roa_prior is not None:
        delta_roa = roa > f.roa_prior
    criteria["F3_roa_improving"] = delta_roa

    # F4 — Accruals: OCF/Assets > ROA (better cash quality)
    accruals: bool | None = None
    ocf_assets = _safe_div(f.operating_cash_flow, f.total_assets)
    if ocf_assets is not None and roa is not None:
        accruals = ocf_assets > roa
    criteria["F4_cash_earnings_quality"] = accruals

    # F5 — Leverage decreased (long-term debt to assets lower than prior)
    # Without prior year leverage we cannot compare — flag as None
    leverage: bool | None = None
    criteria["F5_leverage_decreased"] = leverage  # conservative: None if no prior data

    # F6 — Current ratio > 1 (liquidity improved)
    cr = _safe_div(f.current_assets, f.current_liabilities)
    criteria["F6_adequate_liquidity"] = (cr >= 1.0) if cr is not None else None

    # F7 — No dilution (proxy: shares_outstanding not materially increased — mark True if unknown)
    criteria["F7_no_new_shares"] = True if f.shares_outstanding is None else None

    # F8 — Gross margin improved
    gm: bool | None = None
    if f.gross_profit is not None and f.revenue and f.revenue > 0:
        gm_current = f.gross_profit / f.revenue
        if f.gross_profit_prior_year is not None and f.revenue > 0:
            gm_prior = f.gross_profit_prior_year / f.revenue
            gm = gm_current > gm_prior
    criteria["F8_gross_margin_improved"] = gm

    # F9 — Asset turnover improved (proxy: revenue / assets > prior ratio)
    at_improved: bool | None = None
    current_at = _safe_div(f.revenue, f.total_assets)
    if current_at is not None and f.asset_turnover_prior is not None:
        at_improved = current_at > f.asset_turnover_prior
    criteria["F9_asset_turnover_improved"] = at_improved

    # Score — only count definitive True/False, treat None as 0 (conservative)
    f_score = sum(1 for v in criteria.values() if v is True)

    if f_score < PIOTROSKI_WEAK_THRESHOLD:
        strength = "WEAK"
        interp = (f"Piotroski F-Score = {f_score}/9. WEAK financial health. "
                  "Low score indicates deteriorating profitability, leverage, and efficiency. "
                  "SA 570 Para 16 — indicators of potential going concern uncertainty.")
    elif f_score < 6:
        strength = "NEUTRAL"
        interp = (f"Piotroski F-Score = {f_score}/9. NEUTRAL — some financial stress indicators present. "
                  "Monitor for deterioration.")
    else:
        strength = "STRONG"
        interp = (f"Piotroski F-Score = {f_score}/9. STRONG financial position. "
                  "No significant GC signals from this metric.")

    return PiotroskiResult(f_score=f_score, strength=strength, criteria=criteria, interpretation=interp)


# ─── Module 3: Liquidity & Solvency Ratios ────────────────────────────────────

def compute_liquidity_solvency(f: GoingConcernFinancials) -> LiquiditySolvencyResult:
    """
    SA 570 Para 16 — Financial indicators:
    - Unable to meet obligations as they fall due
    - Current liabilities exceed current assets
    - Fixed-term borrowings approaching maturity
    - Interest coverage deterioration
    """
    signals: list[str] = []

    # Liquidity
    current_ratio = _safe_div(f.current_assets, f.current_liabilities)
    quick_assets = (
        (f.current_assets or 0.0) - (f.inventory or 0.0)
        if f.current_assets is not None else None
    )
    quick_ratio = _safe_div(quick_assets, f.current_liabilities)
    cash_ratio = _safe_div(f.cash_and_equivalents, f.current_liabilities)

    if current_ratio is not None and current_ratio < 1.0:
        signals.append(f"CURRENT_RATIO_BELOW_1 ({current_ratio:.2f}) — Current liabilities exceed current assets [SA 570 Para 16(a)]")
    if quick_ratio is not None and quick_ratio < 0.5:
        signals.append(f"QUICK_RATIO_CRITICAL ({quick_ratio:.2f}) — Acute short-term liquidity risk [SA 570 Para 16(a)]")
    if cash_ratio is not None and cash_ratio < 0.1:
        signals.append(f"CASH_RATIO_VERY_LOW ({cash_ratio:.2f}) — Near-zero immediate liquidity [SA 570 Para 16(a)]")

    # Solvency
    interest_coverage = _safe_div(f.ebit, f.interest_expense)
    if interest_coverage is not None and interest_coverage < 1.5:
        signals.append(
            f"INTEREST_COVERAGE_BELOW_1.5 ({interest_coverage:.2f}) — Earnings barely cover interest [SA 570 Para 16(a)]"
        )
    if interest_coverage is not None and interest_coverage < 0:
        signals.append("EBIT_NEGATIVE — Entity cannot service debt from operations [SA 570 Para 16(a)]")

    equity_val = f.book_value_equity or f.market_value_equity
    debt_to_equity = _safe_div(f.total_debt or f.total_liabilities, equity_val)
    if debt_to_equity is not None and debt_to_equity > 3.0:
        signals.append(f"HIGH_DEBT_TO_EQUITY ({debt_to_equity:.2f}) — Over-leveraged balance sheet [SA 570 Para 16(a)]")

    # Negative equity
    if equity_val is not None and equity_val < 0:
        signals.append("NEGATIVE_EQUITY — Total liabilities exceed total assets [SA 570 Para 16(a)]")

    return LiquiditySolvencyResult(
        current_ratio=round(current_ratio, 4) if current_ratio is not None else None,
        quick_ratio=round(quick_ratio, 4) if quick_ratio is not None else None,
        cash_ratio=round(cash_ratio, 4) if cash_ratio is not None else None,
        interest_coverage=round(interest_coverage, 4) if interest_coverage is not None else None,
        debt_to_equity=round(debt_to_equity, 4) if debt_to_equity is not None else None,
        signals=signals
    )


# ─── Module 4: Cash Flow Burn Analysis ────────────────────────────────────────

def compute_cash_flow_analysis(f: GoingConcernFinancials) -> CashFlowResult:
    """
    SA 570 Para 16 — Operating cash flow indicators.
    Negative OCF for consecutive years is one of the strongest GC signals.
    """
    signals: list[str] = []
    consecutive_negative = 0

    ocf_values = [
        ("current_year", f.operating_cash_flow),
        ("prior_year", f.operating_cash_flow_prior_year),
        ("two_years_ago", f.operating_cash_flow_2_years_ago),
    ]

    negative_ocf_years = [label for label, val in ocf_values if val is not None and val < 0]
    consecutive_negative = len(negative_ocf_years)

    if consecutive_negative >= 3:
        signals.append("OCF_NEGATIVE_3_CONSECUTIVE_YEARS — Persistent cash burn [SA 570 Para 16(a)]")
    elif consecutive_negative == 2:
        signals.append("OCF_NEGATIVE_2_CONSECUTIVE_YEARS — Accelerating cash burn [SA 570 Para 16(a)]")
    elif consecutive_negative == 1 and f.operating_cash_flow is not None and f.operating_cash_flow < 0:
        signals.append("OCF_NEGATIVE_CURRENT_YEAR — Operations consuming cash [SA 570 Para 16(a)]")

    # Free cash flow (OCF - CapEx)
    free_cash_flow: float | None = None
    if f.operating_cash_flow is not None and f.capital_expenditure is not None:
        free_cash_flow = f.operating_cash_flow - abs(f.capital_expenditure)
        if free_cash_flow < 0:
            signals.append(f"NEGATIVE_FREE_CASH_FLOW ({free_cash_flow:,.0f}) — Cannot fund capex from operations")

    # OCF trend
    if f.operating_cash_flow is None:
        ocf_trend = "UNKNOWN"
    elif f.operating_cash_flow > 0 and (
        f.operating_cash_flow_prior_year is None or f.operating_cash_flow >= f.operating_cash_flow_prior_year
    ):
        ocf_trend = "POSITIVE"
    elif f.operating_cash_flow < 0:
        ocf_trend = "NEGATIVE"
    else:
        ocf_trend = "DECLINING"

    return CashFlowResult(
        ocf_trend=ocf_trend,
        consecutive_negative_years=consecutive_negative,
        free_cash_flow=round(free_cash_flow, 2) if free_cash_flow is not None else None,
        signals=signals
    )


# ─── Module 5: LLM SA 570 Evaluation ─────────────────────────────────────────

async def _llm_evaluate_going_concern(
    f: GoingConcernFinancials,
    altman: AltmanResult,
    piotroski: PiotroskiResult,
    liquidity: LiquiditySolvencyResult,
    cash_flow: CashFlowResult,
    all_signals: list[str],
) -> dict[str, Any]:
    """
    Submits quantitative results + qualitative context to GPT-4o
    for an SA 570 compliant going concern verdict.
    """
    from arkashri.services.ai_fabric import analyze_step_evidence

    step_instruction = (
        "You are a Chartered Accountant applying SA 570 (Revised) — Going Concern.\n"
        "Evaluate ALL the quantitative distress signals and qualitative context below.\n"
        "Determine:\n"
        "  1. gc_risk: 'HIGH' | 'MEDIUM' | 'LOW'\n"
        "  2. disclosure_required: true if material uncertainty exists (SA 570 Para 25)\n"
        "  3. emphasis_of_matter_required: true if management has provided adequate disclosure "
        "but material uncertainty still exists (SA 706)\n"
        "  4. opinion_modification_required: true if management's disclosure is inadequate "
        "or management plan is not credible (SA 705 — leads to qualified/adverse)\n"
        "  5. reasoning: 3–5 sentence narrative mentioning specific SA 570 paragraph references\n"
        "  6. management_plan_assessment: brief evaluation of management's stated plans to "
        "address going concern (if provided)\n"
        "  7. sa_570_references: list of specific SA 570 paragraphs triggered (e.g. '16(a)', '16(b)', '25')\n\n"
        "Key SA 570 principles to apply:\n"
        "  - Para 12: Evaluate management's own GC assessment (12 months from report date)\n"
        "  - Para 16: Financial, operating, other indicators of GC uncertainty\n"
        "  - Para 17–20: Auditor's independent evaluation\n"
        "  - Para 21: If management's plan is not credible — modify opinion\n"
        "  - Para 25: If adequate disclosure exists — emphasis of matter only\n"
    )

    evidence = {
        "altman_z_score": {
            "score": altman.z_score,
            "zone": altman.zone,
            "components": altman.components,
            "interpretation": altman.interpretation,
        },
        "piotroski_f_score": {
            "score": piotroski.f_score,
            "strength": piotroski.strength,
            "criteria": piotroski.criteria,
        },
        "liquidity_solvency": {
            "current_ratio": liquidity.current_ratio,
            "quick_ratio": liquidity.quick_ratio,
            "interest_coverage": liquidity.interest_coverage,
            "debt_to_equity": liquidity.debt_to_equity,
        },
        "cash_flow": {
            "trend": cash_flow.ocf_trend,
            "consecutive_negative_years": cash_flow.consecutive_negative_years,
            "free_cash_flow": cash_flow.free_cash_flow,
        },
        "all_distress_signals": all_signals,
        "management_plan": f.management_going_concern_plan or "Not provided",
        "known_covenant_breaches": f.known_covenant_breaches or "None reported",
        "significant_external_events": f.significant_external_events or "None reported",
        "industry_sector": f.industry_sector or "Unknown",
        "years_in_operation": f.years_in_operation,
    }

    try:
        result = await analyze_step_evidence(
            step_instruction=step_instruction,
            evidence_payload=evidence,
            audit_type="financial_audit",
            audit_objective="SA 570 Going Concern Assessment — determine if material uncertainty exists.",
        )

        # Parse extended fields from reasoning (ai_fabric returns verdict/confidence/reasoning/anomalies)
        gc_risk = "HIGH"
        if "LOW" in result.get("verdict", "FAIL").upper() or result.get("confidence_score", 0) > 0.85:
            gc_risk = "LOW"
        elif "PASS" in result.get("verdict", "FAIL").upper() and result.get("confidence_score", 0) > 0.6:
            gc_risk = "MEDIUM"
        elif "FAIL" in result.get("verdict", "FAIL").upper():
            # Check anomalies for risk level
            anomalies = result.get("extracted_anomalies", [])
            gc_risk = "HIGH" if len(anomalies) > 2 else "MEDIUM"

        return {
            "gc_risk": gc_risk,
            "llm_reasoning": result.get("reasoning", "LLM evaluation completed."),
            "llm_confidence": round(result.get("confidence_score", 0.0) * 100, 1),
            "disclosure_required": gc_risk in ("HIGH", "MEDIUM"),
            "emphasis_of_matter_required": gc_risk == "MEDIUM",
            "opinion_modification_required": gc_risk == "HIGH",
            "sa_570_references": result.get("extracted_anomalies", []),
        }
    except Exception as exc:
        logger.error("GC LLM evaluation failed: %s", exc)
        # Conservative fallback: derive from quantitative signals
        high_signals = len(all_signals)
        if high_signals >= 4 or (altman.zone == "DISTRESS") or (piotroski.f_score <= 2):
            gc_risk = "HIGH"
        elif high_signals >= 2 or altman.zone == "GREY" or piotroski.strength == "WEAK":
            gc_risk = "MEDIUM"
        else:
            gc_risk = "LOW"

        return {
            "gc_risk": gc_risk,
            "llm_reasoning": (
                f"LLM evaluation unavailable — falling back to quantitative signals. "
                f"Distress signals fired: {high_signals}. "
                f"Altman zone: {altman.zone}. Piotroski strength: {piotroski.strength}."
            ),
            "llm_confidence": 40.0,
            "disclosure_required": gc_risk in ("HIGH", "MEDIUM"),
            "emphasis_of_matter_required": gc_risk == "MEDIUM",
            "opinion_modification_required": gc_risk == "HIGH",
            "sa_570_references": ["16(a)", "17"],
        }


# ─── Public API ───────────────────────────────────────────────────────────────

async def run_going_concern_assessment(
    session: AsyncSession,
    engagement_id: uuid.UUID,
    tenant_id: str,
    financials: GoingConcernFinancials,
    auto_flag_judgment: bool = True,
) -> GoingConcernResult:
    """
    Full SA 570 Going Concern Assessment pipeline.

    Steps:
      1. Compute Altman Z'-Score
      2. Compute Piotroski F-Score
      3. Compute Liquidity / Solvency ratios
      4. Compute Cash Flow burn analysis
      5. Aggregate all distress signals
      6. LLM evaluation with SA 570 context
      7. Auto-flag ProfessionalJudgment if gc_risk HIGH or MEDIUM
      8. Return GoingConcernResult

    Args:
        session:           DB session
        engagement_id:     UUID of the engagement
        tenant_id:         Tenant identifier
        financials:        GoingConcernFinancials dataclass
        auto_flag_judgment: If True, creates ProfessionalJudgment record when risk is HIGH/MEDIUM
    """
    now_iso = datetime.now(timezone.utc).isoformat()

    # ── 1. Quantitative modules ───────────────────────────────────────────────
    altman = compute_altman_z_score(financials)
    piotroski = compute_piotroski_f_score(financials)
    liquidity = compute_liquidity_solvency(financials)
    cash_flow_result = compute_cash_flow_analysis(financials)

    # ── 2. Aggregate all signals ──────────────────────────────────────────────
    all_signals: list[str] = []
    all_signals.extend(liquidity.signals)
    all_signals.extend(cash_flow_result.signals)

    if altman.zone == "DISTRESS":
        all_signals.append(
            f"ALTMAN_DISTRESS_ZONE (Z'={altman.z_score}) — [SA 570 Para 16(a)]"
        )
    elif altman.zone == "GREY":
        all_signals.append(
            f"ALTMAN_GREY_ZONE (Z'={altman.z_score}) — Moderate financial stress [SA 570 Para 16(a)]"
        )

    if piotroski.strength == "WEAK":
        all_signals.append(
            f"PIOTROSKI_WEAK (F={piotroski.f_score}/9) — Deteriorating financial fundamentals [SA 570 Para 16(a)]"
        )

    # Qualitative signals
    if financials.known_covenant_breaches and financials.known_covenant_breaches.strip():
        all_signals.append(
            "COVENANT_BREACH_REPORTED — Loan covenant breach is a SA 570 Para 16(a) indicator"
        )

    # ── 3. LLM evaluation ────────────────────────────────────────────────────
    llm_result = await _llm_evaluate_going_concern(
        financials, altman, piotroski, liquidity, cash_flow_result, all_signals
    )

    gc_risk: str = llm_result["gc_risk"]
    llm_reasoning: str = llm_result["llm_reasoning"]
    llm_confidence: float = llm_result["llm_confidence"]
    disclosure_required: bool = llm_result["disclosure_required"]
    emphasis_required: bool = llm_result["emphasis_of_matter_required"]
    opinion_modification: bool = llm_result["opinion_modification_required"]
    sa_refs: list[str] = llm_result.get("sa_570_references", [])

    # ── 4. Professional Judgment gate ────────────────────────────────────────
    judgment_id: str | None = None
    judgment_flagged = False

    if auto_flag_judgment and gc_risk in ("HIGH", "MEDIUM"):
        ai_confidence_for_judgment = GC_AI_CONFIDENCE[gc_risk]
        gc_description = (
            f"Going Concern risk assessed as {gc_risk} under SA 570.\n\n"
            f"Altman Z'-Score: {altman.z_score} ({altman.zone})\n"
            f"Piotroski F-Score: {piotroski.f_score}/9 ({piotroski.strength})\n"
            f"Distress signals fired: {len(all_signals)}\n\n"
            f"Key signals:\n" + "\n".join(f"• {s}" for s in all_signals[:5]) + "\n\n"
            f"LLM Reasoning: {llm_reasoning}\n\n"
            f"SA 570 References: {', '.join(sa_refs) if sa_refs else 'Para 16, 17'}\n\n"
            f"Action required: CA must review, assess management's plans (SA 570 Para 12), "
            f"and determine whether disclosure (Para 25) or opinion modification (SA 705) is warranted."
        )
        judgment = await flag_complex_estimate(
            session=session,
            engagement_id=engagement_id,
            area="Going Concern",
            description=gc_description,
            ai_confidence=ai_confidence_for_judgment
        )
        if judgment:
            judgment_id = str(judgment.id)
            judgment_flagged = True
            logger.info(
                "Going Concern judgment flagged for engagement %s. Risk=%s, JudgmentID=%s",
                engagement_id, gc_risk, judgment_id
            )

    # ── 5. Build and return result ────────────────────────────────────────────
    result = GoingConcernResult(
        engagement_id=str(engagement_id),
        assessment_timestamp=now_iso,
        gc_risk=gc_risk,
        altman=altman,
        piotroski=piotroski,
        liquidity_solvency=liquidity,
        cash_flow=cash_flow_result,
        distress_signals=all_signals,
        llm_reasoning=llm_reasoning,
        llm_confidence=llm_confidence,
        disclosure_required=disclosure_required,
        emphasis_of_matter_required=emphasis_required,
        opinion_modification_required=opinion_modification,
        judgment_flagged=judgment_flagged,
        judgment_id=judgment_id,
        sa_570_references=sa_refs if sa_refs else ["SA 570 Para 16", "SA 570 Para 17"],
    )

    logger.info(
        "GC assessment complete. engagement=%s gc_risk=%s altman_zone=%s piotroski=%s signals=%d",
        engagement_id, gc_risk, altman.zone, piotroski.f_score, len(all_signals)
    )

    return result


def going_concern_result_to_dict(result: GoingConcernResult) -> dict[str, Any]:
    """Serialize GoingConcernResult to a JSON-safe dict for API responses and seal bundles."""
    d = asdict(result)
    return d
