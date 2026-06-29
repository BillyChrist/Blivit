"""Load telemetry CSV logs — ground-station snapshots and avionics onboard logs."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy as np

from config import RECEIVED_DATA_DIR

LogFormat = Literal["avionics", "ground_station", "legacy"]


@dataclass(frozen=True, slots=True)
class TelemetryLog:
    path: Path
    format: LogFormat
    sample_count: int
    duration_s: float
    t_sec: np.ndarray
    source: np.ndarray
    source_mask: np.ndarray
    gps_updates: np.ndarray
    imu_frames: np.ndarray
    imu_frame_type: np.ndarray
    latitude: np.ndarray
    longitude: np.ndarray
    altitude: np.ndarray
    speed: np.ndarray
    vel_n: np.ndarray
    vel_e: np.ndarray
    vel_d: np.ndarray
    climb_rate: np.ndarray
    roll: np.ndarray
    pitch: np.ndarray
    yaw: np.ndarray
    temperature: np.ndarray
    accel_x: np.ndarray
    accel_y: np.ndarray
    accel_z: np.ndarray
    gyro_x: np.ndarray
    gyro_y: np.ndarray
    gyro_z: np.ndarray
    mag_x: np.ndarray
    mag_y: np.ndarray
    mag_z: np.ndarray
    gps_valid: np.ndarray

    @property
    def accel_mag(self) -> np.ndarray:
        return np.sqrt(self.accel_x ** 2 + self.accel_y ** 2 + self.accel_z ** 2)

    @property
    def vel_horiz(self) -> np.ndarray:
        return np.sqrt(self.vel_n ** 2 + self.vel_e ** 2)

    def angle_mask(self) -> np.ndarray:
        """Rows with fresh angle/attitude samples (preferred for attitude plots)."""
        if np.any(self.imu_frame_type == "angle"):
            return self.imu_frame_type == "angle"
        return np.ones(self.sample_count, dtype=bool)

    def accel_mask(self) -> np.ndarray:
        """Rows with fresh accelerometer samples."""
        if np.any(self.imu_frame_type == "accel"):
            return self.imu_frame_type == "accel"
        return np.ones(self.sample_count, dtype=bool)

    def gyro_mask(self) -> np.ndarray:
        if np.any(self.imu_frame_type == "gyro"):
            return self.imu_frame_type == "gyro"
        return np.ones(self.sample_count, dtype=bool)

    def imu_plot_mask(self) -> np.ndarray:
        """Rows with IMU state for time-series plots.

        Avionics logs one row per UART frame (accel/gyro/angle/mag); sensor values are
        carried forward on non-fresh rows. Ground-station logs full snapshots every row.
        """
        if self.format == "avionics":
            sources = np.char.lower(self.source.astype(str))
            if np.any(np.char.find(sources, "imu") >= 0):
                return np.char.find(sources, "imu") >= 0
            return self.imu_frame_type != "--"
        return np.ones(self.sample_count, dtype=bool)

    def fresh_frame_count(self, frame_type: str) -> int:
        return int(np.sum(self.imu_frame_type == frame_type))

    def plot_count_label(self, n: int, *, detail: str = "") -> str:
        """Title fragment explaining what n counts (avionics fresh frames vs GS snapshots)."""
        if self.format == "avionics" and detail:
            if n != self.sample_count:
                return f"{detail} = {n} / {self.sample_count} log rows"
            return f"{detail} = {n}"
        if self.format == "ground_station" and detail:
            return f"snapshot rows = {n}"
        return f"n = {n}"

    def gps_event_mask(self) -> np.ndarray:
        """Rows that represent a GPS update (avoid stair-steps from carried-forward GPS)."""
        sources = np.char.lower(self.source.astype(str))
        if np.any(np.char.find(sources, "gps") >= 0):
            return np.char.find(sources, "gps") >= 0

        if self.gps_updates.size and int(np.max(self.gps_updates)) > 0:
            delta = np.diff(self.gps_updates, prepend=self.gps_updates[0])
            return delta > 0

        valid = self.gps_valid
        if not np.any(valid):
            return valid

        changed = np.zeros(self.sample_count, dtype=bool)
        changed[0] = bool(valid[0])
        for i in range(1, self.sample_count):
            if not valid[i]:
                continue
            changed[i] = (
                abs(self.latitude[i] - self.latitude[i - 1]) > 1e-8
                or abs(self.longitude[i] - self.longitude[i - 1]) > 1e-8
                or abs(self.altitude[i] - self.altitude[i - 1]) > 0.05
            )
        return changed

    def series(self, mask: np.ndarray, values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        mask = np.asarray(mask, dtype=bool)
        return self.t_sec[mask], values[mask]

    def _gps_valid_mask(self, gps_mask: np.ndarray | None = None) -> np.ndarray:
        mask = gps_mask if gps_mask is not None else self.gps_event_mask()
        return (
            mask
            & self.gps_valid
            & (np.abs(self.latitude) > 1e-6)
            & (np.abs(self.longitude) > 1e-6)
        )

    def gps_unique_fix_mask(self, gps_mask: np.ndarray | None = None) -> np.ndarray:
        """Drop consecutive GPS rows with identical lat/lon (same reported fix)."""
        valid = self._gps_valid_mask(gps_mask)
        indices = np.flatnonzero(valid)
        if indices.size == 0:
            return valid

        keep = np.zeros(indices.size, dtype=bool)
        keep[0] = True
        for i in range(1, indices.size):
            prev_i = indices[i - 1]
            curr_i = indices[i]
            if (
                abs(self.latitude[curr_i] - self.latitude[prev_i]) > 1e-8
                or abs(self.longitude[curr_i] - self.longitude[prev_i]) > 1e-8
                or abs(self.altitude[curr_i] - self.altitude[prev_i]) > 0.01
            ):
                keep[i] = True

        unique = np.zeros(self.sample_count, dtype=bool)
        unique[indices[keep]] = True
        return unique

    def gps_drift_summary(self, *, gps_mask: np.ndarray | None = None) -> str:
        """Human-readable GPS scatter/spread for plot subtitles."""
        unique = self.gps_unique_fix_mask(gps_mask)
        east, north, up = self.local_enu_m(gps_mask=unique)
        if east.size == 0:
            return "no GPS fixes"

        horiz_span = float(max(east.max() - east.min(), north.max() - north.min()))
        alt_span = float(up.max() - up.min())
        raw_n = int(np.count_nonzero(self._gps_valid_mask(gps_mask)))
        uniq_n = int(east.size)
        return (
            f"unique fixes={uniq_n}/{raw_n} · "
            f"horiz span {horiz_span:.1f} m · alt span {alt_span:.1f} m"
        )

    def local_enu_m(self, *, gps_mask: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """East / north / up (m) relative to first valid GPS fix."""
        valid = self._gps_valid_mask(gps_mask)
        if not np.any(valid):
            return np.zeros(0), np.zeros(0), np.zeros(0)

        idx = int(np.argmax(valid))
        lat0 = np.radians(self.latitude[idx])
        lon0 = np.radians(self.longitude[idx])
        alt0 = self.altitude[idx]

        lat_r = np.radians(self.latitude[valid])
        lon_r = np.radians(self.longitude[valid])
        earth_r = 6_371_000.0

        east = earth_r * (lon_r - lon0) * np.cos(lat0)
        north = earth_r * (lat_r - lat0)
        up = self.altitude[valid] - alt0
        return east, north, up

    def gps_track_enu_msl(self, *, gps_mask: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Easting, northing [m] and altitude MSL [m] for GPS event samples."""
        valid = self._gps_valid_mask(gps_mask)
        if not np.any(valid):
            return np.zeros(0), np.zeros(0), np.zeros(0)

        idx = int(np.argmax(valid))
        lat0 = np.radians(self.latitude[idx])
        lon0 = np.radians(self.longitude[idx])

        lat_r = np.radians(self.latitude[valid])
        lon_r = np.radians(self.longitude[valid])
        earth_r = 6_371_000.0

        east = earth_r * (lon_r - lon0) * np.cos(lat0)
        north = earth_r * (lat_r - lat0)
        alt_msl = self.altitude[valid]
        return east, north, alt_msl

    def gps_track_series(
        self, *, dedupe: bool = True, gps_mask: np.ndarray | None = None
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """Time, east/north [m] from first fix, altitude MSL [m], horizontal distance [m]."""
        mask = self.gps_unique_fix_mask(gps_mask) if dedupe else self._gps_valid_mask(gps_mask)
        t = self.t_sec[mask]
        east, north, up = self.local_enu_m(gps_mask=mask)
        alt_msl = self.altitude[mask]
        horiz_dist = np.hypot(east, north)
        return t, east, north, alt_msl, horiz_dist


def discover_telemetry_logs() -> list[Path]:
    roots = {Path(RECEIVED_DATA_DIR)}
    parent = Path(RECEIVED_DATA_DIR).parent
    for child in parent.iterdir():
        if child.is_dir() and child.name.lower() == "received_data":
            roots.add(child)

    files: list[Path] = []
    for root in roots:
        if root.is_dir():
            files.extend(root.glob("telemetry_*.csv"))
            files.extend(root.glob("AvionicsTelem_*.csv"))

    return sorted({f.resolve() for f in files}, key=lambda p: p.stat().st_mtime, reverse=True)


def _detect_format(fieldnames: list[str] | None) -> LogFormat:
    if not fieldnames:
        return "legacy"
    headers = set(fieldnames)
    if "received_at" in headers:
        return "ground_station"
    if "source_mask" in headers or "imu_frame_type" in headers or "gps_updates" in headers:
        return "avionics"
    return "legacy"


def load_telemetry_csv(path: str | Path) -> TelemetryLog:
    csv_path = Path(path)
    rows: list[dict[str, str]] = []
    with csv_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        log_format = _detect_format(reader.fieldnames)
        for row in reader:
            rows.append(row)

    if not rows:
        raise ValueError(f"No rows in {csv_path}")

    def col_float(name: str, default: float = 0.0) -> np.ndarray:
        out = np.empty(len(rows), dtype=float)
        for i, row in enumerate(rows):
            raw = row.get(name, "")
            if raw in ("", "True", "False"):
                if raw == "True":
                    out[i] = 1.0
                elif raw == "False":
                    out[i] = 0.0
                else:
                    out[i] = default
            else:
                out[i] = float(raw)
        return out

    def col_str(name: str, default: str = "") -> np.ndarray:
        return np.array([(row.get(name) or default) for row in rows], dtype=object)

    uptime_ms = col_float("uptime_ms")
    t0 = uptime_ms[0]
    t_sec = (uptime_ms - t0) / 1000.0

    source = col_str("source", "unknown")
    if log_format == "ground_station" and np.all(source == "unknown"):
        source = np.array(["ground_station"] * len(rows), dtype=object)

    return TelemetryLog(
        path=csv_path,
        format=log_format,
        sample_count=len(rows),
        duration_s=float(t_sec[-1]) if len(t_sec) else 0.0,
        t_sec=t_sec,
        source=source,
        source_mask=col_float("source_mask").astype(np.uint8),
        gps_updates=col_float("gps_updates").astype(np.uint64),
        imu_frames=col_float("imu_frames").astype(np.uint64),
        imu_frame_type=col_str("imu_frame_type", ""),
        latitude=col_float("latitude"),
        longitude=col_float("longitude"),
        altitude=col_float("altitude"),
        speed=col_float("speed"),
        vel_n=col_float("vel_n"),
        vel_e=col_float("vel_e"),
        vel_d=col_float("vel_d"),
        climb_rate=col_float("climb_rate"),
        roll=col_float("roll"),
        pitch=col_float("pitch"),
        yaw=col_float("yaw"),
        temperature=col_float("temperature"),
        accel_x=col_float("accel_x"),
        accel_y=col_float("accel_y"),
        accel_z=col_float("accel_z"),
        gyro_x=col_float("gyro_x"),
        gyro_y=col_float("gyro_y"),
        gyro_z=col_float("gyro_z"),
        mag_x=col_float("mag_x"),
        mag_y=col_float("mag_y"),
        mag_z=col_float("mag_z"),
        gps_valid=col_float("gps_valid") > 0.5,
    )


@dataclass(frozen=True, slots=True)
class ImuFidelityReport:
    row_count: int
    imu_row_count: int
    delta_one_pct: float
    delta_gt_one_pct: float
    max_delta: int
    summary: str


def analyze_imu_fidelity(log: TelemetryLog | str | Path) -> ImuFidelityReport:
    """
    Inspect imu_frames step between CSV rows.

    delta=1 on most rows means one onboard row per IMU UART frame (good).
    Frequent delta>1 means frames were collapsed or dropped before logging.
    """
    if not isinstance(log, TelemetryLog):
        log = load_telemetry_csv(log)

    if log.sample_count < 2:
        return ImuFidelityReport(
            row_count=log.sample_count,
            imu_row_count=0,
            delta_one_pct=0.0,
            delta_gt_one_pct=0.0,
            max_delta=0,
            summary="Too few rows for IMU fidelity analysis",
        )

    if log.format == "ground_station":
        return ImuFidelityReport(
            row_count=log.sample_count,
            imu_row_count=log.sample_count,
            delta_one_pct=0.0,
            delta_gt_one_pct=0.0,
            max_delta=0,
            summary="Ground-station snapshot log (not per-frame avionics format)",
        )

    sources = np.char.lower(log.source.astype(str))
    imu_row_count = int(np.sum(np.char.find(sources, "imu") >= 0))

    delta = np.diff(log.imu_frames.astype(np.int64))
    positive = delta[delta > 0]

    if positive.size == 0:
        return ImuFidelityReport(
            row_count=log.sample_count,
            imu_row_count=imu_row_count,
            delta_one_pct=0.0,
            delta_gt_one_pct=0.0,
            max_delta=0,
            summary="imu_frames never advanced — check log format or recording",
        )

    delta_one_pct = float(np.mean(positive == 1) * 100.0)
    delta_gt_one_pct = float(np.mean(positive > 1) * 100.0)
    max_delta = int(np.max(positive))

    if delta_one_pct >= 95.0:
        verdict = "IMU fidelity good (Δimu_frames≈1)"
    elif delta_one_pct >= 80.0:
        verdict = "IMU mostly preserved — some frame skips"
    else:
        verdict = "IMU frames being skipped — check flash write load"

    summary = (
        f"{verdict} · Δ=1 on {delta_one_pct:.0f}% of steps · "
        f"Δ>1 on {delta_gt_one_pct:.0f}% · max Δ={max_delta} · "
        f"{imu_row_count} imu rows / {log.sample_count} total"
    )

    return ImuFidelityReport(
        row_count=log.sample_count,
        imu_row_count=imu_row_count,
        delta_one_pct=delta_one_pct,
        delta_gt_one_pct=delta_gt_one_pct,
        max_delta=max_delta,
        summary=summary,
    )
