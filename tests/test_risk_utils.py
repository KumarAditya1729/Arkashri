# pyre-ignore-all-errors
from arkashri.services.risk_engine import evaluate_expression, get_nested


def test_get_nested_works_for_dot_path() -> None:
    payload = {"txn": {"amount": 1200, "currency": "INR"}}
    assert get_nested(payload, "txn.amount") == 1200
    assert get_nested(payload, "txn.missing") is None


def test_evaluate_expression_with_nested_all_any() -> None:
    payload = {"txn": {"amount": 1200, "country": "IN", "tags": ["high_value"]}}
    expr = {
        "all": [
            {"field": "txn.amount", "op": "gte", "value": 1000},
            {
                "any": [
                    {"field": "txn.country", "op": "eq", "value": "IN"},
                    {"field": "txn.tags", "op": "contains", "value": "priority"},
                ]
            },
        ]
    }
    assert evaluate_expression(payload, expr) is True
