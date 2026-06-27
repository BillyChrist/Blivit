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
2. Implement the hardware-specific driver modules under `Avionics/Core/`.
3. Add build scripts or toolchain configuration for ESP32 firmware.

## Notes

- The RFD900x and GPS interfaces are expected to use 3.3 V UART levels.
- The HWT905-TTL should be powered no higher than 5 V.
- The project skeleton includes basic core headers and C source stubs.
