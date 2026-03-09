from unittest.mock import patch
from arkashri.services.blockchain_adapter import list_adapters, run_adapter_anchor


def test_adapter_catalog_contains_required_defaults() -> None:
    adapters = list_adapters()
    adapter_keys = {item["adapter_key"] for item in adapters}
    assert "POLKADOT" in adapter_keys
    assert "SIMULATED_CHAIN" in adapter_keys
    assert "HASH_NOTARY" in adapter_keys


def test_simulated_adapter_is_deterministic() -> None:
    first = run_adapter_anchor(
        "SIMULATED_CHAIN",
        tenant_id="tenant_a",
        jurisdiction="IN",
        merkle_root="a" * 64,
        window_start_event_id=1,
        window_end_event_id=10,
        chain_anchor_id=7,
    )
    second = run_adapter_anchor(
        "SIMULATED_CHAIN",
        tenant_id="tenant_a",
        jurisdiction="IN",
        merkle_root="a" * 64,
        window_start_event_id=1,
        window_end_event_id=10,
        chain_anchor_id=7,
    )

    assert first.attestation_hash == second.attestation_hash
    assert first.tx_reference == second.tx_reference


@patch("arkashri.services.blockchain_adapter.get_settings")
def test_polkadot_adapter_is_deterministic(mock_get_settings) -> None:
    mock_get_settings.return_value.polkadot_enabled = False
    first = run_adapter_anchor(
        "POLKADOT",
        tenant_id="tenant_a",
        jurisdiction="IN",
        merkle_root="b" * 64,
        window_start_event_id=1,
        window_end_event_id=10,
        chain_anchor_id=7,
    )
    second = run_adapter_anchor(
        "POLKADOT",
        tenant_id="tenant_a",
        jurisdiction="IN",
        merkle_root="b" * 64,
        window_start_event_id=1,
        window_end_event_id=10,
        chain_anchor_id=7,
    )

    assert first.network == "POLKADOT_MAINNET"
    assert first.attestation_hash == second.attestation_hash
    assert first.tx_reference == second.tx_reference
    assert first.tx_reference.startswith("polkadot://deterministic/0x")
