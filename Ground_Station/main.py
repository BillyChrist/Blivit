#!/usr/bin/env python3
"""
Blivit Ground Station entry point (console).

Usage:
  python main.py              Console mode (mode from Avionics/Core/Src/main.cpp)
  python gui.py               Avionics-style GUI
  python main.py --debug      Force USB serial mode
  python main.py --field      Force RFD900 radio mode
  python main.py --list-ports List available COM ports
"""

from __future__ import annotations

import argparse
import os
import sys

CORE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Core")
sys.path.insert(0, CORE_DIR)

from config import AVIONICS_MAIN_CPP, read_debug_mode          # noqa: E402
from ground_station import GroundStation, list_serial_ports    # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Blivit Ground Station")
    parser.add_argument(
        "--list-ports",
        action="store_true",
        help="List serial ports and exit",
    )
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--debug",
        action="store_true",
        help="Force debug mode (USB serial @ 115200)",
    )
    mode_group.add_argument(
        "--field",
        action="store_true",
        help="Force field mode (RFD900 @ 57600)",
    )
    parser.add_argument(
        "--log",
        metavar="FILE",
        help="Append telemetry snapshots to CSV (background thread)",
    )
    args = parser.parse_args()

    if args.list_ports:
        list_serial_ports()
        return 0

    debug_mode: bool | None = None
    if args.debug:
        debug_mode = True
    elif args.field:
        debug_mode = False
    else:
        try:
            debug_mode = read_debug_mode()
        except (OSError, ValueError) as exc:
            print(f"Could not read debug_mode from {AVIONICS_MAIN_CPP}: {exc}")
            return 1

    station = GroundStation(debug_mode=debug_mode)

    try:
        station.init()
        if args.log:
            path = station.start_csv_logging(args.log)
            print(f"Logging telemetry to {path}\n")
        station.run()
    finally:
        station.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
