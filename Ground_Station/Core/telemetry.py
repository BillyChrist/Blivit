"""
Thread-safe telemetry snapshots for concurrent plotting, logging, and display.

The serial reader publishes immutable TelemetrySnapshot objects. Consumers read
copies via copy_state() / get_latest() or pull from consumer_queue() without
blocking the reader (bounded queue drops oldest pressure on slow consumers).
"""

from __future__ import annotations

import queue
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Callable, Optional

from config import TELEMETRY_HISTORY_SIZE, TELEMETRY_QUEUE_SIZE
from heartbeat import HeartbeatPacket
from serial_receiver import DebugTelemetry


@dataclass(frozen=True, slots=True)
class TelemetrySnapshot:
    """Immutable view of one complete telemetry sample."""

    received_at: float
    sequence: int
    uptime_ms: int
    source: str
    gps_valid: bool
    gps_satellites: int
    hdop: float
    latitude: float
    longitude: float
    altitude: float
    speed: float
    course: float
    vel_n: float
    vel_e: float
    vel_d: float
    climb_rate: float
    roll: float
    pitch: float
    yaw: float
    temperature: float
    accel_x: float
    accel_y: float
    accel_z: float
    gyro_x: float
    gyro_y: float
    gyro_z: float
    mag_x: float
    mag_y: float
    mag_z: float
    imu_frames: int = 0
    imu_bytes: int = 0
    utc: str = ""
    date: str = ""

    @classmethod
    def from_debug(cls, data: DebugTelemetry) -> TelemetrySnapshot:
        return cls(
            received_at=time.monotonic(),
            sequence=data.sequence,
            uptime_ms=data.uptime_ms,
            source="debug",
            gps_valid=data.gps_valid,
            gps_satellites=data.gps_satellites,
            hdop=data.hdop,
            latitude=data.latitude,
            longitude=data.longitude,
            altitude=data.altitude,
            speed=data.speed,
            course=data.course,
            vel_n=data.vel_n,
            vel_e=data.vel_e,
            vel_d=data.vel_d,
            climb_rate=data.climb_rate,
            roll=data.roll,
            pitch=data.pitch,
            yaw=data.yaw,
            temperature=data.temperature,
            imu_frames=data.imu_frames,
            imu_bytes=data.imu_bytes,
            accel_x=data.accel_x,
            accel_y=data.accel_y,
            accel_z=data.accel_z,
            gyro_x=data.gyro_x,
            gyro_y=data.gyro_y,
            gyro_z=data.gyro_z,
            mag_x=data.mag_x,
            mag_y=data.mag_y,
            mag_z=data.mag_z,
            utc=data.utc,
            date=data.date,
        )

    @classmethod
    def from_heartbeat(cls, packet: HeartbeatPacket) -> TelemetrySnapshot:
        return cls(
            received_at=time.monotonic(),
            sequence=packet.sequence,
            uptime_ms=packet.uptime_ms,
            source="field",
            gps_valid=bool(packet.gps_fix),
            gps_satellites=packet.gps_satellites,
            hdop=0.0,
            latitude=packet.latitude,
            longitude=packet.longitude,
            altitude=packet.altitude,
            speed=packet.speed,
            course=packet.course,
            vel_n=0.0,
            vel_e=0.0,
            vel_d=0.0,
            climb_rate=0.0,
            roll=0.0,
            pitch=0.0,
            yaw=0.0,
            temperature=0.0,
            accel_x=packet.accel_x,
            accel_y=packet.accel_y,
            accel_z=packet.accel_z,
            gyro_x=packet.gyro_x,
            gyro_y=packet.gyro_y,
            gyro_z=packet.gyro_z,
            mag_x=packet.mag_x,
            mag_y=packet.mag_y,
            mag_z=packet.mag_z,
        )

    def format_gps_line(self) -> str:
        return (
            f"t={self.uptime_ms}ms seq={self.sequence} "
            f"valid={int(self.gps_valid)} sats={self.gps_satellites} hdop={self.hdop:.1f} "
            f"lat={self.latitude:.6f} lon={self.longitude:.6f} alt={self.altitude:.1f} "
            f"spd={self.speed:.2f} crs={self.course:.1f} "
            f"vn={self.vel_n:.2f} ve={self.vel_e:.2f} vd={self.vel_d:.2f} climb={self.climb_rate:.2f} "
            f"utc={self.utc or '--'} date={self.date or '--'}"
        )

    def format_imu_line(self) -> str:
        return (
            f"frames={self.imu_frames} bytes={self.imu_bytes} "
            f"r={self.roll:.2f} p={self.pitch:.2f} y={self.yaw:.2f} temp={self.temperature:.2f} "
            f"accel=({self.accel_x:.3f},{self.accel_y:.3f},{self.accel_z:.3f}) "
            f"gyro=({self.gyro_x:.2f},{self.gyro_y:.2f},{self.gyro_z:.2f}) "
            f"mag=({self.mag_x:.1f},{self.mag_y:.1f},{self.mag_z:.1f})"
        )

    def format_line(self) -> str:
        return f"{self.format_gps_line()} | {self.format_imu_line()}"


@dataclass(frozen=True, slots=True)
class TelemetryState:
    """Point-in-time copy of latest sample plus history (safe for plotting)."""

    latest: Optional[TelemetrySnapshot]
    history: tuple[TelemetrySnapshot, ...]
    seq: int


class TelemetryStore:
    def __init__(
        self,
        history_size: int = TELEMETRY_HISTORY_SIZE,
        queue_size: int = TELEMETRY_QUEUE_SIZE,
    ) -> None:
        self._lock = threading.Lock()
        self._updated = threading.Condition(self._lock)
        self._latest: Optional[TelemetrySnapshot] = None
        self._history: deque[TelemetrySnapshot] = deque(maxlen=history_size)
        self._seq = 0
        self._queue: queue.Queue[TelemetrySnapshot] = queue.Queue(maxsize=queue_size)

    @property
    def seq(self) -> int:
        with self._lock:
            return self._seq

    def publish(self, snapshot: TelemetrySnapshot) -> None:
        with self._updated:
            self._history.append(snapshot)
            self._latest = snapshot
            self._seq += 1
            self._updated.notify_all()

        try:
            self._queue.put_nowait(snapshot)
        except queue.Full:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                pass
            try:
                self._queue.put_nowait(snapshot)
            except queue.Full:
                pass

    def get_latest(self) -> Optional[TelemetrySnapshot]:
        with self._lock:
            return self._latest

    def copy_state(self) -> TelemetryState:
        with self._lock:
            return TelemetryState(
                latest=self._latest,
                history=tuple(self._history),
                seq=self._seq,
            )

    def wait_for_update(self, after_seq: int = 0, timeout: Optional[float] = None) -> int:
        with self._updated:
            if self._seq > after_seq:
                return self._seq
            self._updated.wait(timeout)
            return self._seq

    def consumer_queue(self) -> queue.Queue[TelemetrySnapshot]:
        return self._queue


def run_consumer(
    store: TelemetryStore,
    handler: Callable[[TelemetrySnapshot], None],
    *,
    stop_event: threading.Event,
    poll_timeout: float = 0.5,
) -> None:
    """Drain consumer_queue in a background thread (logging, plotting hooks)."""
    q = store.consumer_queue()
    while not stop_event.is_set():
        try:
            snapshot = q.get(timeout=poll_timeout)
        except queue.Empty:
            continue
        handler(snapshot)
