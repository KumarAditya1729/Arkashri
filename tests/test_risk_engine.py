# pyre-ignore-all-errors
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from arkashri.models import FormulaRegistry, RuleRegistry, SignalType, WeightEntry, WeightSet
from arkashri.services.risk_engine import clamp, compute_risk


async def _seed_risk_configuration(
    db_session,
    *,
    formula_version: int,
    formula_caps: dict[str, float],
    weight_entries: list[dict[str, object]],
    rules: list[RuleRegistry],
) -> None:
    formula = FormulaRegistry(
        version=formula_version,
        formula_text="risk = weighted_sum",
        formula_hash=f"{formula_version}" * 64,
        component_caps=formula_caps,
        is_active=True,
    )
    weight_set = WeightSet(
        version=formula_version,
        weight_hash=f"w{formula_version}" * 32,
        is_active=True,
    )
    db_session.add_all([formula, weight_set])
    await db_session.flush()

    db_session.add_all(
        [
            WeightEntry(
                weight_set_id=weight_set.id,
                signal_type=entry["signal_type"],
                signal_key=entry["signal_key"],
                weight=entry["weight"],
            )
            for entry in weight_entries
        ]
    )
    db_session.add_all(rules)
    await db_session.commit()


def test_clamp_function() -> None:
    assert clamp(0.5, 0.0, 1.0) == 0.5
    assert clamp(1.5, 0.0, 1.0) == 1.0
    assert clamp(-0.5, 0.0, 1.0) == 0.0


@pytest.mark.asyncio
async def test_compute_risk_uses_configured_registry_data(db_session) -> None:
    await _seed_risk_configuration(
        db_session,
        formula_version=1,
        formula_caps={"DETERMINISTIC": 0.7, "ML": 0.3, "TREND": 0.0},
        weight_entries=[
            {"signal_type": SignalType.DETERMINISTIC, "signal_key": "rule_1", "weight": 0.8},
            {"signal_type": SignalType.ML, "signal_key": "model_1", "weight": 0.2},
        ],
        rules=[
            RuleRegistry(
                rule_key="rule_1",
                version=1,
                name="Active status rule",
                description="Flags active records for follow-up review.",
                expression={"field": "status", "op": "eq", "value": "active"},
                signal_value=0.5,
                severity_floor=0.0,
                is_active=True,
            )
        ],
    )

    with patch("arkashri.services.risk_engine.cache_get", new_callable=AsyncMock) as cache_get, patch(
        "arkashri.services.risk_engine.cache_set",
        new_callable=AsyncMock,
    ) as cache_set:
        cache_get.return_value = None
        result = await compute_risk(
            db_session,
            payload={"status": "active"},
            ml_signals=[{"key": "model_1", "value": 0.8}],
            trend_signals=[],
            model_stability=0.9,
        )

    assert result.final_risk == 56.0
    assert result.formula_version == 1
    assert result.weight_set_version == 1
    assert cache_get.await_count == 3
    assert cache_set.await_count == 3


@pytest.mark.asyncio
async def test_compute_risk_uses_database_when_cache_misses(db_session) -> None:
    await _seed_risk_configuration(
        db_session,
        formula_version=2,
        formula_caps={"DETERMINISTIC": 0.9, "ML": 0.1, "TREND": 0.0},
        weight_entries=[
            {"signal_type": SignalType.DETERMINISTIC, "signal_key": "rule_2", "weight": 0.9},
            {"signal_type": SignalType.ML, "signal_key": "model_2", "weight": 0.1},
        ],
        rules=[],
    )

    with patch("arkashri.services.risk_engine.cache_get", new_callable=AsyncMock) as cache_get, patch(
        "arkashri.services.risk_engine.cache_set",
        new_callable=AsyncMock,
    ) as cache_set:
        cache_get.return_value = None
        result = await compute_risk(
            db_session,
            payload={},
            ml_signals=[{"key": "model_2", "value": 1.0}],
            trend_signals=[],
            model_stability=0.9,
        )

    assert result.final_risk == 10.0
    assert result.formula_version == 2
    assert result.weight_set_version == 2
    assert cache_get.await_count == 3
    assert cache_set.await_count == 3
