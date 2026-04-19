# pyre-ignore-all-errors
from unittest.mock import patch
import pytest

from arkashri.services.blockchain_adapter import list_adapters, run_adapter_anchor


def test_adapter_catalog_excludes_simulated_providers() -> None:
    adapters = list_adapters()
    adapter_keys = {item["adapter_key"] for item in adapters}
    assert "POLKADOT" in adapter_keys
    assert "HASH_NOTARY" in adapter_keys
    assert "SIMULATED_CHAIN" not in adapter_keys


@patch("arkashri.services.blockchain_adapter.get_settings")
def test_polkadot_adapter_fails_closed_when_disabled(mock_get_settings) -> None:
    mock_get_settings.return_value.polkadot_enabled = False
    with pytest.raises(RuntimeError):
        run_adapter_anchor(
            "POLKADOT",
            tenant_id="tenant_a",
            jurisdiction="IN",
            merkle_root="b" * 64,
            window_start_event_id=1,
            window_end_event_id=10,
            chain_anchor_id=7,
        )


@patch("arkashri.services.blockchain_adapter.get_settings")
def test_hash_notary_requires_external_provider(mock_get_settings) -> None:
    mock_get_settings.return_value.hash_notary_url = None

    with pytest.raises(RuntimeError):
        run_adapter_anchor(
            "HASH_NOTARY",
            tenant_id="tenant_a",
            jurisdiction="IN",
            merkle_root="c" * 64,
            window_start_event_id=5,
            window_end_event_id=8,
            chain_anchor_id=11,
        )
