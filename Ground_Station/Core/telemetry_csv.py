"""Load telemetry CSV logs written by CsvTelemetryLogger."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from config import RECEIVED_DATA_DIR


@dataclass(frozen=True, slots=True)
class TelemetryLog:
    path: Path
    sample_count: int
    duration_s: float
    t_sec: np.ndarray
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
    accel_x: np.ndarray
    accel_y: np.ndarray
    accel_z: np.ndarray
    gps_valid: np.ndarray

    @property
    def accel_mag(self) -> np.ndarray:
        return np.sqrt(self.accel_x ** 2 + self.accel_y ** 2 + self.accel_z ** 2)

    @property
    def vel_horiz(self) -> np.ndarray:
        return np.sqrt(self.vel_n ** 2 + self.vel_e ** 2)

    def local_enu_m(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """East / north / up (m) relative to first valid GPS fix."""
        valid = self.gps_valid & (np.abs(self.latitude) > 1e-6) & (np.abs(self.longitude) > 1e-6)
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

    def gps_track_enu_msl(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Easting, northing [m] and altitude MSL [m] for valid GPS samples."""
        valid = self.gps_valid & (np.abs(self.latitude) > 1e-6) & (np.abs(self.longitude) > 1e-6)
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


def load_telemetry_csv(path: str | Path) -> TelemetryLog:
    csv_path = Path(path)
    rows: list[dict[str, str]] = []
    with csv_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            rows.append(row)

    if not rows:
        raise ValueError(f"No rows in {csv_path}")

    def col(name: str, default: float = 0.0) -> np.ndarray:
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

    uptime_ms = col("uptime_ms")
    t0 = uptime_ms[0]
    t_sec = (uptime_ms - t0) / 1000.0

    gps_valid = col("gps_valid") > 0.5

    return TelemetryLog(
        path=csv_path,
        sample_count=len(rows),
        duration_s=float(t_sec[-1]) if len(t_sec) else 0.0,
        t_sec=t_sec,
        latitude=col("latitude"),
        longitude=col("longitude"),
        altitude=col("altitude"),
        speed=col("speed"),
        vel_n=col("vel_n"),
        vel_e=col("vel_e"),
        vel_d=col("vel_d"),
        climb_rate=col("climb_rate"),
        roll=col("roll"),
        pitch=col("pitch"),
        yaw=col("yaw"),
        accel_x=col("accel_x"),
        accel_y=col("accel_y"),
        accel_z=col("accel_z"),
        gps_valid=gps_valid,
    )
