"""
Optional CSV logger — runs as a TelemetryStore consumer in its own thread.
"""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import TextIO

from config import RECEIVED_DATA_DIR
from telemetry import TelemetrySnapshot


def make_log_filepath(directory: str | Path | None = None) -> Path:
    """Timestamped CSV path under received_data/."""
    base = Path(directory or RECEIVED_DATA_DIR)
    base.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return base / f"telemetry_{stamp}.csv"


class CsvTelemetryLogger:
    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._file: TextIO | None = None
        self._writer: csv.DictWriter | None = None

    @property
    def path(self) -> Path:
        return self._path

    def open(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        new_file = not self._path.exists()
        self._file = self._path.open("a", newline="", encoding="utf-8")
        self._writer = csv.DictWriter(self._file, fieldnames=_CSV_FIELDS)
        if new_file:
            self._writer.writeheader()
            self._file.flush()

    def close(self) -> None:
        if self._file is not None:
            self._file.close()
            self._file = None
            self._writer = None

    def __call__(self, snapshot: TelemetrySnapshot) -> None:
        if self._writer is None or self._file is None:
            return
        self._writer.writerow(_snapshot_to_row(snapshot))
        self._file.flush()


_CSV_FIELDS = [
    "received_at",
    "sequence",
    "uptime_ms",
    "source",
    "gps_valid",
    "gps_satellites",
    "hdop",
    "latitude",
    "longitude",
    "altitude",
    "speed",
    "course",
    "vel_n",
    "vel_e",
    "vel_d",
    "climb_rate",
    "roll",
    "pitch",
    "yaw",
    "temperature",
    "imu_frames",
    "imu_bytes",
    "accel_x",
    "accel_y",
    "accel_z",
    "gyro_x",
    "gyro_y",
    "gyro_z",
    "mag_x",
    "mag_y",
    "mag_z",
    "utc",
    "date",
]


def _snapshot_to_row(snapshot: TelemetrySnapshot) -> dict[str, object]:
    return {field: getattr(snapshot, field) for field in _CSV_FIELDS}
