# Blivit Avionics Suite Overview

## System Overview

The Blivit avionics suite is centered on an ESP32 DevKit V1 running flight firmware. It fuses GNSS and AHRS data into a telemetry heartbeat and transmits it over USB serial (development) or an RFD900 long-range radio (field operation).

## Core Components

### ESP32 DevKit V1
- Based on ESP32-WROOM-32
- Dual-core Xtensa LX6 up to 240 MHz
- Typically 4 MB flash
- 2.4 GHz Wi-Fi and Bluetooth 4.2 Classic + BLE (not used for telemetry in current firmware)
- Micro-USB programming and USB serial debug @ 115200 baud
- Multiple UART, I²C, SPI, and GPIO interfaces

### RFD900x US
- Long-range modem operating in the 902–928 MHz band
- Supports up to 500 kbps air data rate
- Diversity antenna support
- USART interface (transparent serial link)
- Default serial: **57600 baud**, 8N1
- 5 V operating voltage with 3.3 V I/O logic
- Peak TX draw ≈1 A at +30 dBm; RX ≈60 mA typical

### WitMotion HWT905-TTL
- AHRS / IMU with on-board sensor fusion
- MPU9250-based, but exposes **TTL serial output** (WitMotion protocol)
- Default baud: **9600**
- Measures angle, angular rate, acceleration, and magnetic field
- XY angle accuracy ≈0.05°, Z-axis ≈1° (with good mag calibration)
- Supply voltage must not exceed 5 V

### SparkFun u-blox SAM-M8Q GPS Breakout, Qwiic
- 72-channel GNSS (GPS, GLONASS, Galileo, BeiDou)
- Built-in antenna and LNA
- 3.3 V power
- Firmware uses **I²C (Qwiic)** at address 0x42

## ESP32 Pin Map

| Signal | GPIO | Device |
|--------|------|--------|
| RFD900 TX → radio RX | 25 | RFD900x (UART1) |
| RFD900 RX ← radio TX | 26 | RFD900x |
| RFD900 RTS → radio CTS | 14 | RFD900x (optional) |
| RFD900 CTS ← radio RTS | 27 | RFD900x (optional) |
| HWT905 TX → sensor RX | 17 (TX2) | HWT905 (UART2) |
| HWT905 RX ← sensor TX | 16 (RX2) | HWT905 |
| GPS SDA | 21 | SAM-M8Q (I²C) |
| GPS SCL | 22 | SAM-M8Q |
| Status LED | 2 | On-board LED |

## Power System

The avionics box is powered from a regulated ~5 V rail (typically an external UBEC). Logic interfaces are 3.3 V UART/I²C. See `Documentation/PL_4-14S_HYB-BEC.pdf` for the power module reference.

## Firmware Modules

| Module | File | Role |
|--------|------|------|
| Main | `main.cpp` | Init/run loop, `debug_mode`, pin definitions |
| GPS | `gps.cpp` | SAM-M8Q I²C driver |
| IMU | `imu.cpp` | HWT905 WitMotion serial parser |
| Heartbeat | `heartbeat.cpp` | Sensor fusion into `HeartbeatPacket_t`, telemetry output |
| RFD900 | `rfd900.cpp` | Radio handshake and telemetry frames |
| Serial debug | `serial_debug.cpp` | USB status and debug lines |

## Telemetry Paths

**Bench debug** (`debug_mode = true` in `main.cpp`):
- No RFD900 traffic
- `[DEBUG]` lines @ 1 Hz and `[HB]` packet summary @ 0.2 Hz on USB serial

**Field mode** (`debug_mode = false`):
- RFD900 handshake then `TELEMETRY,<seq>,<hex>,<crc>` frames @ 1 Hz
- Requires a paired ground-station RFD900 modem

## Project Structure

```
Blivit/
├── Avionics/           # ESP32 firmware (PlatformIO project root)
├── Ground_Station/     # PC ground station skeleton
└── Documentation/      # Design notes and hardware references
```

## Notes

- Keep RFD900x serial levels at 3.3 V logic
- GPS breakout and ESP32 must share common ground
- Do not exceed 5 V on the HWT905-TTL supply
- HWT905 wiring: ESP TX → sensor RX, ESP RX ← sensor TX
