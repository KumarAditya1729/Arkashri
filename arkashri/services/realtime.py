# pyre-ignore-all-errors
from __future__ import annotations

from collections import defaultdict
from threading import Lock
from typing import Any


class RealtimeHub:
    def __init__(self) -> None:
        self._events: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._lock = Lock()
        self._max_events_per_channel = 2000

    def publish(self, channel: str, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            channel_events = self._events[channel]
            sequence = channel_events[-1]["sequence"] + 1 if channel_events else 1
            event = {"sequence": sequence, "payload": payload}
            channel_events.append(event)
            if len(channel_events) > self._max_events_per_channel:
                del channel_events[: len(channel_events) - self._max_events_per_channel]
            return event

    def fetch_since(self, channel: str, last_sequence: int) -> list[dict[str, Any]]:
        with self._lock:
            return [event for event in self._events[channel] if event["sequence"] > last_sequence]


realtime_hub = RealtimeHub()
