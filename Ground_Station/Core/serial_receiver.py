"""
Parse avionics USB serial debug lines ([DEBUG] / [HB] / TELEMETRY binary on USB).
Used when debug_mode is True on both avionics and ground station.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Optional

GRAVITY_MS2 = 9.80665

# Single-line atomic sample (GPS + IMU) — preferred; fits 115200 @ 33 Hz
DEBUG_COMBINED_LINE = re.compile(
    r"^\[DEBUG\] t=(?P<uptime>\d+)ms seq=(?P<seq>\d+) "
    r"(?:gps_ready=(?P<gps_ready>\d+) )?gps valid=(?P<valid>\d+) sats=(?P<sats>\d+) hdop=(?P<hdop>[\d.]+) "
    r"lat=(?P<lat>[-\d.]+) lon=(?P<lon>[-\d.]+) alt=(?P<alt>[-\d.]+) "
    r"spd=(?P<spd>[-\d.]+) crs=(?P<crs>[-\d.]+) "
    r"(?:vn=(?P<vn>[-\d.]+) ve=(?P<ve>[-\d.]+) vd=(?P<vd>[-\d.]+) climb=(?P<climb>[-\d.]+) )?"
    r"utc=(?P<utc>\S+) date=(?P<utc_date>\S+) "
    r"imu (?:frames=(?P<frames>\d+) )?(?:bytes=(?P<bytes>\d+) )?"
    r"r=(?P<roll>[-\d.]+) p=(?P<pitch>[-\d.]+) y=(?P<yaw>[-\d.]+) "
    r"temp=(?P<temp>[-\d.]+) "
    r"(?P<accel_unit>accel_g|accel)=\((?P<ax>[-\d.]+),(?P<ay>[-\d.]+),(?P<az>[-\d.]+)\) "
    r"gyro=\((?P<gx>[-\d.]+),(?P<gy>[-\d.]+),(?P<gz>[-\d.]+)\) "
    r"mag=\((?P<mx>[-\d.]+),(?P<my>[-\d.]+),(?P<mz>[-\d.]+)\)"
)

# Legacy two-line format (GPS line then IMU line)
DEBUG_GPS_LINE = re.compile(
    r"^\[DEBUG\] t=(?P<uptime>\d+)ms seq=(?P<seq>\d+) "
    r"gps valid=(?P<valid>\d+) sats=(?P<sats>\d+) hdop=(?P<hdop>[\d.]+) "
    r"lat=(?P<lat>[-\d.]+) lon=(?P<lon>[-\d.]+) alt=(?P<alt>[-\d.]+) "
    r"spd=(?P<spd>[-\d.]+) crs=(?P<crs>[-\d.]+) "
    r"(?:vn=(?P<vn>[-\d.]+) ve=(?P<ve>[-\d.]+) vd=(?P<vd>[-\d.]+) climb=(?P<climb>[-\d.]+) )?"
    r"utc=(?P<utc>\S+) date=(?P<date>\S+)$"
)

DEBUG_IMU_LINE = re.compile(
    r"^\[DEBUG\] imu (?:frames=(?P<frames>\d+) )?(?:bytes=(?P<bytes>\d+) )?"
    r"r=(?P<roll>[-\d.]+) p=(?P<pitch>[-\d.]+) y=(?P<yaw>[-\d.]+) "
    r"temp=(?P<temp>[-\d.]+) "
    r"(?P<accel_unit>accel_g|accel)=\((?P<ax>[-\d.]+),(?P<ay>[-\d.]+),(?P<az>[-\d.]+)\) "
    r"gyro=\((?P<gx>[-\d.]+),(?P<gy>[-\d.]+),(?P<gz>[-\d.]+)\) "
    r"mag=\((?P<mx>[-\d.]+),(?P<my>[-\d.]+),(?P<mz>[-\d.]+)\)"
)

HB_LINE = re.compile(
    r"^\[HB\] seq=(?P<seq>\d+) uptime=(?P<uptime>\d+)ms size=(?P<size>\d+) "
    r"crc=0x(?P<crc>[0-9A-Fa-f]{4}) valid=(?P<valid>\w+)"
)


@dataclass
class DebugTelemetry:
    uptime_ms: int
    sequence: int
    gps_valid: bool
    gps_satellites: int
    hdop: float
    latitude: float
    longitude: float
    altitude: float
    speed: float
    course: float
    utc: str
    date: str
    vel_n: float = 0.0
    vel_e: float = 0.0
    vel_d: float = 0.0
    climb_rate: float = 0.0
    roll: float = 0.0
    pitch: float = 0.0
    yaw: float = 0.0
    temperature: float = 0.0
    imu_frames: int = 0
    imu_bytes: int = 0
    accel_x: float = 0.0
    accel_y: float = 0.0
    accel_z: float = 0.0
    gyro_x: float = 0.0
    gyro_y: float = 0.0
    gyro_z: float = 0.0
    mag_x: float = 0.0
    mag_y: float = 0.0
    mag_z: float = 0.0


class SerialDebugParser:
    def __init__(
        self,
        on_boot_line: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._pending: Optional[DebugTelemetry] = None
        self._on_boot_line = on_boot_line

    def feed_line(self, line: str) -> Optional[DebugTelemetry]:
        line = line.strip()
        if not line:
            return None

        if line.startswith("ax_g="):
            return None

        combined = DEBUG_COMBINED_LINE.match(line)
        if combined:
            return self._from_combined(combined.groupdict())

        gps_match = DEBUG_GPS_LINE.match(line)
        if gps_match:
            data = gps_match.groupdict()
            self._pending = DebugTelemetry(
                uptime_ms=int(data["uptime"]),
                sequence=int(data["seq"]),
                gps_valid=bool(int(data["valid"])),
                gps_satellites=int(data["sats"]),
                hdop=float(data["hdop"]),
                latitude=float(data["lat"]),
                longitude=float(data["lon"]),
                altitude=float(data["alt"]),
                speed=float(data["spd"]),
                course=float(data["crs"]),
                vel_n=float(data["vn"] or 0.0),
                vel_e=float(data["ve"] or 0.0),
                vel_d=float(data["vd"] or 0.0),
                climb_rate=float(data["climb"] or 0.0),
                utc=data["utc"],
                date=data["date"],
            )
            return None

        imu_match = DEBUG_IMU_LINE.match(line)
        if imu_match and self._pending is not None:
            self._apply_imu(self._pending, imu_match.groupdict())
            complete = self._pending
            self._pending = None
            return complete

        if HB_LINE.match(line) or line.startswith("TELEMETRY,"):
            return None

        if line.startswith("[") and not line.startswith("[DEBUG]") and not line.startswith("[HB]"):
            if self._on_boot_line is not None:
                self._on_boot_line(line)

        return None

    def _from_combined(self, data: dict[str, str]) -> DebugTelemetry:
        sample = DebugTelemetry(
            uptime_ms=int(data["uptime"]),
            sequence=int(data["seq"]),
            gps_valid=bool(int(data["valid"])),
            gps_satellites=int(data["sats"]),
            hdop=float(data["hdop"]),
            latitude=float(data["lat"]),
            longitude=float(data["lon"]),
            altitude=float(data["alt"]),
            speed=float(data["spd"]),
            course=float(data["crs"]),
            vel_n=float(data["vn"] or 0.0),
            vel_e=float(data["ve"] or 0.0),
            vel_d=float(data["vd"] or 0.0),
            climb_rate=float(data["climb"] or 0.0),
            utc=data["utc"],
            date=data["utc_date"],
        )
        self._apply_imu(sample, data)
        return sample

    @staticmethod
    def _apply_imu(target: DebugTelemetry, data: dict[str, str]) -> None:
        target.imu_frames = int(data["frames"] or 0)
        target.imu_bytes = int(data["bytes"] or 0)
        target.roll = float(data["roll"])
        target.pitch = float(data["pitch"])
        target.yaw = float(data["yaw"])
        target.temperature = float(data["temp"])
        ax = float(data["ax"])
        ay = float(data["ay"])
        az = float(data["az"])
        if data["accel_unit"] == "accel_g":
            ax *= GRAVITY_MS2
            ay *= GRAVITY_MS2
            az *= GRAVITY_MS2
        target.accel_x = ax
        target.accel_y = ay
        target.accel_z = az
        target.gyro_x = float(data["gx"])
        target.gyro_y = float(data["gy"])
        target.gyro_z = float(data["gz"])
        target.mag_x = float(data["mx"])
        target.mag_y = float(data["my"])
        target.mag_z = float(data["mz"])

    @staticmethod
    def format_telemetry(data: DebugTelemetry) -> str:
        return (
            f"t={data.uptime_ms}ms seq={data.sequence} "
            f"gps valid={int(data.gps_valid)} sats={data.gps_satellites} hdop={data.hdop:.1f} "
            f"lat={data.latitude:.6f} lon={data.longitude:.6f} alt={data.altitude:.1f} "
            f"imu r={data.roll:.1f} p={data.pitch:.1f} y={data.yaw:.1f} temp={data.temperature:.1f}"
        )
