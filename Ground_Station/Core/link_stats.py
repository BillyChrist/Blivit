"""Link / receive statistics for periodic status reporting."""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from typing import Optional

from heartbeat import HEARTBEAT_PACKET_SIZE


@dataclass
class LinkStats:
    link_state: str = "waiting"
    handshake: str = "none"
    packets_received: int = 0
    acks_sent: int = 0
    last_seq: Optional[int] = None
    last_interval_ms: Optional[float] = None
    avg_interval_ms: Optional[float] = None
    estimated_hz: Optional[float] = None
    packet_payload_bytes: int = HEARTBEAT_PACKET_SIZE
    wire_format: str = "text"
    last_rx_monotonic: Optional[float] = None


class LinkStatsTracker:
    def __init__(self, *, window: int = 32) -> None:
        self._intervals: deque[float] = deque(maxlen=window)
        self._last_rx: Optional[float] = None
        self.stats = LinkStats()

    def note_handshake(self, event: str) -> None:
        self.stats.handshake = event

    def note_ack_sent(self) -> None:
        self.stats.acks_sent += 1

    def note_packet(
        self,
        *,
        sequence: int,
        wire_format: str = "text",
        payload_bytes: int = HEARTBEAT_PACKET_SIZE,
    ) -> None:
        now = time.monotonic()
        if self._last_rx is not None:
            interval_ms = (now - self._last_rx) * 1000.0
            self._intervals.append(interval_ms)
            self.stats.last_interval_ms = interval_ms
            if self._intervals:
                avg = sum(self._intervals) / len(self._intervals)
                self.stats.avg_interval_ms = avg
                self.stats.estimated_hz = 1000.0 / avg if avg > 0 else None

        self._last_rx = now
        self.stats.last_rx_monotonic = now
        self.stats.packets_received += 1
        self.stats.last_seq = sequence
        self.stats.wire_format = wire_format
        self.stats.packet_payload_bytes = payload_bytes
        if self.stats.handshake in ("none", "remote_hello", "hello"):
            self.stats.handshake = "telemetry"

    def set_link_state(self, state: str) -> None:
        self.stats.link_state = state

    def format_status_line(self, *, port: str, baud: int, mode: str) -> str:
        s = self.stats
        mode_label = "USB debug" if mode == "debug" else "RFD900"
        parts = [f"Link {s.link_state}", f"{port} @ {baud} baud", mode_label]
        if s.last_seq is not None:
            parts.append(f"seq {s.last_seq}")
        if s.estimated_hz is not None:
            parts.append(f"{s.estimated_hz:.1f} Hz")
        elif s.last_interval_ms is not None:
            parts.append(f"Δt {s.last_interval_ms:.0f} ms")
        return "[STATUS] " + " · ".join(parts)
