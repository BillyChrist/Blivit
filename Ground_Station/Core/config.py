"""
Ground station runtime configuration.

DEBUG_MODE is read from Avionics/Core/Src/main.cpp by default.
Set DEBUG_MODE_OVERRIDE to True/False to force a mode without editing firmware.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Optional

# Debug mode — avionics USB serial (same format as PlatformIO monitor @ 115200)
DEBUG_SERIAL_PORT = "COM5"  # ESP32 USB COM port on your PC
DEBUG_BAUD = 115200

# Field mode — ground-side RFD900 modem (matches avionics RFD900 @ 57600)
RFD900_SERIAL_PORT = "COM6"
RFD900_BAUD = 57600

# Telemetry cadence — keep in sync with Avionics/Core/Inc/heartbeat.h
# TELEMETRY_OUTPUT_INTERVAL_MS = 30 ms: sensor sample, onboard CSV, USB debug (~33 Hz)
# RFD900_TELEMETRY_INTERVAL_MS = 100 ms: field radio only (~10 Hz, ~1.9 KB/s on wire)
#   Wire frame is fixed ~190 B (84 B binary → 168 hex + TELEMETRY,seq,crc,\\r\\n overhead).
#   30 ms on RFD would be ~6.3 KB/s — exceeds 57600 (~5.8 KB/s usable).
TELEMETRY_INTERVAL_MS = 30
RFD900_TELEMETRY_INTERVAL_MS = 100
TELEMETRY_STALE_MS = 450  # ~4–5 missed RFD frames before STALE
# USB serial on Windows can deliver lines in driver-sized bursts; use a looser
# threshold in debug so bursty reads are not mistaken for a dead link.
DEBUG_TELEMETRY_STALE_MS = 3000
GUI_REFRESH_MS = 33
STATUS_LOG_INTERVAL_MS = 5000

# Serial open — Windows can briefly hold COM ports after monitor disconnect
SERIAL_OPEN_RETRIES = 6
SERIAL_OPEN_RETRY_DELAY_S = 0.5
SERIAL_OPEN_INITIAL_DELAY_S = 0.75

# Reopen serial when link is stale, reader stopped, or port dropped (USB unplug/replug)
SERIAL_STALE_RECONNECT_MS = 2000
SERIAL_RECONNECT_COOLDOWN_S = 3.0
SERIAL_RECONNECT_POLL_MS = 3000

# Telemetry store — ring buffer for plots; bounded queue for async consumers
TELEMETRY_HISTORY_SIZE = 1000
TELEMETRY_QUEUE_SIZE = 256

_GROUND_STATION_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RECEIVED_DATA_DIR = os.path.join(_GROUND_STATION_ROOT, "received_data")
GROUND_STATION_SETTINGS_PATH = os.path.join(_GROUND_STATION_ROOT, "settings.json")
DEFAULT_BAUD_RATES = [57600, 115200, 9600, 19200, 38400]

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
AVIONICS_MAIN_CPP = os.path.join(_REPO_ROOT, "Avionics", "Core", "Src", "main.cpp")

_DEBUG_MODE_PATTERN = re.compile(
    r"bool\s+debug_mode\s*=\s*(true|false)\s*;",
    re.IGNORECASE,
)

# None = auto-detect from avionics main.cpp; True/False = manual override
DEBUG_MODE_OVERRIDE: Optional[bool] = None

def read_debug_mode(path: Optional[str] = None) -> bool:
    """
    Parse `bool debug_mode = true/false;` from avionics main.cpp.
    Returns True for bench debug (USB serial), False for field (RFD900).
    """
    main_cpp = path or AVIONICS_MAIN_CPP
    with open(main_cpp, encoding="utf-8") as handle:
        source = handle.read()

    match = _DEBUG_MODE_PATTERN.search(source)
    if match is None:
        raise ValueError(
            f"Could not find debug_mode assignment in {main_cpp}"
        )

    return match.group(1).lower() == "true"


def default_serial_settings(debug_mode: bool) -> tuple[str, int]:
    return (DEBUG_SERIAL_PORT, DEBUG_BAUD) if debug_mode else (RFD900_SERIAL_PORT, RFD900_BAUD)


def load_gui_settings() -> dict[str, str | int]:
    try:
        with open(GROUND_STATION_SETTINGS_PATH, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {}

    if not isinstance(data, dict):
        return {}

    settings: dict[str, str | int] = {}
    port = data.get("port")
    baud = data.get("baud")
    if isinstance(port, str):
        settings["port"] = port
    if isinstance(baud, int):
        settings["baud"] = baud
    return settings


def save_gui_settings(port: str, baud: int) -> None:
    Path(GROUND_STATION_SETTINGS_PATH).parent.mkdir(parents=True, exist_ok=True)
    with open(GROUND_STATION_SETTINGS_PATH, "w", encoding="utf-8") as handle:
        json.dump({"port": port, "baud": baud}, handle, indent=2)


def resolve_debug_mode() -> bool:
    if DEBUG_MODE_OVERRIDE is not None:
        return DEBUG_MODE_OVERRIDE
    return read_debug_mode()
