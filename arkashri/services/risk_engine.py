# pyre-ignore-all-errors
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from opentelemetry import trace

from arkashri.models import FormulaRegistry, RuleRegistry, SignalType, WeightSet, WeightEntry
from arkashri.cache import cache_get, cache_set

tracer = trace.get_tracer(__name__)


@dataclass
class ComputedComponent:
    signal_type: SignalType
    signal_key: str
    raw_value: float
    normalized_value: float
    weight: float
    contribution: float


@dataclass
class RiskComputationResult:
    final_risk: float
    formula_version: int
    weight_set_version: int
    rule_snapshot: list[dict[str, Any]]
    model_versions: list[dict[str, Any]]
    components: list[ComputedComponent]
    confidence_breakdown: dict[str, float]

    def components_as_dicts(self) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for item in self.components:
            serialized = asdict(item)  # type: ignore
            serialized["signal_type"] = item.signal_type.value
            result.append(serialized)
        return result


def clamp(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(value, max_value))


def get_nested(payload: dict[str, Any], dotted_key: str) -> Any:
    current: Any = payload
    for part in dotted_key.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def evaluate_expression(payload: dict[str, Any], expression: dict[str, Any]) -> bool:
    if "all" in expression:
        return all(evaluate_expression(payload, item) for item in expression["all"])
    if "any" in expression:
        return any(evaluate_expression(payload, item) for item in expression["any"])

    field = expression.get("field")
    op = expression.get("op")
    expected = expression.get("value")
    actual = get_nested(payload, field) if field else None

    if op == "eq":
        return actual == expected
    if op == "ne":
        return actual != expected
    if op == "gt":
        return actual is not None and actual > expected
    if op == "gte":
        return actual is not None and actual >= expected
    if op == "lt":
        return actual is not None and actual < expected
    if op == "lte":
        return actual is not None and actual <= expected
    if op == "in":
        return actual in expected if isinstance(expected, list) else False
    if op == "not_in":
        return actual not in expected if isinstance(expected, list) else False
    if op == "contains":
        return isinstance(actual, (list, str)) and expected is not None and expected in actual
    if op == "exists":
        return actual is not None

    raise ValueError(f"Unsupported operation: {op}")


def _collect_fields(expression: dict[str, Any], collector: set[str]) -> None:
    if "all" in expression:
        for item in expression["all"]:
            _collect_fields(item, collector)
        return
    if "any" in expression:
        for item in expression["any"]:
            _collect_fields(item, collector)
        return

    field = expression.get("field")
    if field:
        collector.add(field)


async def _active_formula(session: AsyncSession, version: int | None = None) -> FormulaRegistry:
    cache_key = f"formula:v:{version}" if version else "formula:active:latest"
    cached = await cache_get(cache_key)
    if cached:
        return FormulaRegistry(**cached)

    stmt = select(FormulaRegistry)
    if version is not None:
        stmt = stmt.where(FormulaRegistry.version == version)
    else:
        stmt = stmt.where(FormulaRegistry.is_active.is_(True)).order_by(FormulaRegistry.version.desc())

    formula = await session.scalar(stmt.limit(1))
    if formula is None:
        raise ValueError("No formula version available")
    assert formula is not None

    # Cache for next request
    formula_dict = {
        "version": formula.version,
        "formula_text": formula.formula_text,
        "formula_hash": formula.formula_hash,
        "component_caps": formula.component_caps,
        "is_active": formula.is_active,
    }
    await cache_set(cache_key, formula_dict, ttl=3600)
    return formula


async def _active_weight_set(session: AsyncSession, version: int | None = None) -> WeightSet:
    cache_key = f"weight_set:v:{version}" if version else "weight_set:active:latest"
    cached = await cache_get(cache_key)
    if cached:
        entries_data = cached.pop("entries", [])
        ws = WeightSet(**cached)
        ws.entries = []
        for e in entries_data:
            stype = SignalType(e["signal_type"]) if isinstance(e["signal_type"], str) else e["signal_type"]
            ws.entries.append(WeightEntry(signal_type=stype, signal_key=e["signal_key"], weight=e["weight"]))
        return ws

    stmt = select(WeightSet).options(selectinload(WeightSet.entries))
    if version is not None:
        stmt = stmt.where(WeightSet.version == version)
    else:
        stmt = stmt.where(WeightSet.is_active.is_(True)).order_by(WeightSet.version.desc())

    weight_set = await session.scalar(stmt.limit(1))
    if weight_set is None:
        raise ValueError("No weight set version available")
    assert weight_set is not None

    ws_dict = {
        "version": weight_set.version,
        "weight_hash": weight_set.weight_hash,
        "is_active": weight_set.is_active,
        "entries": [
            {
                "signal_type": e.signal_type.value if hasattr(e.signal_type, 'value') else e.signal_type,
                "signal_key": e.signal_key,
                "weight": e.weight
            } for e in weight_set.entries
        ]
    }
    await cache_set(cache_key, ws_dict, ttl=3600)
    return weight_set


async def _rules_from_snapshot(session: AsyncSession, rule_snapshot: list[dict[str, Any]] | None) -> list[RuleRegistry]:
    if not rule_snapshot:
        cache_key = "rules:active:latest"
        cached = await cache_get(cache_key)
        if cached and isinstance(cached, dict):
            cached_rules = cached.get("rules", [])
            if isinstance(cached_rules, list):
                return [RuleRegistry(**r) for r in cached_rules if isinstance(r, dict)]

        result = await session.scalars(select(RuleRegistry).where(RuleRegistry.is_active.is_(True)))
        rules = list(result)
        
        rules_data = [
            {
                "rule_key": r.rule_key,
                "version": r.version,
                "name": r.name,
                "expression": r.expression,
                "signal_value": r.signal_value,
                "severity_floor": r.severity_floor,
                "is_active": r.is_active
            } for r in rules
        ]
        await cache_set(cache_key, {"rules": rules_data}, ttl=3600)
        return rules

    matched_rules: list[RuleRegistry] = []
    for item in rule_snapshot:
        rk = item["rule_key"]
        rv = item["version"]
        r_key = f"rule:{rk}:v:{rv}"
        cached = await cache_get(r_key)
        if cached and isinstance(cached, dict):
            matched_rules.append(RuleRegistry(**cached))
            continue

        rule = await session.scalar(
            select(RuleRegistry).where(
                RuleRegistry.rule_key == rk, RuleRegistry.version == rv
            )
        )
        if rule is None:
            raise ValueError(f"Missing rule for replay: {rk}@{rv}")
        
        matched_rules.append(rule)
        await cache_set(r_key, {
            "rule_key": rule.rule_key,
            "version": rule.version,
            "name": rule.name,
            "expression": rule.expression,
            "signal_value": rule.signal_value,
            "severity_floor": rule.severity_floor,
            "is_active": rule.is_active
        }, ttl=86400) # cache deterministic replay artifacts for 24h

    return matched_rules


def validate_weight_policy(weight_set: WeightSet, component_caps: dict[str, float]) -> None:
    total = sum(abs(entry.weight) for entry in weight_set.entries)
    if total <= 0:
        raise ValueError("Weight set total must be > 0")

    grouped = {
        SignalType.DETERMINISTIC: 0.0,
        SignalType.ML: 0.0,
        SignalType.TREND: 0.0,
    }
    for entry in weight_set.entries:
        grouped[entry.signal_type] += abs(entry.weight)

    deterministic_ratio = grouped[SignalType.DETERMINISTIC] / total
    ml_ratio = grouped[SignalType.ML] / total
    trend_ratio = grouped[SignalType.TREND] / total

    det_cap = component_caps.get("DETERMINISTIC", 0.7)
    ml_cap = component_caps.get("ML", 0.2)
    trend_cap = component_caps.get("TREND", 0.1)

    if deterministic_ratio < det_cap:
        raise ValueError("Weight policy violation: deterministic allocation below minimum")
    if ml_ratio > ml_cap:
        raise ValueError("Weight policy violation: ML allocation above cap")
    if trend_ratio > trend_cap:
        raise ValueError("Weight policy violation: trend allocation above cap")


async def compute_risk(
    session: AsyncSession,
    *,
    payload: dict[str, Any],
    ml_signals: list[dict[str, Any]],
    trend_signals: list[dict[str, Any]],
    model_stability: float,
    formula_version: int | None = None,
    weight_set_version: int | None = None,
    rule_snapshot: list[dict[str, Any]] | None = None,
) -> RiskComputationResult:
    with tracer.start_as_current_span("compute_risk") as span:
        span.set_attribute("payload.keys_count", len(payload))
        span.set_attribute("signals.ml_count", len(ml_signals))
        span.set_attribute("signals.trend_count", len(trend_signals))
        
        with tracer.start_as_current_span("fetch_configurations"):
            formula = await _active_formula(session, formula_version)
            weight_set = await _active_weight_set(session, weight_set_version)
            rules = await _rules_from_snapshot(session, rule_snapshot)
            validate_weight_policy(weight_set, formula.component_caps)

        weights = {(entry.signal_type, entry.signal_key): entry.weight for entry in weight_set.entries}

        components: list[ComputedComponent] = []
        min_risk_floor = 0.0
        field_collector: set[str] = set()

        snapshot: list[dict[str, Any]] = []
        
        with tracer.start_as_current_span("evaluate_deterministic_rules") as det_span:
            det_span.set_attribute("rules.count", len(rules))
            for rule in sorted(rules, key=lambda r: (r.rule_key, r.version)):
                _collect_fields(rule.expression, field_collector)
                matched = evaluate_expression(payload, rule.expression)
                raw_value = rule.signal_value if matched else 0.0
                normalized = clamp(raw_value, 0.0, 1.0)
                weight = weights.get((SignalType.DETERMINISTIC, rule.rule_key), 0.0)
                contribution = normalized * weight

                components.append(
                    ComputedComponent(
                        signal_type=SignalType.DETERMINISTIC,
                        signal_key=rule.rule_key,
                        raw_value=raw_value,
                        normalized_value=normalized,
                        weight=weight,
                        contribution=contribution,
                    )
                )

                if matched:
                    min_risk_floor = max(min_risk_floor, rule.severity_floor)

                snapshot.append({"rule_key": rule.rule_key, "version": rule.version, "matched": matched})

        model_versions: dict[tuple[str, int], dict[str, Any]] = {}

        with tracer.start_as_current_span("evaluate_ml_signals"):
            for signal in ml_signals:
                key = signal["key"]
                raw_value = float(signal["value"])
                bounded = clamp(raw_value, float(signal.get("lower_bound", 0.0)), float(signal.get("upper_bound", 1.0)))
                normalized = clamp(bounded, 0.0, 1.0)
                weight = weights.get((SignalType.ML, key), 0.0)
                contribution = normalized * weight

                components.append(
                    ComputedComponent(
                        signal_type=SignalType.ML,
                        signal_key=key,
                        raw_value=raw_value,
                        normalized_value=normalized,
                        weight=weight,
                        contribution=contribution,
                    )
                )

                if signal.get("model_key") and signal.get("model_version") is not None:
                    model_key = str(signal["model_key"])
                    model_version = int(signal["model_version"])
                    model_versions[(model_key, model_version)] = {
                        "model_key": model_key,
                        "version": model_version,
                    }

        with tracer.start_as_current_span("evaluate_trend_signals"):
            for signal in trend_signals:
                key = signal["key"]
                raw_value = float(signal["value"])
                bounded = clamp(raw_value, float(signal.get("lower_bound", 0.0)), float(signal.get("upper_bound", 1.0)))
                normalized = clamp(bounded, 0.0, 1.0)
                weight = weights.get((SignalType.TREND, key), 0.0)
                contribution = normalized * weight

                components.append(
                    ComputedComponent(
                        signal_type=SignalType.TREND,
                        signal_key=key,
                        raw_value=raw_value,
                        normalized_value=normalized,
                        weight=weight,
                        contribution=contribution,
                    )
                )

        with tracer.start_as_current_span("aggregate_risk_confidence"):
            risk_sum = sum(component.contribution for component in components)
            final_risk = clamp(risk_sum * 100.0, 0.0, 100.0)
            if min_risk_floor > 0.0:
                final_risk = max(final_risk, min_risk_floor)

            required_fields = len(field_collector)
            present_fields = sum(1 for field in field_collector if get_nested(payload, field) is not None)
            q_data = (present_fields / required_fields) if required_fields > 0 else 1.0

            expected_weighted_signals = len(weights)
            observed_weighted_signals = len(
                {
                    (item.signal_type, item.signal_key)
                    for item in components
                    if (item.signal_type, item.signal_key) in weights
                }
            )
            q_coverage = (
                observed_weighted_signals / expected_weighted_signals if expected_weighted_signals > 0 else 1.0
            )

            q_stability = clamp(model_stability, 0.0, 1.0)
            confidence = clamp(q_data * q_coverage * q_stability, 0.0, 1.0)

            confidence_breakdown = {
                "q_data": float(f"{q_data:.6f}"),
                "q_coverage": float(f"{q_coverage:.6f}"),
                "q_stability": float(f"{q_stability:.6f}"),
                "overall": float(f"{confidence:.6f}"),
            }
            
            span.set_attribute("result.final_risk", float(final_risk))
            span.set_attribute("result.confidence", float(confidence))

        return RiskComputationResult(
            final_risk=float(f"{final_risk:.6f}"),
            formula_version=formula.version,
            weight_set_version=weight_set.version,
            rule_snapshot=snapshot,
            model_versions=sorted(model_versions.values(), key=lambda item: (item["model_key"], item["version"])),
            components=components,
            confidence_breakdown=confidence_breakdown,
        )


