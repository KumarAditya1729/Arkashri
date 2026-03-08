from arkashri.services.hash_chain import ZERO_HASH, compute_event_hash


def test_hash_chain_changes_with_payload_and_prev_hash() -> None:
    payload = {
        "tenant_id": "t1",
        "jurisdiction": "IN",
        "event_type": "X",
        "entity_type": "transaction",
        "entity_id": "1",
        "payload": {"a": 1},
    }
    h1 = compute_event_hash(ZERO_HASH, payload)
    h2 = compute_event_hash(h1, payload)

    assert h1 != h2
    assert len(h1) == 64


def test_hash_chain_is_deterministic() -> None:
    payload = {
        "tenant_id": "t1",
        "jurisdiction": "IN",
        "event_type": "X",
        "entity_type": "transaction",
        "entity_id": "1",
        "payload": {"a": 1, "b": 2},
    }
    first = compute_event_hash(ZERO_HASH, payload)
    second = compute_event_hash(ZERO_HASH, payload)

    assert first == second
