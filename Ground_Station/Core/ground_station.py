"""
Blivit Ground Station — background serial reader + thread-safe telemetry store.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Callable, Optional

import serial
from serial.tools import list_ports

from config import (
    AVIONICS_MAIN_CPP,
    DEBUG_BAUD,
    DEBUG_SERIAL_PORT,
    RFD900_BAUD,
    RFD900_SERIAL_PORT,
    SERIAL_OPEN_RETRIES,
    SERIAL_OPEN_RETRY_DELAY_S,
    SERIAL_OPEN_INITIAL_DELAY_S,
    TELEMETRY_INTERVAL_MS,
    resolve_debug_mode,
)
from rfd900_receiver import handle_incoming_line
from serial_receiver import SerialDebugParser
from telemetry import TelemetrySnapshot, TelemetryStore, run_consumer
from telemetry_log import CsvTelemetryLogger, make_log_filepath


class GroundStation:
    def __init__(self, debug_mode: bool | None = None) -> None:
        self._debug_mode = resolve_debug_mode() if debug_mode is None else debug_mode
        self._serial: serial.Serial | None = None
        self._port = ""
        self._baud = 0
        self._quiet = False
        self._boot_logger: Optional[Callable[[str], None]] = None
        self._debug_parser = SerialDebugParser(on_boot_line=self._on_boot_line)
        self.telemetry = TelemetryStore()
        self._stop = threading.Event()
        self._reader_thread: threading.Thread | None = None
        self._consumer_threads: list[threading.Thread] = []
        self._last_printed_seq = 0
        self._csv_logger: CsvTelemetryLogger | None = None
        self._csv_stop: threading.Event | None = None
        self._csv_thread: threading.Thread | None = None
        self._csv_path: Path | None = None

    @property
    def debug_mode(self) -> bool:
        return self._debug_mode

    @property
    def port(self) -> str:
        return self._port

    @property
    def baud(self) -> int:
        return self._baud

    @property
    def csv_log_path(self) -> Path | None:
        return self._csv_path

    def is_csv_logging(self) -> bool:
        return self._csv_logger is not None

    def set_boot_logger(self, handler: Callable[[str], None]) -> None:
        self._boot_logger = handler

    def init(self, *, quiet: bool = False) -> None:
        self._quiet = quiet
        mode = "debug (USB serial)" if self._debug_mode else "field (RFD900 radio)"

        if self._debug_mode:
            self._port = DEBUG_SERIAL_PORT
            self._baud = DEBUG_BAUD
        else:
            self._port = RFD900_SERIAL_PORT
            self._baud = RFD900_BAUD

        if not self._quiet:
            print("Blivit Ground Station")
            print(f"  mode: {mode}")
            print(f"  avionics main.cpp: {AVIONICS_MAIN_CPP}")
            print(f"  avionics debug_mode: {self._debug_mode}")
            print()
            print(f"Opening {self._port} @ {self._baud} baud...")

        try:
            self._serial = self._open_serial_with_retry(self._port, self._baud)
        except serial.SerialException as exc:
            self._serial = None
            raise OSError(
                f"Cannot open {self._port}: {exc}. "
                "Close PlatformIO serial monitor or other apps using this port."
            ) from exc

        self._stop.clear()
        self._reader_thread = threading.Thread(
            target=self._reader_loop,
            name="blivit-serial-reader",
            daemon=True,
        )
        self._reader_thread.start()

        if not self._quiet:
            print("Listening for telemetry. Ctrl+C to stop.\n")
        elif self._boot_logger:
            self._boot_logger(f"Opened {self._port} @ {self._baud} ({mode})")

    def _open_serial_with_retry(self, port: str, baud: int) -> serial.Serial:
        time.sleep(SERIAL_OPEN_INITIAL_DELAY_S)

        last_exc: serial.SerialException | None = None
        for attempt in range(1, SERIAL_OPEN_RETRIES + 1):
            try:
                ser = serial.Serial(
                    port,
                    baud,
                    timeout=0.1,
                    dsrdtr=False,
                    rtscts=False,
                )
                # Avoid toggling DTR on open — can reset ESP32 mid-connect on first launch
                ser.dtr = False
                ser.rts = False
                ser.reset_input_buffer()
                ser.reset_output_buffer()
                time.sleep(0.15)
                return ser
            except serial.SerialException as exc:
                last_exc = exc
                if attempt >= SERIAL_OPEN_RETRIES:
                    break
                if self._boot_logger is not None:
                    self._boot_logger(
                        f"[GS] Port busy, retry {attempt}/{SERIAL_OPEN_RETRIES - 1}..."
                    )
                time.sleep(SERIAL_OPEN_RETRY_DELAY_S)
        assert last_exc is not None
        raise last_exc

    def add_consumer(
        self,
        handler,
        *,
        name: str = "blivit-consumer",
        stop_event: threading.Event | None = None,
    ) -> threading.Thread:
        """Register a background consumer (e.g. CSV logger, plot updater)."""
        event = stop_event or self._stop
        thread = threading.Thread(
            target=run_consumer,
            kwargs={
                "store": self.telemetry,
                "handler": handler,
                "stop_event": event,
            },
            name=name,
            daemon=True,
        )
        thread.start()
        self._consumer_threads.append(thread)
        return thread

    def start_csv_logging(self, path: str | Path | None = None) -> Path:
        if self.is_csv_logging():
            return self._csv_path  # type: ignore[return-value]

        log_path = Path(path) if path else make_log_filepath()
        self._csv_logger = CsvTelemetryLogger(log_path)
        self._csv_logger.open()
        self._csv_path = log_path
        self._csv_stop = threading.Event()
        self._csv_thread = self.add_consumer(
            self._csv_logger,
            name="blivit-csv-logger",
            stop_event=self._csv_stop,
        )
        return log_path

    def stop_csv_logging(self) -> Path | None:
        if not self.is_csv_logging():
            return None

        assert self._csv_stop is not None
        self._csv_stop.set()
        if self._csv_thread is not None:
            self._csv_thread.join(timeout=1.0)
            if self._csv_thread in self._consumer_threads:
                self._consumer_threads.remove(self._csv_thread)
            self._csv_thread = None

        path = self._csv_path
        if self._csv_logger is not None:
            self._csv_logger.close()
        self._csv_logger = None
        self._csv_stop = None
        self._csv_path = None
        return path

    def run(self, *, print_telemetry: bool = True) -> None:
        if self._serial is None:
            raise RuntimeError("GroundStation.init() must be called first")

        try:
            while not self._stop.is_set():
                if print_telemetry:
                    self._print_latest_telemetry()
                self.telemetry.wait_for_update(after_seq=self._last_printed_seq, timeout=TELEMETRY_INTERVAL_MS / 1000.0)
        except KeyboardInterrupt:
            if not self._quiet:
                print("\nGround station stopped.")
        finally:
            self.close()

    def _print_latest_telemetry(self) -> None:
        state = self.telemetry.copy_state()
        if state.latest is None or state.seq == self._last_printed_seq:
            return
        self._last_printed_seq = state.seq
        print(f"[TELEM] gps {state.latest.format_gps_line()}")
        print(f"[TELEM] imu {state.latest.format_imu_line()}")

    def _reader_loop(self) -> None:
        while not self._stop.is_set():
            try:
                self._poll()
            except serial.SerialException as exc:
                message = f"[GS] serial read error: {exc}"
                if self._boot_logger is not None:
                    self._boot_logger(message)
                elif not self._quiet:
                    print(message)
                break

    def _poll(self) -> None:
        assert self._serial is not None
        raw = self._serial.readline()
        if not raw:
            return

        try:
            line = raw.decode("utf-8", errors="replace")
        except UnicodeDecodeError:
            return

        if self._debug_mode:
            self._handle_debug_line(line)
        else:
            self._handle_radio_line(line)

    def _handle_debug_line(self, line: str) -> None:
        telemetry = self._debug_parser.feed_line(line)
        if telemetry is not None:
            self.telemetry.publish(TelemetrySnapshot.from_debug(telemetry))

    def _handle_radio_line(self, line: str) -> None:
        result = handle_incoming_line(line)
        if result is None:
            return

        reply, packet = result
        if reply and self._serial is not None:
            self._serial.write(reply.encode("ascii"))

        if packet is not None:
            self.telemetry.publish(TelemetrySnapshot.from_heartbeat(packet))

    def _on_boot_line(self, line: str) -> None:
        message = f"[GS] {line}"
        if self._boot_logger is not None:
            self._boot_logger(message)
        elif not self._quiet:
            print(message)

    def close(self) -> None:
        self.stop_csv_logging()
        self._stop.set()
        if self._reader_thread is not None:
            self._reader_thread.join(timeout=1.0)
            self._reader_thread = None
        for thread in self._consumer_threads:
            thread.join(timeout=1.0)
        self._consumer_threads.clear()
        if self._serial is not None and self._serial.is_open:
            self._serial.close()


def list_serial_ports() -> None:
    ports = list_ports.comports()
    if not ports:
        print("No serial ports found.")
        return
    for port in ports:
        print(f"  {port.device} — {port.description}")


def ground_station_init() -> GroundStation:
    station = GroundStation()
    station.init()
    return station


def ground_station_run(station: GroundStation) -> None:
    station.run()
