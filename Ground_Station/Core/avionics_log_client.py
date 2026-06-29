"""Ground-station client for avionics onboard CSV log commands and download."""

from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

_ACK_PREFIX = "Blivit,LOG,ACK,"
_ERR_PREFIX = "Blivit,LOG,ERR,"


@dataclass(frozen=True, slots=True)
class OnboardLogInfo:
    bytes: int
    rows: int = 0


def parse_onboard_log_protocol(line: str) -> Optional[OnboardLogInfo]:
    """Parse machine-readable avionics LOG lines (byte counts for progress %)."""
    if line.startswith("Blivit,LOG,OK,STOP,"):
        parts = line.split(",")
        if len(parts) >= 5:
            try:
                nbytes = int(parts[4])
                rows = int(parts[5]) if len(parts) >= 6 else 0
                return OnboardLogInfo(bytes=nbytes, rows=rows)
            except ValueError:
                return None

    if line.startswith("Blivit,LOG,OK,DL,"):
        parts = line.split(",")
        if len(parts) >= 5:
            try:
                return OnboardLogInfo(bytes=int(parts[4]))
            except ValueError:
                return None

    if line.startswith("Blivit,LOG,STAT,"):
        rows_match = re.search(r"rows=(\d+)", line)
        bytes_match = re.search(r"bytes=(\d+)", line)
        if bytes_match:
            try:
                rows = int(rows_match.group(1)) if rows_match else 0
                return OnboardLogInfo(bytes=int(bytes_match.group(1)), rows=rows)
            except ValueError:
                return None

    if line.startswith("Blivit,LOG,END,"):
        parts = line.split(",")
        if len(parts) >= 4:
            try:
                return OnboardLogInfo(bytes=int(parts[3]))
            except ValueError:
                return None

    return None


def format_download_progress(nbytes: int, total_bytes: Optional[int]) -> str:
    kb = nbytes / 1024.0
    if total_bytes is not None and total_bytes > 0:
        pct = min(100, int(nbytes * 100 / total_bytes))
        return f"Downloading… {kb:.0f} KB received, {pct}% Complete"
    return f"Downloading… {kb:.0f} KB received"


def format_onboard_log_stop(info: OnboardLogInfo) -> str:
    kb = info.bytes / 1024.0
    if info.rows > 0:
        return (
            f"ESP32: onboard recording stopped — "
            f"{info.rows} rows, {kb:.1f} KB stored on device"
        )
    return f"ESP32: onboard recording stopped — {kb:.1f} KB stored on device"


def format_avionics_log_console_line(line: str) -> Optional[str]:
    """Map avionics LOG protocol lines to user-facing console text."""
    if line.startswith(_ACK_PREFIX):
        return line[len(_ACK_PREFIX) :]

    if line.startswith("Blivit,LOG,OK,START"):
        return None

    if line.startswith("Blivit,LOG,OK,STOP"):
        info = parse_onboard_log_protocol(line)
        if info is not None:
            return format_onboard_log_stop(info)
        return None

    if line.startswith("Blivit,LOG,OK,DL"):
        info = parse_onboard_log_protocol(line)
        if info is not None:
            return f"ESP32 acknowledged download — receiving {info.bytes / 1024.0:.1f} KB…"
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
        parts = line.split(",")
        if len(parts) >= 4:
            try:
                nbytes = int(parts[3])
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

    if text.startswith("[GPS]"):
        return text

    if text.startswith("[IMU]"):
        return None

    if text.startswith("[HB]") or text.startswith("TELEMETRY,"):
        return None

    if text.startswith("[") and not text.startswith("[DEBUG]"):
        return text

    return None


class AvionicsLogDownloadSession:
    """Collects hex chunks from Blivit,LOG,DATA lines until Blivit,LOG,END."""

    def __init__(
        self,
        *,
        on_progress: Callable[[int, Optional[int]], None] | None = None,
        on_started: Callable[[], None] | None = None,
        fallback_size: int | None = None,
    ) -> None:
        self._buffer = bytearray()
        self._done = threading.Event()
        self._error: Optional[str] = None
        self._expected_size: Optional[int] = fallback_size if fallback_size else None
        self._fallback_size = fallback_size
        self._on_progress = on_progress
        self._on_started = on_started
        self._download_acknowledged = False
        self._ack_time: float | None = None
        self._started_notified = False
        self._last_progress_bytes = 0
        self._last_progress_time: float | None = None

    def _notify_started(self) -> None:
        if self._started_notified or self._on_started is None:
            return
        self._started_notified = True
        self._on_started()

    def _notify_progress(self) -> None:
        now = time.monotonic()
        if len(self._buffer) != self._last_progress_bytes:
            self._last_progress_bytes = len(self._buffer)
            self._last_progress_time = now
        if self._on_progress is not None:
            total = self._expected_size or self._fallback_size
            self._on_progress(len(self._buffer), total)

    def feed_line(self, line: str) -> None:
        if line.startswith("Blivit,LOG,OK,DL"):
            info = parse_onboard_log_protocol(line)
            if info is not None:
                self._expected_size = info.bytes
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
            self._notify_progress()
            return

        if line.startswith("Blivit,LOG,END,"):
            parts = line.split(",")
            if len(parts) >= 4:
                try:
                    self._expected_size = int(parts[3])
                except ValueError:
                    self._expected_size = None
            elif len(parts) >= 3:
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
        stall_timeout_s: float = 45.0,
    ) -> bytes:
        started = time.monotonic()
        while not self._done.is_set():
            now = time.monotonic()

            effective_timeout = timeout_s
            if self._expected_size is not None and self._expected_size > 0:
                # ~2 KB/s effective over USB with chunk overhead; generous margin
                effective_timeout = max(timeout_s, (self._expected_size / 1800.0) + 90.0)

            if now - started > effective_timeout:
                raise TimeoutError(
                    f"Timed out waiting for ESP32 log download "
                    f"({len(self._buffer) / 1024.0:.0f} KB received"
                    f"{f' of {self._expected_size / 1024.0:.0f} KB expected' if self._expected_size else ''})"
                )
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
            if (
                self._last_progress_time is not None
                and self._buffer
                and now - self._last_progress_time > stall_timeout_s
            ):
                raise TimeoutError(
                    f"Download stalled at {len(self._buffer) / 1024.0:.0f} KB "
                    f"(no new data for {stall_timeout_s:.0f} s)"
                )
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
