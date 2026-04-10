# pyre-ignore-all-errors
"""
services/gc_advanced.py — Advanced GC Capabilities (Next-Level)
================================================================
Adds 5 missing capabilities to the Going Concern engine:

  1. GC Risk Score (0–100) with explainability
       - Composite weighted score across all modules
       - Per-component contribution breakdown
       - Confidence band (pessimistic / base / optimistic)

  2. Predictive Bankruptcy Model (academic ML)
       - Ohlson O-Score (logistic regression, Ohlson 1980)
       - Shumway Hazard Model (discrete-time, Shumway 2001)
       - Combined P(bankrupt within 1 year) and P(bankrupt within 2 years)

  3. 12-Month Cash Flow Simulation
       - Linear burn-rate extrapolation + trend adjustment
       - Monthly cash balance projection
       - Months until cash exhaustion (runway)

  4. Scenario Analysis (Best / Base / Worst)
       - Parameterised revenue shock + cost flexibility
       - Produces OCF and GC score per scenario

  5. Industry Benchmarking
       - 12-sector median database (Damodaran / NSE sector data)
       - Percentile rank vs industry peers
       - Gap-to-peer analysis

All functions are pure / synchronous — no DB access — so they can be
called inside the async assessment pipeline without blocking.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from arkashri.services.going_concern import (
    GoingConcernFinancials,
    AltmanResult,
    PiotroskiResult,
    LiquiditySolvencyResult,
    CashFlowResult,
    _safe_div,
)


# ═══════════════════════════════════════════════════════════════════════════════
# MODULE 1 — GC Risk Score (0–100 with Explainability)
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class ScoreComponent:
    name: str
    raw_value: float | None          # The underlying metric value
    contribution: float              # Points contributed to composite (0–max_points)
    max_points: float                # Max this component can contribute
    weight_pct: float                # Weight as % of total score
    interpretation: str             # Human-readable explanation


@dataclass
class GCRiskScore:
    """
    Composite Going Concern Risk Score (0–100).
    Higher = MORE distressed / higher risk.
    """
    composite_score: float           # 0–100
    risk_band: str                   # "CRITICAL" | "HIGH" | "ELEVATED" | "MODERATE" | "LOW"
    components: list[ScoreComponent]
    pessimistic_score: float         # +10 sensitivity (more conservative)
    optimistic_score: float          # -10 sensitivity (more optimistic)
    confidence_band: str             # "NARROW" | "MODERATE" | "WIDE" (data completeness)
    key_driver: str                  # Single biggest contributor to the score
    score_interpretation: str        # Audit-language description
    audit_action: str                # Recommended next action

    # Explainability waterfall (component name → contribution)
    waterfall: dict[str, float]


# Weights (must sum to 100)
_COMPONENT_WEIGHTS = {
    "altman_z_score":    25,   # Most widely cited academic model
    "piotroski_f_score": 20,   # Multi-dimensional financial health
    "liquidity_solvency": 20,  # Direct SA 570 Para 16(a) indicators
    "cash_flow_burn":    20,   # Strongest operational GC signal
    "qualitative":       15,   # Covenants, management plan, external events
}


def _altman_to_score(altman: AltmanResult) -> tuple[float, str]:
    """Convert Altman zone/score to component contribution (0–25, higher = more distressed)."""
    if altman.z_score is None:
        return 12.5, "Insufficient data — mid-point assigned (conservative)"
    z = altman.z_score
    # Linear mapping: Z' ≤ 0 → 25 points, Z' ≥ 3.5 → 0 points
    raw = max(0.0, min(25.0, (3.5 - z) / 3.5 * 25.0))
    interp = f"Altman Z' = {z:.3f} ({altman.zone}) → {raw:.1f}/25 distress contribution"
    return round(raw, 2), interp


def _piotroski_to_score(piotroski: PiotroskiResult) -> tuple[float, str]:
    """Convert Piotroski F-score to component contribution (0–20, higher = more distressed)."""
    # F=0 → 20 pts, F=9 → 0 pts
    raw = (9 - piotroski.f_score) / 9 * 20.0
    interp = f"Piotroski F = {piotroski.f_score}/9 ({piotroski.strength}) → {raw:.1f}/20 distress contribution"
    return round(raw, 2), interp


def _liquidity_to_score(liquidity: LiquiditySolvencyResult) -> tuple[float, str]:
    """Score liquidity/solvency sub-signals (0–20). Each fired signal contributes."""
    signal_count = len(liquidity.signals)
    # Max 5 signals — each worth 4 points
    raw = min(20.0, signal_count * 4.0)
    # Boost for critical signals
    if liquidity.current_ratio is not None and liquidity.current_ratio < 0.5:
        raw = min(20.0, raw + 3.0)  # Critically low current ratio
    if liquidity.interest_coverage is not None and liquidity.interest_coverage < 0:
        raw = min(20.0, raw + 2.0)  # Negative EBIT
    interp = f"{signal_count} liquidity/solvency signals fired → {raw:.1f}/20 distress contribution"
    return round(raw, 2), interp


def _cashflow_to_score(cash_flow: CashFlowResult) -> tuple[float, str]:
    """Score cash flow burn (0–20). Consecutive negative years are the heaviest weight."""
    base = cash_flow.consecutive_negative_years * 6.0   # 6 pts per negative year
    if cash_flow.ocf_trend == "NEGATIVE":
        base += 2.0
    elif cash_flow.ocf_trend == "DECLINING":
        base += 1.0
    if cash_flow.free_cash_flow is not None and cash_flow.free_cash_flow < 0:
        base += 1.0
    raw = min(20.0, base)
    interp = f"{cash_flow.consecutive_negative_years} consecutive negative OCF years, trend={cash_flow.ocf_trend} → {raw:.1f}/20"
    return round(raw, 2), interp


def _qualitative_to_score(f: GoingConcernFinancials) -> tuple[float, str]:
    """Score qualitative signals (0–15)."""
    pts = 0.0
    reasons = []
    if f.known_covenant_breaches and f.known_covenant_breaches.strip():
        pts += 6.0
        reasons.append("covenant breach (+6)")
    if f.significant_external_events and f.significant_external_events.strip():
        pts += 4.0
        reasons.append("external events (+4)")
    if not f.management_going_concern_plan or not f.management_going_concern_plan.strip():
        pts += 5.0
        reasons.append("no management GC plan (+5)")
    elif len(f.management_going_concern_plan) < 50:
        pts += 2.0
        reasons.append("management plan appears thin (+2)")
    raw = min(15.0, pts)
    interp = f"Qualitative: {', '.join(reasons) if reasons else 'no qualitative risk'} → {raw:.1f}/15"
    return round(raw, 2), interp


def compute_gc_risk_score(
    f: GoingConcernFinancials,
    altman: AltmanResult,
    piotroski: PiotroskiResult,
    liquidity: LiquiditySolvencyResult,
    cash_flow: CashFlowResult,
) -> GCRiskScore:
    """
    Compute composite GC Risk Score (0–100) with full component explainability.

    Score bands:
      0–20   → LOW        (clean — SA 570: no GC indicators)
      21–40  → MODERATE   (monitor — SA 570 Para 17 attention)
      41–60  → ELEVATED   (concern — SA 570 Para 16 indicators present)
      61–80  → HIGH       (serious — SA 570 Para 21 / 25 likely triggered)
      81–100 → CRITICAL   (extreme — qualified / adverse opinion, immediate action)
    """
    a_pts, a_interp = _altman_to_score(altman)
    p_pts, p_interp = _piotroski_to_score(piotroski)
    l_pts, l_interp = _liquidity_to_score(liquidity)
    c_pts, c_interp = _cashflow_to_score(cash_flow)
    q_pts, q_interp = _qualitative_to_score(f)

    composite = round(a_pts + p_pts + l_pts + c_pts + q_pts, 2)

    components = [
        ScoreComponent("Altman Z'-Score",       altman.z_score,      a_pts, 25.0, 25, a_interp),
        ScoreComponent("Piotroski F-Score",     float(piotroski.f_score), p_pts, 20.0, 20, p_interp),
        ScoreComponent("Liquidity & Solvency",  float(len(liquidity.signals)), l_pts, 20.0, 20, l_interp),
        ScoreComponent("Cash Flow Burn",        float(cash_flow.consecutive_negative_years), c_pts, 20.0, 20, c_interp),
        ScoreComponent("Qualitative Signals",   None,                q_pts, 15.0, 15, q_interp),
    ]

    # Waterfall
    waterfall = {
        "Altman Z'":   a_pts,
        "Piotroski F": p_pts,
        "Liquidity":   l_pts,
        "Cash Flow":   c_pts,
        "Qualitative": q_pts,
    }

    # Key driver
    pts_map = {
        "Altman Z'":   a_pts,
        "Piotroski F": p_pts,
        "Liquidity":   l_pts,
        "Cash Flow":   c_pts,
        "Qualitative": q_pts,
    }
    key_driver = max(pts_map, key=lambda k: pts_map[k])

    # Sensitivity bands (data completeness)
    data_fields = [f.total_assets, f.revenue, f.ebit, f.operating_cash_flow, f.net_income]
    available = sum(1 for v in data_fields if v is not None)
    if available >= 4:
        confidence_band = "NARROW"
        pessimistic = min(100.0, composite + 7.0)
        optimistic = max(0.0, composite - 7.0)
    elif available >= 2:
        confidence_band = "MODERATE"
        pessimistic = min(100.0, composite + 12.0)
        optimistic = max(0.0, composite - 12.0)
    else:
        confidence_band = "WIDE"
        pessimistic = min(100.0, composite + 18.0)
        optimistic = max(0.0, composite - 18.0)

    # Risk band
    if composite >= 81:
        risk_band = "CRITICAL"
        interp = f"CRITICAL risk ({composite:.1f}/100). Immediate going concern uncertainty. SA 705 opinion modification is required."
        action = "Issue qualified or adverse opinion. Mandatory CA sign-off. Report to TCWG immediately."
    elif composite >= 61:
        risk_band = "HIGH"
        interp = f"HIGH risk ({composite:.1f}/100). Material uncertainty about going concern. SA 570 Para 25 disclosure required."
        action = "Generate draft GC disclosure. Flag ProfessionalJudgment. Evaluate management plan credibility."
    elif composite >= 41:
        risk_band = "ELEVATED"
        interp = f"ELEVATED risk ({composite:.1f}/100). Going concern indicators present per SA 570 Para 16. Emphasis of Matter may be required."
        action = "Apply enhanced audit procedures (SA 570 Para 17–20). Obtain management's 12-month projection."
    elif composite >= 21:
        risk_band = "MODERATE"
        interp = f"MODERATE risk ({composite:.1f}/100). Some indicators — monitor closely. No immediate SA 570 disclosure warranted."
        action = "Document GC assessment in planning memo. No disclosure required at this stage."
    else:
        risk_band = "LOW"
        interp = f"LOW risk ({composite:.1f}/100). No material GC indicators. Standard procedures sufficient."
        action = "Document that GC has been assessed and no issues identified (SA 570 Para 12)."

    return GCRiskScore(
        composite_score=composite,
        risk_band=risk_band,
        components=components,
        pessimistic_score=round(pessimistic, 2),
        optimistic_score=round(optimistic, 2),
        confidence_band=confidence_band,
        key_driver=key_driver,
        score_interpretation=interp,
        audit_action=action,
        waterfall=waterfall,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# MODULE 2 — Predictive Bankruptcy Model
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class BankruptcyPrediction:
    # Ohlson O-Score
    o_score: float | None             # Raw logit score
    p_bankrupt_ohlson: float | None   # Probability 0.0–1.0
    ohlson_signals_available: int     # How many of 9 factors computed

    # Shumway Hazard Model
    shumway_hazard_rate: float | None # Annual conditional probability
    p_bankrupt_1yr: float | None      # P(bankrupt within 1 year) — combined
    p_bankrupt_2yr: float | None      # P(bankrupt within 2 years) — combined

    # Classification
    default_risk: str                 # "VERY_HIGH" | "HIGH" | "MEDIUM" | "LOW" | "VERY_LOW"
    interpretation: str
    factors_used: list[str]           # Which model components were computable


def _logistic(x: float) -> float:
    """Standard logistic function clamped to avoid overflow."""
    try:
        return 1.0 / (1.0 + math.exp(-x))
    except OverflowError:
        return 0.0 if x < 0 else 1.0


def compute_bankruptcy_prediction(f: GoingConcernFinancials) -> BankruptcyPrediction:
    """
    Ohlson O-Score (1980) + Shumway Hazard Model (2001).

    Ohlson O-Score (9 factors):
      O = -1.32 - 0.407*SIZE + 6.03*TLTA - 1.43*WCTA + 0.076*CLCA
          - 1.72*OENEG - 2.37*NITA - 1.83*FUTL + 0.285*INTWO - 0.521*CHIN

    Where:
      SIZE   = log(TA / GNP deflator) — proxied as log(total_assets / 1000) for INR
      TLTA   = Total Liabilities / Total Assets
      WCTA   = Working Capital / Total Assets
      CLCA   = Current Liabilities / Current Assets
      OENEG  = 1 if total liabilities > total assets else 0
      NITA   = Net Income / Total Assets
      FUTL   = OCF / Total Liabilities
      INTWO  = 1 if net income negative in last 2 years
      CHIN   = (NI_t - NI_t-1) / (|NI_t| + |NI_t-1|)  — change in net income

    Shumway (2001) — simplified:
      Uses NI/TA (profitability) + TL/TA (leverage) + working capital signal
    """
    ta = f.total_assets
    tl = f.total_liabilities
    factors_used: list[str] = []

    # ── Ohlson factors ───────────────────────────────────────────────────────
    # SIZE
    size_val: float = 0.0
    if ta and ta > 0:
        size_val = math.log(ta / 1000.0)  # INR thousands → millions scale
        factors_used.append("SIZE")

    # TLTA
    tlta = _safe_div(tl, ta) or 0.0
    if f.total_liabilities and f.total_assets:
        factors_used.append("TLTA")

    # WCTA
    wc = (
        (f.current_assets or 0.0) - (f.current_liabilities or 0.0)
        if f.current_assets is not None and f.current_liabilities is not None else None
    )
    wcta = _safe_div(wc, ta) or 0.0
    if wc is not None and ta:
        factors_used.append("WCTA")

    # CLCA
    clca = _safe_div(f.current_liabilities, f.current_assets) or 0.0
    if f.current_liabilities and f.current_assets:
        factors_used.append("CLCA")

    # OENEG — equity underwater
    oeneg = 0.0
    if tl is not None and ta is not None:
        oeneg = 1.0 if tl > ta else 0.0
        factors_used.append("OENEG")

    # NITA
    nita = _safe_div(f.net_income, ta) or 0.0
    if f.net_income is not None and ta:
        factors_used.append("NITA")

    # FUTL — OCF / Total Liabilities
    futl = _safe_div(f.operating_cash_flow, tl) or 0.0
    if f.operating_cash_flow is not None and tl:
        factors_used.append("FUTL")

    # INTWO — net income negative in at least 2 of last 3 years
    neg_ni_years = sum(1 for v in [f.net_income, f.net_income_prior_year] if v is not None and v < 0)
    intwo = 1.0 if neg_ni_years >= 2 else 0.0
    if f.net_income is not None and f.net_income_prior_year is not None:
        factors_used.append("INTWO")

    # CHIN — earnings momentum
    chin: float = 0.0
    ni_curr = f.net_income
    ni_prev = f.net_income_prior_year
    if ni_curr is not None and ni_prev is not None:
        denom = abs(ni_curr) + abs(ni_prev)
        if denom > 0:
            chin = (ni_curr - ni_prev) / denom
        factors_used.append("CHIN")

    # O-Score (Ohlson 1980 coefficients)
    o_score: float | None = None
    p_ohlson: float | None = None
    if len(factors_used) >= 4:
        o_score = (
            -1.32
            - 0.407 * size_val
            + 6.03  * tlta
            - 1.43  * wcta
            + 0.076 * clca
            - 1.72  * oeneg
            - 2.37  * nita
            - 1.83  * futl
            + 0.285 * intwo
            - 0.521 * chin
        )
        # P(bankrupt) — logistic transform of O-score
        p_ohlson = round(_logistic(o_score), 4)
        o_score = round(o_score, 4)

    # ── Shumway hazard model (simplified 3-factor) ────────────────────────────
    # h(t) = exp(-13.303 - 1.982*NI/TA + 3.593*TL/TA - 0.467*ln(SIZE)) / ...
    # Simplified annual hazard rate (from Shumway 2001 Table IV coefficients)
    shumway_hazard: float | None = None
    p_1yr: float | None = None
    p_2yr: float | None = None

    if f.net_income is not None and ta and ta > 0 and tl is not None:
        log_ta = math.log(max(ta, 1.0))
        logit = (
            -13.303
            + (-1.982) * (nita)
            + 3.593    * (tlta)
            + (-0.467) * log_ta
        )
        shumway_hazard = round(_logistic(logit), 4)
        # P(survive at least 1 year) = exp(-hazard_rate)
        # P(bankrupt by year 1) ≈ 1 - exp(-hazard)
        p_1yr = round(1.0 - math.exp(-shumway_hazard), 4)
        p_2yr = round(1.0 - math.exp(-shumway_hazard * 2.0), 4)

    # ── Combined P(1 year) ────────────────────────────────────────────────────
    combined_p1: float | None = None
    if p_ohlson is not None and p_1yr is not None:
        combined_p1 = round((p_ohlson + p_1yr) / 2.0, 4)
    elif p_ohlson is not None:
        combined_p1 = p_ohlson
    elif p_1yr is not None:
        combined_p1 = p_1yr

    # ── Classification ────────────────────────────────────────────────────────
    p_ref = combined_p1 or p_ohlson or 0.0
    if p_ref >= 0.70:
        risk = "VERY_HIGH"
        interp = f"P(bankrupt within 1yr) ≈ {p_ref:.0%}. Extreme distress — immediate action."
    elif p_ref >= 0.40:
        risk = "HIGH"
        interp = f"P(bankrupt within 1yr) ≈ {p_ref:.0%}. Serious distress — GC opinion modification likely."
    elif p_ref >= 0.20:
        risk = "MEDIUM"
        interp = f"P(bankrupt within 1yr) ≈ {p_ref:.0%}. Elevated risk — SA 570 disclosure warranted."
    elif p_ref >= 0.05:
        risk = "LOW"
        interp = f"P(bankrupt within 1yr) ≈ {p_ref:.0%}. Moderate — monitor closely."
    else:
        risk = "VERY_LOW"
        interp = f"P(bankrupt within 1yr) ≈ {p_ref:.0%}. Strong financial position."

    if not factors_used:
        interp = "Insufficient data for bankruptcy probability computation. Provide at least: total assets, liabilities, net income."

    return BankruptcyPrediction(
        o_score=o_score,
        p_bankrupt_ohlson=p_ohlson,
        ohlson_signals_available=len(factors_used),
        shumway_hazard_rate=shumway_hazard,
        p_bankrupt_1yr=combined_p1,
        p_bankrupt_2yr=p_2yr,
        default_risk=risk,
        interpretation=interp,
        factors_used=factors_used,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# MODULE 3 — 12-Month Cash Flow Simulation
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class MonthlyProjection:
    month: int
    projected_ocf: float
    cumulative_cash: float
    crisis_flag: bool               # True when cumulative cash < 0


@dataclass
class CashFlowSimulation:
    starting_cash: float | None
    monthly_burn_rate: float        # Negative = cash burning
    months_until_exhaustion: int | None   # None if cash never exhausted
    runway_label: str               # e.g. "< 3 months", "6–9 months", "Sustainable"
    monthly_projections: list[MonthlyProjection]
    minimum_projected_cash: float
    minimum_cash_month: int
    annual_projected_ocf: float
    requires_external_funding: bool
    interpretation: str


def simulate_12_month_cash_flow(
    f: GoingConcernFinancials,
    monthly_revenue_growth_rate: float = 0.0,  # e.g. 0.005 = 0.5% monthly growth
    monthly_cost_reduction_rate: float = 0.0,  # e.g. 0.003 = cost cut 0.3% monthly
) -> CashFlowSimulation:
    """
    Projects monthly cash position over 12 months.

    Algorithm:
      1. Derive monthly OCF from annual: base_monthly_ocf = annual_OCF / 12
      2. Apply OCF trend adjustment: if declining, extrapolate trend
      3. Account for capex outflow (monthly: annual_capex / 12)
      4. Compound growth/cost adjustments month by month
      5. Accumulate cash from starting_cash (cash_and_equivalents)
    """
    # Base monthly OCF
    annual_ocf = f.operating_cash_flow or 0.0
    monthly_capex = (abs(f.capital_expenditure or 0.0)) / 12.0
    base_monthly_ocf = annual_ocf / 12.0 - monthly_capex

    # Trend adjustment: if OCF was declining, extrapolate worsening
    trend_adj = 0.0
    if (f.operating_cash_flow is not None and
        f.operating_cash_flow_prior_year is not None and
        f.operating_cash_flow_prior_year != 0):
        yoy_change = (f.operating_cash_flow - f.operating_cash_flow_prior_year) / abs(f.operating_cash_flow_prior_year)
        # Apply 50% of YoY trend as monthly carryover (dampened)
        trend_adj = (yoy_change / 12.0) * 0.50

    starting_cash = f.cash_and_equivalents or 0.0
    cumulative_cash = starting_cash

    projections: list[MonthlyProjection] = []
    crisis_month: int | None = None
    min_cash = cumulative_cash
    min_month = 0

    for m in range(1, 13):
        # Monthly OCF with compounding growth + cost reduction + trend
        month_factor = (1.0 + monthly_revenue_growth_rate - monthly_cost_reduction_rate + trend_adj) ** m
        monthly_ocf = base_monthly_ocf * month_factor

        cumulative_cash += monthly_ocf
        is_crisis = cumulative_cash < 0

        if is_crisis and crisis_month is None:
            crisis_month = m

        if cumulative_cash < min_cash:
            min_cash = cumulative_cash
            min_month = m

        projections.append(MonthlyProjection(
            month=m,
            projected_ocf=round(monthly_ocf, 2),
            cumulative_cash=round(cumulative_cash, 2),
            crisis_flag=is_crisis,
        ))

    # Runway label
    if crisis_month is None:
        runway = "Sustainable (>12 months)"
        requires_funding = False
    elif crisis_month <= 3:
        runway = f"CRITICAL — cash exhausted in {crisis_month} month(s)"
        requires_funding = True
    elif crisis_month <= 6:
        runway = f"URGENT — cash exhausted in {crisis_month} months"
        requires_funding = True
    elif crisis_month <= 9:
        runway = f"WARNING — cash exhausted in {crisis_month} months"
        requires_funding = True
    else:
        runway = f"CAUTION — cash exhausted in {crisis_month} months"
        requires_funding = True

    annual_projected = sum(p.projected_ocf for p in projections)

    if requires_funding:
        interp = (
            f"At current burn rate, the entity's cash reserves will be exhausted in {crisis_month} month(s). "
            "External financing or operating turnaround is required within this window. "
            "SA 570 Para 16(b) — management's plan to address this must be evaluated critically."
        )
    else:
        interp = (
            "12-month cash flow projection does not indicate cash exhaustion under base assumptions. "
            f"Minimum projected cash: {min_cash:,.0f} (Month {min_month}). "
            "SA 570: entity appears able to continue as a going concern over the review period."
        )

    return CashFlowSimulation(
        starting_cash=starting_cash if f.cash_and_equivalents is not None else None,
        monthly_burn_rate=round(base_monthly_ocf, 2),
        months_until_exhaustion=crisis_month,
        runway_label=runway,
        monthly_projections=projections,
        minimum_projected_cash=round(min_cash, 2),
        minimum_cash_month=min_month,
        annual_projected_ocf=round(annual_projected, 2),
        requires_external_funding=requires_funding,
        interpretation=interp,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# MODULE 4 — Scenario Analysis (Best / Base / Worst)
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class Scenario:
    name: str                        # "BEST" | "BASE" | "WORST"
    revenue_shock_pct: float         # e.g. -0.30 = 30% revenue decline
    cost_flexibility_pct: float      # e.g. 0.15 = 15% cost reduction achievable
    adjusted_ocf: float | None
    adjusted_current_ratio: float | None
    cash_simulation: CashFlowSimulation
    gc_risk_estimate: str            # "HIGH" | "MEDIUM" | "LOW" (fast heuristic)
    narrative: str


@dataclass
class ScenarioAnalysis:
    best: Scenario
    base: Scenario
    worst: Scenario
    stress_resilience: str          # "RESILIENT" | "FRAGILE" | "STRESSED" | "NON-VIABLE"
    break_even_revenue_shock: float | None   # % decline that tips entity into GC concern
    summary: str


def _adjust_financials_for_scenario(
    f: GoingConcernFinancials,
    revenue_shock: float,
    cost_flexibility: float,
) -> GoingConcernFinancials:
    """Return a modified copy of financials applying shock assumptions."""
    from copy import copy
    adj = copy(f)
    if adj.revenue is not None:
        adj.revenue = adj.revenue * (1 + revenue_shock)
    if adj.gross_profit is not None:
        # Revenue decline hits gross profit, but cost flexibility partially offsets
        adj.gross_profit = adj.gross_profit * (1 + revenue_shock) * (1 + cost_flexibility * 0.5)
    if adj.ebit is not None:
        adj.ebit = adj.ebit * (1 + revenue_shock) + (adj.total_assets or 0) * cost_flexibility * 0.02
    if adj.net_income is not None:
        adj.net_income = adj.net_income * (1 + revenue_shock) + (adj.total_assets or 0) * cost_flexibility * 0.015
    if adj.operating_cash_flow is not None:
        adj.operating_cash_flow = adj.operating_cash_flow * (1 + revenue_shock) + (adj.total_assets or 0) * cost_flexibility * 0.01
    return adj


def _quick_gc_risk(ocf: float | None, cr: float | None, total_signals: int) -> str:
    if ocf is not None and ocf < 0 and (cr is None or cr < 0.8):
        return "HIGH"
    if total_signals >= 4 or (ocf is not None and ocf < 0):
        return "MEDIUM"
    return "LOW"


def run_scenario_analysis(f: GoingConcernFinancials) -> ScenarioAnalysis:
    """
    Three-scenario stress test:
      BEST:  Revenue +10%, cost reduction 10% achievable
      BASE:  Current trajectory (0% shock)
      WORST: Revenue -30%, credit lines withdrawn, cost fixed
    """
    scenarios_config = [
        ("BEST",  +0.10, 0.10,
         "Revenue grows 10%, management achieves 10% cost reduction, external credit available."),
        ("BASE",  0.00,  0.00,
         "Current financial trajectory continues, no turnaround or deterioration."),
        ("WORST", -0.30, 0.00,
         "Revenue falls 30% (major customer loss / market contraction), credit lines withdrawn, no cost flexibility."),
    ]

    built_scenarios: list[Scenario] = []
    for name, rev_shock, cost_flex, narrative in scenarios_config:
        adj = _adjust_financials_for_scenario(f, rev_shock, cost_flex)
        sim = simulate_12_month_cash_flow(adj,
                                          monthly_revenue_growth_rate=rev_shock / 12.0,
                                          monthly_cost_reduction_rate=cost_flex / 12.0)
        cr = _safe_div(adj.current_assets, adj.current_liabilities)
        gc_est = _quick_gc_risk(adj.operating_cash_flow, cr, int(sim.requires_external_funding) * 3)
        built_scenarios.append(Scenario(
            name=name,
            revenue_shock_pct=rev_shock,
            cost_flexibility_pct=cost_flex,
            adjusted_ocf=round(adj.operating_cash_flow, 2) if adj.operating_cash_flow else None,
            adjusted_current_ratio=round(cr, 2) if cr else None,
            cash_simulation=sim,
            gc_risk_estimate=gc_est,
            narrative=narrative,
        ))

    best, base, worst = built_scenarios

    # Stress resilience assessment
    if worst.gc_risk_estimate == "LOW" and base.gc_risk_estimate == "LOW":
        resilience = "RESILIENT"
    elif worst.gc_risk_estimate == "HIGH" and base.gc_risk_estimate == "HIGH":
        resilience = "NON-VIABLE"
    elif worst.gc_risk_estimate == "HIGH" and base.gc_risk_estimate in ("LOW", "MEDIUM"):
        resilience = "FRAGILE"
    else:
        resilience = "STRESSED"

    # Binary search for break-even revenue shock (10-step approximation)
    break_even: float | None = None
    if f.operating_cash_flow is not None:
        for shock_pct in [-0.05, -0.10, -0.15, -0.20, -0.25, -0.30, -0.40, -0.50]:
            test = _adjust_financials_for_scenario(f, shock_pct, 0.0)
            test_sim = simulate_12_month_cash_flow(test)
            if test_sim.requires_external_funding:
                break_even = shock_pct
                break

    summary = (
        f"Under BASE scenario: GC risk = {base.gc_risk_estimate}. "
        f"Under WORST case (-30% revenue): GC risk = {worst.gc_risk_estimate}. "
        f"Stress resilience: {resilience}. "
        + (f"Entity enters GC concern territory at approximately {abs(break_even):.0%} revenue decline." if break_even else
           "Entity appears sustainable even under severe stress scenarios.")
    )

    return ScenarioAnalysis(
        best=best,
        base=base,
        worst=worst,
        stress_resilience=resilience,
        break_even_revenue_shock=break_even,
        summary=summary,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# MODULE 5 — Industry Benchmarking (12-Sector Database)
# ═══════════════════════════════════════════════════════════════════════════════

# Sector median ratios — sourced from Damodaran (Jan 2024), NSE/BSE sector data,
# and RBI Financial Stability Reports for Indian sectors.
# Values: (current_ratio, interest_coverage, debt_to_equity, ocf_margin, altman_z_safe_threshold)
_INDUSTRY_BENCHMARKS: dict[str, dict[str, float]] = {
    "manufacturing": {
        "current_ratio_median": 1.40,
        "interest_coverage_median": 4.5,
        "debt_to_equity_median": 0.80,
        "ocf_margin_median": 0.08,       # OCF / Revenue
        "altman_z_safe": 2.90,
        "piotroski_median": 5.0,
    },
    "it_services": {
        "current_ratio_median": 2.80,
        "interest_coverage_median": 35.0,
        "debt_to_equity_median": 0.05,
        "ocf_margin_median": 0.18,
        "altman_z_safe": 3.50,
        "piotroski_median": 6.5,
    },
    "nbfc": {
        "current_ratio_median": 1.10,
        "interest_coverage_median": 1.8,
        "debt_to_equity_median": 5.0,   # High leverage is structural for NBFCs
        "ocf_margin_median": 0.12,
        "altman_z_safe": 1.50,          # Adjusted for financial firms
        "piotroski_median": 4.5,
    },
    "retail": {
        "current_ratio_median": 1.20,
        "interest_coverage_median": 6.0,
        "debt_to_equity_median": 0.60,
        "ocf_margin_median": 0.05,
        "altman_z_safe": 2.50,
        "piotroski_median": 4.8,
    },
    "real_estate": {
        "current_ratio_median": 1.50,
        "interest_coverage_median": 2.5,
        "debt_to_equity_median": 1.80,
        "ocf_margin_median": 0.10,
        "altman_z_safe": 2.0,
        "piotroski_median": 4.0,
    },
    "pharma": {
        "current_ratio_median": 2.10,
        "interest_coverage_median": 12.0,
        "debt_to_equity_median": 0.30,
        "ocf_margin_median": 0.14,
        "altman_z_safe": 3.20,
        "piotroski_median": 5.5,
    },
    "infrastructure": {
        "current_ratio_median": 1.05,
        "interest_coverage_median": 2.2,
        "debt_to_equity_median": 2.50,
        "ocf_margin_median": 0.12,
        "altman_z_safe": 1.80,
        "piotroski_median": 4.0,
    },
    "fmcg": {
        "current_ratio_median": 1.60,
        "interest_coverage_median": 25.0,
        "debt_to_equity_median": 0.15,
        "ocf_margin_median": 0.15,
        "altman_z_safe": 3.80,
        "piotroski_median": 6.0,
    },
    "hospitality": {
        "current_ratio_median": 0.90,
        "interest_coverage_median": 3.0,
        "debt_to_equity_median": 1.20,
        "ocf_margin_median": 0.08,
        "altman_z_safe": 2.20,
        "piotroski_median": 4.0,
    },
    "telecom": {
        "current_ratio_median": 0.70,
        "interest_coverage_median": 1.5,
        "debt_to_equity_median": 3.00,
        "ocf_margin_median": 0.20,
        "altman_z_safe": 1.60,
        "piotroski_median": 3.5,
    },
    "banking": {
        "current_ratio_median": 1.00,   # Not meaningful for banks — CASA ratio more relevant
        "interest_coverage_median": 1.5,
        "debt_to_equity_median": 8.0,   # High leverage is structural
        "ocf_margin_median": 0.15,
        "altman_z_safe": 1.20,
        "piotroski_median": 4.0,
    },
    "general": {   # Fallback for unknown sectors
        "current_ratio_median": 1.50,
        "interest_coverage_median": 5.0,
        "debt_to_equity_median": 1.00,
        "ocf_margin_median": 0.10,
        "altman_z_safe": 2.70,
        "piotroski_median": 5.0,
    },
}

# Sector name aliases (normalise input)
_SECTOR_ALIASES: dict[str, str] = {
    "it": "it_services", "technology": "it_services", "software": "it_services",
    "bank": "banking", "banks": "banking", "financial services": "nbfc",
    "finance": "nbfc", "ml": "nbfc",
    "pharma": "pharma", "pharmaceutical": "pharma", "healthcare": "pharma",
    "fmcg": "fmcg", "consumer goods": "fmcg", "consumer staples": "fmcg",
    "real estate": "real_estate", "realty": "real_estate", "construction": "real_estate",
    "infra": "infrastructure", "power": "infrastructure", "energy": "infrastructure",
    "hotel": "hospitality", "tourism": "hospitality",
    "telecom": "telecom", "communications": "telecom",
    "retail": "retail", "e-commerce": "retail",
    "manufacturing": "manufacturing", "auto": "manufacturing", "automotive": "manufacturing",
    "steel": "manufacturing", "cement": "manufacturing", "chemicals": "manufacturing",
}


def _resolve_sector(raw: str | None) -> str:
    if not raw:
        return "general"
    key = raw.strip().lower()
    return _SECTOR_ALIASES.get(key, key if key in _INDUSTRY_BENCHMARKS else "general")


@dataclass
class BenchmarkGap:
    metric: str
    entity_value: float | None
    sector_median: float
    gap: float | None        # entity - sector (negative = entity is worse)
    percentile_estimate: str # "BELOW_25th" | "25th–50th" | "50th–75th" | "ABOVE_75th"
    flag: str               # "SIGNIFICANTLY_BELOW" | "BELOW" | "IN_LINE" | "ABOVE"


@dataclass
class IndustryBenchmark:
    sector: str
    sector_key: str
    benchmarks_used: dict[str, float]
    gaps: list[BenchmarkGap]
    overall_position: str   # "INDUSTRY_LAGGARD" | "BELOW_MEDIAN" | "MEDIAN" | "ABOVE_MEDIAN"
    peer_gc_risk_context: str
    interpretation: str


def benchmark_against_industry(
    f: GoingConcernFinancials,
    liquidity: LiquiditySolvencyResult,
    altman: AltmanResult,
    piotroski: PiotroskiResult,
) -> IndustryBenchmark:
    """
    Compare entity's key ratios against sector median benchmarks.
    Returns gap analysis and percentile position estimate.
    """
    sector_key = _resolve_sector(f.industry_sector)
    benchmarks = _INDUSTRY_BENCHMARKS[sector_key]
    gaps: list[BenchmarkGap] = []

    def _classify_gap(val: float | None, median: float, higher_is_better: bool) -> BenchmarkGap:
        """Classify entity's performance vs sector median."""
        return val, median  # placeholder — built inline below

    def _make_gap(metric: str, entity_val: float | None, median: float,
                  higher_is_better: bool = True) -> BenchmarkGap:
        gap = (entity_val - median) if entity_val is not None else None
        if entity_val is None:
            pct = "UNKNOWN"
            flag = "UNKNOWN"
        else:
            ratio = entity_val / median if median != 0 else 0
            if higher_is_better:
                if ratio < 0.50:
                    pct, flag = "BELOW_25th", "SIGNIFICANTLY_BELOW"
                elif ratio < 0.85:
                    pct, flag = "25th–50th", "BELOW"
                elif ratio <= 1.20:
                    pct, flag = "50th–75th", "IN_LINE"
                else:
                    pct, flag = "ABOVE_75th", "ABOVE"
            else:  # lower is better (e.g. debt/equity)
                if ratio > 2.0:
                    pct, flag = "BELOW_25th", "SIGNIFICANTLY_BELOW"
                elif ratio > 1.20:
                    pct, flag = "25th–50th", "BELOW"
                elif ratio <= 0.80:
                    pct, flag = "ABOVE_75th", "ABOVE"
                else:
                    pct, flag = "50th–75th", "IN_LINE"
        return BenchmarkGap(
            metric=metric,
            entity_value=round(entity_val, 3) if entity_val is not None else None,
            sector_median=median,
            gap=round(gap, 3) if gap is not None else None,
            percentile_estimate=pct,
            flag=flag,
        )

    gaps.append(_make_gap("Current Ratio",      liquidity.current_ratio,
                          benchmarks["current_ratio_median"]))
    gaps.append(_make_gap("Interest Coverage",  liquidity.interest_coverage,
                          benchmarks["interest_coverage_median"]))
    gaps.append(_make_gap("Debt to Equity",     liquidity.debt_to_equity,
                          benchmarks["debt_to_equity_median"], higher_is_better=False))

    ocf_margin = _safe_div(f.operating_cash_flow, f.revenue)
    gaps.append(_make_gap("OCF Margin",          ocf_margin,
                          benchmarks["ocf_margin_median"]))
    gaps.append(_make_gap("Altman Z' Score",     altman.z_score,
                          benchmarks["altman_z_safe"]))
    gaps.append(_make_gap("Piotroski F Score",   float(piotroski.f_score),
                          benchmarks["piotroski_median"]))

    laggard_count = sum(1 for g in gaps if g.flag == "SIGNIFICANTLY_BELOW")
    below_count = sum(1 for g in gaps if g.flag == "BELOW")

    if laggard_count >= 3:
        position = "INDUSTRY_LAGGARD"
        gc_context = "Entity significantly trails sector peers on multiple dimensions — peer-relative GC risk is HIGH."
    elif laggard_count >= 1 or below_count >= 3:
        position = "BELOW_MEDIAN"
        gc_context = "Entity is below industry median on key risk metrics — warrants closer SA 570 scrutiny relative to peers."
    elif below_count >= 1:
        position = "MEDIAN"
        gc_context = "Entity is broadly in line with sector peers — no elevated peer-relative GC risk."
    else:
        position = "ABOVE_MEDIAN"
        gc_context = "Entity outperforms sector peers — peer-relative GC concern is LOW."

    interp = (
        f"Benchmarked against {sector_key.replace('_', ' ').title()} sector medians. "
        f"Entity position: {position}. "
        f"{laggard_count} metrics significantly below sector. "
        f"{gc_context}"
    )

    return IndustryBenchmark(
        sector=f.industry_sector or "General",
        sector_key=sector_key,
        benchmarks_used=benchmarks,
        gaps=gaps,
        overall_position=position,
        peer_gc_risk_context=gc_context,
        interpretation=interp,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Serialization helper
# ═══════════════════════════════════════════════════════════════════════════════

def _to_dict(obj: Any) -> Any:
    """Recursively convert dataclasses + nested objects to JSON-safe dicts."""
    from dataclasses import asdict as _asdict, is_dataclass
    if is_dataclass(obj) and not isinstance(obj, type):
        return {k: _to_dict(v) for k, v in _asdict(obj).items()}
    if isinstance(obj, list):
        return [_to_dict(i) for i in obj]
    if isinstance(obj, dict):
        return {k: _to_dict(v) for k, v in obj.items()}
    return obj


def advanced_gc_to_dict(
    score: GCRiskScore,
    bankruptcy: BankruptcyPrediction,
    simulation: CashFlowSimulation,
    scenarios: ScenarioAnalysis,
    benchmarks: IndustryBenchmark,
) -> dict[str, Any]:
    """Produce a single JSON-safe dict for API response / seal bundle."""
    return {
        "gc_risk_score":         _to_dict(score),
        "bankruptcy_prediction": _to_dict(bankruptcy),
        "cash_flow_simulation":  _to_dict(simulation),
        "scenario_analysis":     _to_dict(scenarios),
        "industry_benchmarks":   _to_dict(benchmarks),
    }
