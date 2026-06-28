"""
Ground-side RFD900 receiver — parses TELEMETRY frames from avionics field mode.
"""

from __future__ import annotations

from typing import Optional, Tuple

from heartbeat import HeartbeatPacket, decode_hex_payload, format_packet


def parse_telemetry_line(line: str) -> Optional[Tuple[int, HeartbeatPacket, int]]:
    """
    Parse: TELEMETRY,<seq>,<hex_payload>,<crc>
    Returns (sequence, packet, crc_from_frame) or None.
    """
    line = line.strip()
    if not line.startswith("TELEMETRY,"):
        return None

    parts = line.split(",")
    if len(parts) < 4:
        return None

    try:
        sequence = int(parts[1])
        frame_crc = int(parts[-1], 16)
    except ValueError:
        return None

    hex_payload = ",".join(parts[2:-1])
    packet = decode_hex_payload(hex_payload)
    if packet is None:
        return None

    return sequence, packet, frame_crc


def build_ack(sequence: int) -> str:
    return f"ACK,{sequence}\r\n"


def build_ready() -> str:
    return "Blivit,READY\r\n"


def handle_incoming_line(line: str) -> Optional[Tuple[str, Optional[HeartbeatPacket]]]:
    """
    Process one received line.
    Returns (optional_reply, decoded_packet).
    """
    line = line.strip()
    if not line:
        return None

    if line.startswith("Blivit,HELLO,") or line == "PING":
        if line == "PING":
            return "ACK\r\n", None
        return build_ready(), None

    parsed = parse_telemetry_line(line)
    if parsed is None:
        return None

    sequence, packet, frame_crc = parsed
    if packet.crc != frame_crc:
        print(f"[GS] CRC mismatch frame=0x{frame_crc:04X} packet=0x{packet.crc:04X}")
        return build_ack(sequence), None

    return build_ack(sequence), packet
