"""
Ground station runtime configuration.

DEBUG_MODE is read from Avionics/Core/Src/main.cpp by default.
Set DEBUG_MODE_OVERRIDE to True/False to force a mode without editing firmware.
"""

from __future__ import annotations

import os
import re
from typing import Optional

# Debug mode — avionics USB serial (same format as PlatformIO monitor @ 115200)
DEBUG_SERIAL_PORT = "COM6"  # ESP32 USB COM port on your PC
DEBUG_BAUD = 115200

# Field mode — ground-side RFD900 modem (matches avionics RFD900 @ 57600)
RFD900_SERIAL_PORT = "COM7"
RFD900_BAUD = 57600

# Telemetry cadence — keep in sync with Avionics/Core/Inc/heartbeat.h
# TELEMETRY_OUTPUT_INTERVAL_MS = 30 ms (~33 Hz) on RFD900 @ 57600 (binary ~160 B/frame)
# USB debug @ 115200: one combined [DEBUG] line @ 33 Hz (~9 KB/s) fits; two lines saturated link.
# Set debug_binary_telemetry=true in avionics main.cpp to send TELEMETRY hex on USB (RFD sim).
TELEMETRY_INTERVAL_MS = 30
TELEMETRY_STALE_MS = 120  # ~4 missed packets before STALE
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


def resolve_debug_mode() -> bool:
    if DEBUG_MODE_OVERRIDE is not None:
        return DEBUG_MODE_OVERRIDE
    return read_debug_mode()
