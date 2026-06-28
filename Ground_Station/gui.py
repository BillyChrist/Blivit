#!/usr/bin/env python3
"""
Blivit Ground Station — GUI entry point.

Usage:
  python gui.py              Launch GUI (mode from Avionics/Core/Src/main.cpp)
  python gui.py --debug      Force USB serial mode
  python gui.py --field      Force RFD900 radio mode
  python gui.py --log FILE   Log telemetry to CSV while GUI runs
"""

from __future__ import annotations

import argparse
import faulthandler
import os
import sys

CORE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Core")
sys.path.insert(0, CORE_DIR)

from config import AVIONICS_MAIN_CPP, read_debug_mode  # noqa: E402
from ground_station import GroundStation  # noqa: E402
from gui.main_window import run_gui  # noqa: E402


def main() -> int:
    faulthandler.enable()

    parser = argparse.ArgumentParser(description="Blivit Ground Station GUI")
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
    return run_gui(station, log_path=args.log)


if __name__ == "__main__":
    raise SystemExit(main())
