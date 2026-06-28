"""Ground-station client for avionics onboard CSV log commands and download."""

from __future__ import annotations

import re
import threading
import time
from typing import Callable, Optional

_ACK_PREFIX = "Blivit,LOG,ACK,"
_ERR_PREFIX = "Blivit,LOG,ERR,"


def format_avionics_log_console_line(line: str) -> Optional[str]:
    """Map avionics LOG protocol lines to user-facing console text."""
    if line.startswith(_ACK_PREFIX):
        return line[len(_ACK_PREFIX) :]

    if line.startswith("Blivit,LOG,OK,START"):
        return None

    if line.startswith("Blivit,LOG,OK,STOP"):
        return None

    if line.startswith("Blivit,LOG,OK,DL"):
        parts = line.split(",")
        if len(parts) >= 4:
            try:
                nbytes = int(parts[3])
                return f"ESP32 acknowledged download — receiving {nbytes / 1024.0:.1f} KB…"
            except ValueError:
                pass
        return "ESP32 acknowledged download — receiving file…"

    if line.startswith("Blivit,LOG,STAT,"):
        recording = "recording=1" in line
        rows_match = re.search(r"rows=(\d+)", line)
        bytes_match = re.search(r"bytes=(\d+)", line)
        rows = rows_match.group(1) if rows_match else "0"
        nbytes = int(bytes_match.group(1)) if bytes_match else 0
        state = "recording" if recording else "idle"
        if nbytes > 0:
            return f"Onboard log {state} — {rows} rows, {nbytes / 1024.0:.1f} KB on device"
        return f"Onboard log {state}"

    if line.startswith("Blivit,LOG,END,"):
        match = re.search(r"Blivit,LOG,END,(\d+)", line) or re.search(r"Blivit,LOG,END,(\d+)", line)
        parts = line.split(",")
        if len(parts) >= 3:
            try:
                nbytes = int(parts[2])
                return f"ESP32 finished sending log file ({nbytes / 1024.0:.1f} KB)"
            except ValueError:
                pass
        return "ESP32 finished sending log file"

    if line.startswith(_ERR_PREFIX):
        code = line[len(_ERR_PREFIX) :].split(",", 1)[0]
        details = {
            "START": "could not start onboard recording",
            "STOP": "could not stop onboard recording",
            "DL": "download refused (no file, still recording, or storage error)",
            "CLEAR": "could not clear onboard log (recording, downloading, or storage error)",
            "UNKNOWN": "unrecognized log command",
        }
        return f"ESP32 log error: {details.get(code, line[len(_ERR_PREFIX) :])}"

    return None


def format_firmware_console_line(line: str) -> Optional[str]:
    """Translate ESP32 boot/status serial lines for the GUI console."""
    text = line.strip()
    if not text:
        return None

    if text.startswith("[LOG]"):
        if "recording @ sensor-loop" in text or "recording started" in text.lower():
            return "ESP32: onboard high-rate CSV recording started"
        if "recording stopped" in text:
            match_rows = re.search(r"rows=(\d+)", text)
            match_bytes = re.search(r"bytes=(\d+)", text)
            if match_rows and match_bytes:
                kb = int(match_bytes.group(1)) / 1024.0
                return (
                    f"ESP32: onboard recording stopped — "
                    f"{match_rows.group(1)} rows, {kb:.1f} KB stored on device"
                )
            return "ESP32: onboard recording stopped"
        if "LittleFS ready" in text:
            return "ESP32: flash storage ready for onboard logs"
        if "LittleFS mount failed" in text:
            return "ESP32: flash storage unavailable — onboard logging disabled"
        if "failed to create" in text:
            return "ESP32: could not create onboard log file"
        if "file size limit" in text:
            return "ESP32: onboard log file size limit reached — recording stopped"
        if "flight data cleared" in text:
            return "Onboard flight data cleared from flash"

    if text.startswith("[MODE]"):
        if "debug" in text.lower():
            return "ESP32 mode: debug (USB serial telemetry)"
        return "ESP32 mode: field (RFD900 radio telemetry)"

    if text.startswith("Blivit avionics boot"):
        return "ESP32 booting…"

    if text.startswith("Blivit dual-core tasks started"):
        return "ESP32 sensors and comms tasks running"

    if text.startswith("[TASK]") or text.startswith("[ERR]") or text.startswith("[WARN]"):
        return text

    if text.startswith("[RFD900]") or text.startswith("[GPS]") or text.startswith("[IMU]"):
        return None

    if text.startswith("[") and not text.startswith("[DEBUG]") and not text.startswith("[HB]"):
        return text

    return None


class AvionicsLogDownloadSession:
    """Collects hex chunks from Blivit,LOG,DATA lines until Blivit,LOG,END."""

    def __init__(
        self,
        *,
        on_progress: Callable[[int, Optional[int]], None] | None = None,
        on_started: Callable[[], None] | None = None,
    ) -> None:
        self._buffer = bytearray()
        self._done = threading.Event()
        self._error: Optional[str] = None
        self._expected_size: Optional[int] = None
        self._on_progress = on_progress
        self._on_started = on_started
        self._download_acknowledged = False
        self._ack_time: float | None = None
        self._started_notified = False

    def _notify_started(self) -> None:
        if self._started_notified or self._on_started is None:
            return
        self._started_notified = True
        self._on_started()

    def _notify_progress(self) -> None:
        if self._on_progress is not None:
            self._on_progress(len(self._buffer), self._expected_size)

    def feed_line(self, line: str) -> None:
        if line.startswith("Blivit,LOG,OK,DL"):
            parts = line.split(",")
            if len(parts) >= 4:
                try:
                    self._expected_size = int(parts[3])
                except ValueError:
                    pass
            self._download_acknowledged = True
            self._ack_time = time.monotonic()
            self._notify_started()
            return

        if line.startswith(_ACK_PREFIX) and "Download accepted" in line:
            self._download_acknowledged = True
            self._ack_time = time.monotonic()
            self._notify_started()
            return

        if line.startswith("Blivit,LOG,DATA,"):
            rest = line[len("Blivit,LOG,DATA,") :]
            _seq, sep, hex_payload = rest.partition(",")
            if not sep or not hex_payload:
                return
            try:
                self._buffer.extend(bytes.fromhex(hex_payload))
            except ValueError:
                self._error = "Invalid data in download stream"
                self._done.set()
                return
            if self._on_progress is not None:
                self._notify_progress()
            return

        if line.startswith("Blivit,LOG,END,"):
            parts = line.split(",")
            if len(parts) >= 3:
                try:
                    self._expected_size = int(parts[2])
                except ValueError:
                    self._expected_size = None
            self._done.set()
            return

        if line.startswith(_ERR_PREFIX):
            self._error = line
            self._done.set()

    def wait(
        self,
        timeout_s: float = 120.0,
        *,
        idle_timeout_s: float = 20.0,
    ) -> bytes:
        started = time.monotonic()
        while not self._done.is_set():
            now = time.monotonic()
            if now - started > timeout_s:
                raise TimeoutError("Timed out waiting for ESP32 log download")
            if not self._download_acknowledged and now - started > idle_timeout_s:
                raise TimeoutError(
                    "ESP32 did not acknowledge download (check serial link and firmware reflash)"
                )
            if (
                self._ack_time is not None
                and not self._buffer
                and now - self._ack_time > idle_timeout_s
            ):
                raise TimeoutError("ESP32 acknowledged download but sent no data")
            if not self._done.wait(0.5):
                continue
            break

        if self._error:
            friendly = format_avionics_log_console_line(self._error)
            raise RuntimeError(friendly or self._error)
        data = bytes(self._buffer)
        if self._expected_size is not None and len(data) != self._expected_size:
            raise RuntimeError(
                f"Download size mismatch: received {len(data)} bytes, expected {self._expected_size}"
            )
        if not data:
            raise RuntimeError("Download finished but no data was received")
        return data

    @property
    def bytes_received(self) -> int:
        return len(self._buffer)
