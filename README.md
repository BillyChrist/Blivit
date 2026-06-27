# Blivit Avionics Suite

This repository contains the Blivit Avionics Project, including:

- `Avionics/` — flight controller firmware modules
- `Ground_Station/` — ground station software skeleton
- `Documentation/` — architecture and design notes

## Overview

The avionics suite is built around an ESP32 DevKit V1 microcontroller. It integrates:

- RFD900x long-range telemetry modem
- WitMotion HWT905-TTL AHRS/IMU
- SparkFun u-blox SAM-M8Q GPS breakout

## Getting Started

1. Review `Documentation/avionics_overview.md` for system architecture.
2. Use the provided `Avionics/platformio.ini` to manage ESP32 and library dependencies automatically.
3. Implement or extend the hardware driver modules under `Avionics/Core/`.
4. The ground station is a separate PC-side component and will use a different structure from the ESP32 flight firmware.

## Recommended Setup

- Use PlatformIO with the `esp32dev` environment.
- This project uses the Arduino framework for fastest development.
- `platformio.ini` includes Arduino-style libraries for:
  - `TinyGPSPlus` for GNSS parsing
  - `SparkFun_Ublox_Arduino_Library` for the SAM-M8Q GPS
  - `MPU9250_asukiaaa` for IMU handling

## RFD900x Telemetry Handshake

For the RFD900x, treat it as a serial modem. Start with a simple handshake sequence:

1. Open UART at the configured baud rate.
2. Send a short `HELLO` or `PING` packet.
3. Wait for an acknowledgement packet such as `ACK`.
4. Begin telemetry exchange once the radio link is established.

## Notes

- The RFD900x and GPS interfaces are expected to use 3.3 V UART levels.
- The HWT905-TTL should be powered no higher than 5 V.
- The project skeleton includes basic core headers and C source stubs.
