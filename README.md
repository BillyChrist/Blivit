# Blivit Avionics Suite

This repository contains the Blivit Avionics Project, including:

- `Avionics/` — ESP32 flight firmware (PlatformIO / Arduino)
- `Ground_Station/` — ground station software skeleton
- `Documentation/` — architecture and design notes

## Overview

The avionics suite is built around an ESP32 DevKit V1 microcontroller. It integrates:

- RFD900x long-range telemetry modem
- WitMotion HWT905-TTL AHRS/IMU
- SparkFun u-blox SAM-M8Q GPS breakout (Qwiic / I²C)

Sensor data is aggregated into a packed binary heartbeat packet and sent either over **USB serial** (bench debug) or the **RFD900 radio** (field mode).

## Getting Started

1. Review `Documentation/avionics_overview.md` for hardware and pin map.
2. Review `Documentation/esp32_build_and_libraries.md` for build details and telemetry protocol.
3. Open the **`Avionics/`** folder in PlatformIO (not the repo root).
4. Build, upload, and open the serial monitor at **115200 baud**.

## Recommended Setup

- PlatformIO with the `esp32dev` environment
- Arduino framework on ESP32
- Third-party library in use:
  - **SparkFun u-blox GNSS Arduino Library** — SAM-M8Q GPS over I²C (UBX protocol)

The HWT905 IMU and RFD900 radio use **custom serial drivers** in firmware (no dedicated PlatformIO library).

## Debug vs Field Mode

Set `debug_mode` near the top of `Avionics/Core/Src/main.cpp`:

| `debug_mode` | Telemetry output |
|--------------|------------------|
| `true` (default) | Human-readable `[DEBUG]` / `[HB]` lines over **USB serial** |
| `false` | Binary/text frames over the **RFD900** radio to a ground-station modem |

Use **debug mode** on the bench when you do not have a second RFD900 connected.

## RFD900x Telemetry Handshake

Treat the RFD900x as a transparent serial modem (default **57600 baud**, 8N1):

1. Open UART to the radio.
2. Send `Blivit,HELLO,1` (or `PING`).
3. Wait for `ACK` or `Blivit,READY`.
4. Exchange telemetry frames:
   - `TELEMETRY,<seq>,<hex_payload>,<crc>`
   - `ACK,<seq>`

See `Documentation/esp32_build_and_libraries.md` for full protocol notes.

## Notes

- RFD900x and GPS logic levels are **3.3 V**.
- HWT905-TTL power must not exceed **5 V**.
- USB serial remains available for boot/status messages in both modes.
