# pyre-ignore-all-errors
from arkashri.services.orchestrator import requires_approval, resolve_agent_key


def test_requires_approval_for_governance_roles() -> None:
    assert requires_approval("Engagement Partner", {}) is True
    assert requires_approval("Audit Manager", {}) is True
    assert requires_approval("Senior Auditor", {}) is False


def test_resolve_agent_key_has_stable_fallback() -> None:
    assert resolve_agent_key("Audit Lead") == "rule_linter"
    assert resolve_agent_key("Unmapped Role") == "coverage_guard"
