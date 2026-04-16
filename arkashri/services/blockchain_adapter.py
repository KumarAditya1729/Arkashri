# pyre-ignore-all-errors
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from arkashri.config import get_settings
from arkashri.services.canonical import hash_object
from circuitbreaker import circuit, CircuitBreakerError


@dataclass
class AttestationResult:
    adapter_key: str
    network: str
    tx_reference: str
    attestation_hash: str
    provider_payload: dict


class BlockchainAdapter(Protocol):
    adapter_key: str
    network: str

    def anchor(
        self,
        *,
        tenant_id: str,
        jurisdiction: str,
        merkle_root: str,
        window_start_event_id: int,
        window_end_event_id: int,
        chain_anchor_id: int,
    ) -> AttestationResult: ...

    async def check_health(self) -> bool: ...


class SimulatedBlockchainAdapter:
    adapter_key = "SIMULATED_CHAIN"
    network = "ARKASHRI_SIMNET"

    def anchor(
        self,
        *,
        tenant_id: str,
        jurisdiction: str,
        merkle_root: str,
        window_start_event_id: int,
        window_end_event_id: int,
        chain_anchor_id: int,
    ) -> AttestationResult:
        material = {
            "adapter_key": self.adapter_key,
            "tenant_id": tenant_id,
            "jurisdiction": jurisdiction,
            "merkle_root": merkle_root,
            "window_start_event_id": window_start_event_id,
            "window_end_event_id": window_end_event_id,
            "chain_anchor_id": chain_anchor_id,
        }
        attestation_hash = hash_object(material)
        tx_reference = f"sim://{attestation_hash[:28]}"
        return AttestationResult(
            adapter_key=self.adapter_key,
            network=self.network,
            tx_reference=tx_reference,
            attestation_hash=attestation_hash,
            provider_payload={
                "mode": "deterministic_simulation",
                "material_hash": attestation_hash,
            },
        )

    async def check_health(self) -> bool:
        return True


class HashNotaryAdapter:
    adapter_key = "HASH_NOTARY"
    network = "OFFCHAIN_NOTARY"

    def anchor(
        self,
        *,
        tenant_id: str,
        jurisdiction: str,
        merkle_root: str,
        window_start_event_id: int,
        window_end_event_id: int,
        chain_anchor_id: int,
    ) -> AttestationResult:
        material = {
            "adapter_key": self.adapter_key,
            "tenant_id": tenant_id,
            "jurisdiction": jurisdiction,
            "merkle_root": merkle_root,
            "window_start_event_id": window_start_event_id,
            "window_end_event_id": window_end_event_id,
            "chain_anchor_id": chain_anchor_id,
        }
        attestation_hash = hash_object(material)
        tx_reference = f"notary://{attestation_hash[-28:]}"
        return AttestationResult(
            adapter_key=self.adapter_key,
            network=self.network,
            tx_reference=tx_reference,
            attestation_hash=attestation_hash,
            provider_payload={
                "mode": "hash_notary",
                "signature_stub": attestation_hash[:32],
            },
        )

    async def check_health(self) -> bool:
        return True


class PolkadotAdapter:
    adapter_key = "POLKADOT"
    network = "POLKADOT_MAINNET"

    def anchor(
        self,
        *,
        tenant_id: str,
        jurisdiction: str,
        merkle_root: str,
        window_start_event_id: int,
        window_end_event_id: int,
        chain_anchor_id: int,
    ) -> AttestationResult:
        material = {
            "adapter_key": self.adapter_key,
            "network": self.network,
            "tenant_id": tenant_id,
            "jurisdiction": jurisdiction,
            "merkle_root": merkle_root,
            "window_start_event_id": window_start_event_id,
            "window_end_event_id": window_end_event_id,
            "chain_anchor_id": chain_anchor_id,
        }
        attestation_hash = hash_object(material)
        tx_reference = f"polkadot://deterministic/0x{attestation_hash[:48]}"
        provider_payload: dict = {
            "mode": "deterministic_polkadot_stub",
            "extrinsic_stub_hash": f"0x{attestation_hash[:64]}",
            "relay_chain": "polkadot",
        }

        settings = get_settings()
        if settings.polkadot_enabled:
            try:
                tx_reference, provider_payload = _submit_polkadot_anchor(
                    attestation_hash=attestation_hash,
                    merkle_root=merkle_root,
                    tenant_id=tenant_id,
                    jurisdiction=jurisdiction,
                    window_start_event_id=window_start_event_id,
                    window_end_event_id=window_end_event_id,
                    chain_anchor_id=chain_anchor_id,
                )
            except CircuitBreakerError:
                provider_payload["mode"] = "polkadot_circuit_broken"
                provider_payload["remark"] = "The Polkadot relay connection is temporarily broken. The hash was not physically anchored."

        return AttestationResult(
            adapter_key=self.adapter_key,
            network=self.network,
            tx_reference=tx_reference,
            attestation_hash=attestation_hash,
            provider_payload=provider_payload,
        )

    async def check_health(self) -> bool:
        settings = get_settings()
        if not settings.polkadot_enabled:
            return True
        try:
            from substrateinterface import SubstrateInterface
            substrate = SubstrateInterface(url=settings.polkadot_ws_url)
            return substrate.is_connected
        except Exception:
            return False


ADAPTERS: dict[str, BlockchainAdapter] = {
    PolkadotAdapter.adapter_key: PolkadotAdapter(),
    SimulatedBlockchainAdapter.adapter_key: SimulatedBlockchainAdapter(),
    HashNotaryAdapter.adapter_key: HashNotaryAdapter(),
}


def list_adapters() -> list[dict[str, str]]:
    return [
        {"adapter_key": adapter.adapter_key, "network": adapter.network}
        for adapter in sorted(ADAPTERS.values(), key=lambda item: item.adapter_key)
    ]


def run_adapter_anchor(
    adapter_key: str,
    *,
    tenant_id: str,
    jurisdiction: str,
    merkle_root: str,
    window_start_event_id: int,
    window_end_event_id: int,
    chain_anchor_id: int,
) -> AttestationResult:
    adapter = ADAPTERS.get(adapter_key)
    if adapter is None:
        raise ValueError(f"Unknown blockchain adapter: {adapter_key}")
    return adapter.anchor(
        tenant_id=tenant_id,
        jurisdiction=jurisdiction,
        merkle_root=merkle_root,
        window_start_event_id=window_start_event_id,
        window_end_event_id=window_end_event_id,
        chain_anchor_id=chain_anchor_id,
    )


@circuit(failure_threshold=3, recovery_timeout=60)
def _submit_polkadot_anchor(
    *,
    attestation_hash: str,
    merkle_root: str,
    tenant_id: str,
    jurisdiction: str,
    window_start_event_id: int,
    window_end_event_id: int,
    chain_anchor_id: int,
) -> tuple[str, dict]:
    settings = get_settings()
    if not settings.polkadot_keypair_uri:
        raise RuntimeError("POLKADOT_ENABLED=true requires POLKADOT_KEYPAIR_URI")

    try:
        from substrateinterface import Keypair, SubstrateInterface
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "Real Polkadot anchoring requires 'substrate-interface' dependency."
        ) from exc

    substrate = SubstrateInterface(url=settings.polkadot_ws_url, type_registry_preset="polkadot")
    keypair = Keypair.create_from_uri(settings.polkadot_keypair_uri)

    remark_payload = hash_object(
        {
            "attestation_hash": attestation_hash,
            "merkle_root": merkle_root,
            "tenant_id": tenant_id,
            "jurisdiction": jurisdiction,
            "window_start_event_id": window_start_event_id,
            "window_end_event_id": window_end_event_id,
            "chain_anchor_id": chain_anchor_id,
        }
    )

    call = substrate.compose_call(
        call_module="System",
        call_function="remark",
        call_params={"remark": f"ARKASHRI:{remark_payload}".encode("utf-8")},
    )
    extrinsic = substrate.create_signed_extrinsic(call=call, keypair=keypair)
    receipt = substrate.submit_extrinsic(
        extrinsic,
        wait_for_inclusion=settings.polkadot_wait_for_inclusion,
    )

    extrinsic_hash = str(getattr(receipt, "extrinsic_hash", ""))
    block_hash = str(getattr(receipt, "block_hash", ""))
    tx_reference = f"polkadot://{block_hash or 'pending'}/{extrinsic_hash or attestation_hash[:16]}"

    provider_payload = {
        "mode": "polkadot_live",
        "ws_url": settings.polkadot_ws_url,
        "account_ss58": keypair.ss58_address,
        "block_hash": block_hash,
        "extrinsic_hash": extrinsic_hash,
        "remark_hash": remark_payload,
    }
    return tx_reference, provider_payload
