"""
Heartbeat packet — matches Avionics/Core/Inc/heartbeat.h (HeartbeatPacket_t, 84 bytes).
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Optional

HEARTBEAT_PACKET_SIZE = 84
HEARTBEAT_STRUCT = struct.Struct("<HIBBBB18fH")


@dataclass
class HeartbeatPacket:
    sequence: int
    uptime_ms: int
    system_state: int
    gps_fix: int
    gps_satellites: int
    reserved: int
    latitude: float
    longitude: float
    altitude: float
    speed: float
    course: float
    accel_x: float
    accel_y: float
    accel_z: float
    gyro_x: float
    gyro_y: float
    gyro_z: float
    mag_x: float
    mag_y: float
    mag_z: float
    roll: float
    pitch: float
    yaw: float
    temperature: float
    crc: int

    @property
    def system_state_label(self) -> str:
        return "debug" if self.system_state == 1 else "field"


def calculate_crc(data: bytes) -> int:
    """Modbus CRC16 (poly 0xA001) — same as avionics Heartbeat_CalculateCRC."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc & 0xFFFF


def decode_packet(raw: bytes) -> Optional[HeartbeatPacket]:
    if len(raw) != HEARTBEAT_PACKET_SIZE:
        return None

    fields = HEARTBEAT_STRUCT.unpack(raw)
    stored_crc = fields[-1]
    payload = raw[: HEARTBEAT_PACKET_SIZE - 2]
    if calculate_crc(payload) != stored_crc:
        return None

    return HeartbeatPacket(
        sequence=fields[0],
        uptime_ms=fields[1],
        system_state=fields[2],
        gps_fix=fields[3],
        gps_satellites=fields[4],
        reserved=fields[5],
        latitude=fields[6],
        longitude=fields[7],
        altitude=fields[8],
        speed=fields[9],
        course=fields[10],
        accel_x=fields[11],
        accel_y=fields[12],
        accel_z=fields[13],
        gyro_x=fields[14],
        gyro_y=fields[15],
        gyro_z=fields[16],
        mag_x=fields[17],
        mag_y=fields[18],
        mag_z=fields[19],
        roll=fields[20],
        pitch=fields[21],
        yaw=fields[22],
        temperature=fields[23],
        crc=stored_crc,
    )


def decode_hex_payload(hex_text: str) -> Optional[HeartbeatPacket]:
    try:
        raw = bytes.fromhex(hex_text.strip())
    except ValueError:
        return None
    return decode_packet(raw)


def format_packet(packet: HeartbeatPacket) -> str:
    return (
        f"seq={packet.sequence} uptime={packet.uptime_ms}ms mode={packet.system_state_label} "
        f"fix={packet.gps_fix} sats={packet.gps_satellites} "
        f"lat={packet.latitude:.6f} lon={packet.longitude:.6f} alt={packet.altitude:.1f} "
        f"spd={packet.speed:.1f} crs={packet.course:.1f} "
        f"accel=({packet.accel_x:.2f},{packet.accel_y:.2f},{packet.accel_z:.2f}) "
        f"gyro=({packet.gyro_x:.1f},{packet.gyro_y:.1f},{packet.gyro_z:.1f}) "
        f"mag=({packet.mag_x:.1f},{packet.mag_y:.1f},{packet.mag_z:.1f}) "
        f"crc=0x{packet.crc:04X}"
    )
