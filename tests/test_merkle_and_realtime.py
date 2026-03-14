# pyre-ignore-all-errors
from arkashri.services.hash_chain import ZERO_HASH
from arkashri.services.merkle import merkle_root
from arkashri.services.realtime import RealtimeHub


def test_merkle_root_is_deterministic() -> None:
    hashes = [
        "a" * 64,
        "b" * 64,
        "c" * 64,
    ]
    first = merkle_root(hashes)
    second = merkle_root(hashes)

    assert first == second
    assert len(first) == 64


def test_merkle_root_for_empty_stream() -> None:
    assert merkle_root([]) == ZERO_HASH


def test_realtime_hub_fetch_since() -> None:
    hub = RealtimeHub()
    channel = "tenant:IN"

    event1 = hub.publish(channel, {"event_type": "A"})
    event2 = hub.publish(channel, {"event_type": "B"})

    assert event1["sequence"] == 1
    assert event2["sequence"] == 2

    events = hub.fetch_since(channel, 1)
    assert len(events) == 1
    assert events[0]["payload"]["event_type"] == "B"
