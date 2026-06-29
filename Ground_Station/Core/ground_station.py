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
    SERIAL_RECONNECT_COOLDOWN_S,
    SERIAL_STALE_RECONNECT_MS,
    resolve_debug_mode,
)
from heartbeat import HEARTBEAT_PACKET_SIZE
from link_stats import LinkStats, LinkStatsTracker
from avionics_log_client import (
    AvionicsLogDownloadSession,
    format_avionics_log_console_line,
    format_download_progress,
    format_firmware_console_line,
    parse_onboard_log_protocol,
)
from rfd900_receiver import handle_incoming_line
from serial_receiver import SerialDebugParser
from telemetry import TelemetrySnapshot, TelemetryStore, run_consumer
from telemetry_log import CsvTelemetryLogger, make_avionics_log_filepath, make_log_filepath


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
        self._link_stats = LinkStatsTracker()
        self._avionics_download: AvionicsLogDownloadSession | None = None
        self._avionics_download_lock = threading.Lock()
        self._avionics_log_event: Optional[Callable[[str], None]] = None
        self._serial_fault: Optional[str] = None
        self._onboard_log_bytes: Optional[int] = None
        self._onboard_log_rows: int = 0
        self._log_end_announced = False

    def set_avionics_log_event_handler(self, handler: Callable[[str], None]) -> None:
        """Called for avionics LOG ack/err/end events (GUI may update state)."""
        self._avionics_log_event = handler

    @property
    def link_stats(self) -> LinkStats:
        return self._link_stats.stats

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

    def is_avionics_downloading(self) -> bool:
        with self._avionics_download_lock:
            return self._avionics_download is not None

    def cancel_avionics_download(self, *, send_abort: bool = True) -> None:
        """Clear any in-progress GS download session and tell avionics to stop streaming."""
        with self._avionics_download_lock:
            self._avionics_download = None
        if send_abort and self._serial is not None and self._serial.is_open:
            try:
                self.send_command("Blivit,LOG,ABORT")
            except Exception:
                pass

    @property
    def serial_fault(self) -> Optional[str]:
        return self._serial_fault

    @property
    def reader_alive(self) -> bool:
        return self._reader_thread is not None and self._reader_thread.is_alive()

    @property
    def serial_is_open(self) -> bool:
        return self._serial is not None and self._serial.is_open

    @property
    def onboard_log_bytes(self) -> Optional[int]:
        return self._onboard_log_bytes

    @property
    def onboard_log_rows(self) -> int:
        return self._onboard_log_rows

    def set_boot_logger(self, handler: Callable[[str], None]) -> None:
        self._boot_logger = handler

    def format_link_status(self) -> str:
        mode = "debug" if self._debug_mode else "field"
        return self._link_stats.format_status_line(
            port=self._port or "—",
            baud=self._baud or 0,
            mode=mode,
        )

    def update_link_state(self, state: str) -> None:
        self._link_stats.set_link_state(state)

    def serial_age_ms(self) -> Optional[float]:
        return self._link_stats.serial_age_ms()

    def is_serial_link_alive(self, stale_ms: float) -> bool:
        age = self.serial_age_ms()
        return age is not None and age <= stale_ms

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
            raise OSError(f"Cannot open {self._port}: {exc}") from exc

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
        self._link_stats.note_handshake("port_open")
        self._serial_fault = None

    def reconnect_serial(self) -> None:
        """Close and reopen the serial port and restart the reader thread."""
        if not self._port:
            if self._debug_mode:
                self._port = DEBUG_SERIAL_PORT
                self._baud = DEBUG_BAUD
            else:
                self._port = RFD900_SERIAL_PORT
                self._baud = RFD900_BAUD

        self._stop.set()
        if self._reader_thread is not None:
            self._reader_thread.join(timeout=1.5)
            self._reader_thread = None

        if self._serial is not None:
            try:
                if self._serial.is_open:
                    self._serial.close()
            except serial.SerialException:
                pass
            self._serial = None

        self._stop.clear()
        self._serial_fault = None
        self._serial = self._open_serial_with_retry(self._port, self._baud)
        self._reader_thread = threading.Thread(
            target=self._reader_loop,
            name="blivit-serial-reader",
            daemon=True,
        )
        self._reader_thread.start()
        self._link_stats.note_handshake("port_reopen")
        if self._boot_logger is not None:
            self._boot_logger(f"Reopened {self._port} @ {self._baud}")

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

    def send_command(self, command: str) -> None:
        if self._serial is None or not self._serial.is_open:
            raise RuntimeError("Serial port is not open")
        line = command if command.endswith("\n") else f"{command}\n"
        self._serial.write(line.encode("ascii"))
        self._serial.flush()

    def avionics_log_start(self) -> None:
        self.send_command("Blivit,LOG,START")

    def avionics_log_stop(self) -> None:
        self.send_command("Blivit,LOG,STOP")

    def avionics_log_clear(self) -> None:
        """Delete onboard flight-data CSV from avionics flash (does not touch ground-station files)."""
        self.send_command("Blivit,LOG,CLEAR")

    def query_avionics_storage(self) -> None:
        """Ask ESP32 for onboard log status and flash capacity (Blivit,LOG,STAT)."""
        self.send_command("Blivit,LOG,STAT")

    def download_avionics_log(
        self,
        path: str | Path | None = None,
        *,
        timeout_s: float = 300.0,
    ) -> Path:
        if self._serial is None or not self._serial.is_open:
            raise RuntimeError("Serial port is not open")

        last_logged_at = 0.0
        progress_interval_s = 3.0

        def on_started() -> None:
            if self._boot_logger is not None:
                self._boot_logger("ESP32 download started — receiving data chunks…")

        def on_progress(nbytes: int, total_bytes: int | None) -> None:
            nonlocal last_logged_at
            if self._boot_logger is None:
                return
            now = time.monotonic()
            if last_logged_at > 0.0 and (now - last_logged_at) < progress_interval_s:
                return
            last_logged_at = now

            total = total_bytes or self._onboard_log_bytes
            self._boot_logger(format_download_progress(nbytes, total))

        session = AvionicsLogDownloadSession(
            on_progress=on_progress,
            on_started=on_started,
            fallback_size=self._onboard_log_bytes,
        )
        with self._avionics_download_lock:
            if self._avionics_download is not None:
                raise RuntimeError("Avionics log download already in progress")
            self._avionics_download = session

        try:
            self.send_command("Blivit,LOG,DL")
            data = session.wait(timeout_s)
            dest = Path(path) if path else make_avionics_log_filepath()
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            if self._boot_logger is not None:
                self._boot_logger(
                    f"Download complete — saved {len(data) / 1024.0:.1f} KB to {dest}"
                )
            return dest
        except Exception:
            self.cancel_avionics_download(send_abort=True)
            raise
        finally:
            with self._avionics_download_lock:
                self._avionics_download = None

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
                self._serial_fault = str(exc)
                if self._boot_logger is not None:
                    self._boot_logger(message)
                elif not self._quiet:
                    print(message)
                break

    def _poll(self) -> None:
        assert self._serial is not None
        try:
            raw = self._serial.readline()
        except serial.SerialException as exc:
            self._serial_fault = str(exc)
            raise
        if not raw:
            return

        self._link_stats.note_serial_rx()

        try:
            line = raw.decode("utf-8", errors="replace")
        except UnicodeDecodeError:
            return

        if self._debug_mode:
            self._handle_debug_line(line)
        else:
            self._handle_radio_line(line)

    def _feed_avionics_log_line(self, line: str) -> bool:
        """Return True if the line is avionics-log protocol (not live telemetry)."""
        if not line.startswith("Blivit,LOG,"):
            return False

        info = parse_onboard_log_protocol(line)
        if info is not None:
            self._onboard_log_bytes = info.bytes
            self._onboard_log_rows = info.rows

        if line.startswith("Blivit,LOG,OK,DL"):
            self._log_end_announced = False

        if line.startswith("Blivit,LOG,OK,CLEAR") or "Onboard flight data cleared" in line:
            self._onboard_log_bytes = 0
            self._onboard_log_rows = 0

        with self._avionics_download_lock:
            session = self._avionics_download
        if session is not None:
            session.feed_line(line)

        console_text = format_avionics_log_console_line(line)
        # Firmware sends Blivit,LOG,END three times for link reliability; log once.
        if console_text and line.startswith("Blivit,LOG,END,"):
            if self._log_end_announced:
                console_text = None
            else:
                self._log_end_announced = True
        if console_text and self._boot_logger is not None:
            self._boot_logger(console_text)

        if self._avionics_log_event is not None and not line.startswith("Blivit,LOG,DATA,"):
            self._avionics_log_event(line)

        return True

    def _handle_debug_line(self, line: str) -> None:
        stripped = line.strip()
        if self._feed_avionics_log_line(stripped):
            return

        if stripped.startswith("Blivit,HELLO,"):
            self._link_stats.note_handshake("remote_hello")

        if stripped.startswith("[HB]") or stripped.startswith("LEMETRY,"):
            return

        if stripped.startswith("TELEMETRY,"):
            result = handle_incoming_line(line)
            if result is None:
                return
            reply, packet = result
            if reply and self._serial is not None:
                self._serial.write(reply.encode("ascii"))
                self._link_stats.note_ack_sent()
            if packet is not None:
                self._link_stats.note_packet(
                    sequence=packet.sequence,
                    wire_format="binary",
                    payload_bytes=HEARTBEAT_PACKET_SIZE,
                )
                self.telemetry.publish(
                    TelemetrySnapshot.from_heartbeat(packet, source="debug")
                )
            return

        telemetry = self._debug_parser.feed_line(line)
        if telemetry is not None:
            self._link_stats.note_packet(
                sequence=telemetry.sequence,
                wire_format="text",
                payload_bytes=0,
            )
            self.telemetry.publish(TelemetrySnapshot.from_debug(telemetry))

    def _handle_radio_line(self, line: str) -> None:
        stripped = line.strip()
        if self._feed_avionics_log_line(stripped):
            return

        if stripped.startswith("Blivit,HELLO,"):
            self._link_stats.note_handshake("remote_hello")
        elif stripped == "PING":
            self._link_stats.note_handshake("ping")

        result = handle_incoming_line(line)
        if result is None:
            return

        reply, packet = result
        if reply and self._serial is not None:
            self._serial.write(reply.encode("ascii"))
            self._link_stats.note_ack_sent()
            if reply.strip().startswith("Blivit,READY"):
                self._link_stats.note_handshake("ready_sent")

        if packet is not None:
            self._link_stats.note_packet(
                sequence=packet.sequence,
                wire_format="binary",
                payload_bytes=HEARTBEAT_PACKET_SIZE,
            )
            self.telemetry.publish(TelemetrySnapshot.from_heartbeat(packet))

    def _on_boot_line(self, line: str) -> None:
        message = format_firmware_console_line(line)
        if message is None:
            return
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
