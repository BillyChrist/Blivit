# Blivit Avionics Suite Overview

## System Overview

The Blivit avionics suite is centered on an ESP32 DevKit V1 microcontroller running the flight software. The system integrates sensor and telemetry subsystems to support a compact autopilot/telemetry controller.

## Core Components

### ESP32 DevKit V1
- Based on ESP32-WROOM-32
- Dual-core Xtensa LX6 up to 240 MHz
- Typically 4 MB flash
- 2.4 GHz Wi-Fi and Bluetooth 4.2 Classic + BLE
- Micro-USB programming/debug interface
- Multiple UART, I²C, SPI, GPIO, ADC, DAC, and PWM interfaces

This board is the central controller. The design expects multiple serial/UART interfaces:
- One UART for RFD900x
- One UART for WitMotion HWT905-TTL AHRS/IMU
- One UART or I²C for SparkFun u-blox SAM-M8Q GPS

### RFD900x US
- Long-range modem operating in the 902–928 MHz band
- Supports up to 500 kbps air data rate
- Diversity antenna support
- USART interface
- 5 V operating voltage with 3.3 V I/O logic
- Peak TX draw ≈1 A at +30 dBm
- RX draw ≈60 mA typical
- Dimensions ≈ 30 mm × 57.7 mm × 12.8 mm
- Weight ≈ 14 g

### WitMotion HWT905-TTL
- AHRS / IMU sensor
- Measures 3-axis angle, angular velocity, acceleration, and magnetic field
- MPU9250-based sensor
- XY angle accuracy around 0.05°, Z-axis around 1°
- TTL serial data interface
- Requires a supply voltage not exceeding 5 V

### SparkFun u-blox SAM-M8Q GPS Breakout, Qwiic
- 72-channel GNSS receiver
- Supports GPS, GLONASS, Galileo, BeiDou and other M8-family constellations
- Built-in antenna and LNA
- Requires 3.3 V power
- Supports UART/FTDI and I²C via Qwiic/header

## Power System

The avionics system is powered by a regulated 5 V-ish avionics rail, typically derived from an external UBEC or power module. All logic interfaces are designed around 3.3 V UART/I²C levels.

## Project Structure

- `Avionics/` — flight software and sensor/radio modules
- `Ground_Station/` — ground station interface and telemetry handling
- `Documentation/` — design notes and project documentation

## Notes

- Keep the RFD900x serial levels at 3.3 V logic
- Ensure GPS breakout and ESP32 share a common ground
- Avoid exceeding 5 V on the HWT905-TTL main power input
