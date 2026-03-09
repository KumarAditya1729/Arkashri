import pytest
from arkashri.services.risk_engine import compute_risk, clamp
from arkashri.models import FormulaRegistry, WeightSet, SignalType, WeightEntry

@pytest.mark.asyncio
async def test_clamp_function():
    assert clamp(0.5, 0.0, 1.0) == 0.5
    assert clamp(1.5, 0.0, 1.0) == 1.0
    assert clamp(-0.5, 0.0, 1.0) == 0.0

@pytest.mark.asyncio
async def test_compute_risk_caching_layer(mock_redis, mock_session):
    # Setup mock active formula
    mock_redis["get"].side_effect = [
        {
            "version": 1,
            "formula_text": "risk = f(x)",
            "formula_hash": "hash123",
            "component_caps": {"DETERMINISTIC": 0.7, "ML": 0.2, "TREND": 0.1},
            "is_active": True
        },
        {
            "version": 1,
            "weight_hash": "hash456",
            "is_active": True,
            "entries": [
                {"signal_type": "DETERMINISTIC", "signal_key": "rule_1", "weight": 0.8},
                {"signal_type": "ML", "signal_key": "model_1", "weight": 0.2}
            ]
        },
        {
            "rules": [
                {
                    "rule_key": "rule_1", "version": 1, "name": "Test Rule",
                    "expression": {"field": "status", "op": "eq", "value": "active"},
                    "signal_value": 0.5, "severity_floor": 0.1, "is_active": True
                }
            ]
        }
    ]

    result = await compute_risk(
        mock_session,
        payload={"status": "active"},
        ml_signals=[{"key": "model_1", "value": 0.8}],
        trend_signals=[],
        model_stability=0.9
    )

    # Risk should be deterministic rule (1.0 * 0.8) + ML signal (0.8 * 0.2 = 0.16) since rule_1 matched (value=0.5 -> 0.5) wait, 
    # matched rule normalized value -> clamp(0.5, 0, 1) = 0.5 * weight 0.8 = 0.40 contribution
    # risk_sum = 0.40 + 0.16 = 0.56. Final risk = 56.0
    
    assert result.final_risk == 56.0
    assert result.formula_version == 1
    assert result.weight_set_version == 1
    assert mock_redis["get"].call_count == 3


@pytest.mark.asyncio
async def test_compute_risk_cache_miss_db_fallback(mock_redis, mock_session):
    # Simulate Cache Miss 
    mock_redis["get"].side_effect = [None, None, None]
    
    # Mock DB objects returned by SQLAlchemy
    formula = FormulaRegistry(version=2, formula_text="x", component_caps={"DETERMINISTIC": 0.9, "ML": 0.1})
    weight_entry_1 = WeightEntry(signal_type=SignalType.DETERMINISTIC, signal_key="rule_2", weight=0.9)
    weight_entry_2 = WeightEntry(signal_type=SignalType.ML, signal_key="model_2", weight=0.1)
    weight_set = WeightSet(version=2, entries=[weight_entry_1, weight_entry_2])
    
    mock_session.scalar.side_effect = [formula, weight_set]
    mock_session.scalars.return_value = [] # no rules

    result = await compute_risk(
        mock_session,
        payload={},
        ml_signals=[{"key": "model_2", "value": 1.0}],
        trend_signals=[],
        model_stability=0.9
    )

    # ML Component (1.0 * 0.1 = 0.1) -> 10.0 risk
    assert result.final_risk == 10.0
    assert result.formula_version == 2
    assert result.weight_set_version == 2
    assert mock_redis["get"].call_count == 3
    assert mock_redis["set"].call_count == 3 # Should cache formula, weight_set, rules

