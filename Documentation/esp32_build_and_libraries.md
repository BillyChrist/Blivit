# ESP32 Build and Library Options

## Chosen path: Arduino framework with PlatformIO

This project uses the **Arduino framework on ESP32** via PlatformIO.

- Simple toolchain and library management
- Native ESP32 Arduino APIs for UART, I²C, and USB serial
- All application source is **C++** under `Avionics/Core/`

## Project layout

```
Avionics/
├── platformio.ini          # src_dir = Core/Src, include_dir = Core/Inc
└── Core/
    ├── Inc/                  # Module headers
    └── Src/                  # Module implementations (.cpp)
        ├── main.cpp          # Entry point, pin map, debug_mode, setup/loop
        ├── gps.cpp           # SAM-M8Q over I²C
        ├── imu.cpp           # HWT905 over UART (WitMotion protocol)
        ├── rfd900.cpp        # RFD900x radio link
        ├── heartbeat.cpp     # Telemetry packet + output routing
        └── serial_debug.cpp  # USB serial @ 115200
```

Open **`Avionics/`** as the PlatformIO project root (the folder containing `platformio.ini`).

## Libraries

### In use (PlatformIO `lib_deps`)

| Library | Peripheral | Notes |
|---------|------------|-------|
| SparkFun u-blox GNSS Arduino Library | SAM-M8Q GPS | I²C @ 100 kHz, UBX auto-PVT |

### Not used — custom drivers instead

| Peripheral | Approach |
|------------|----------|
| HWT905-TTL IMU | WitMotion standard serial protocol (`0x55` frames) in `imu.cpp` — **not** a raw MPU9250 I²C library |
| RFD900x | Transparent UART + Blivit text framing in `rfd900.cpp` |

Previously considered but **not** in the project: TinyGPSPlus, NMEAGPS, MPU9250_asukiaaa, Madgwick/Mahony AHRS libraries.

## Runtime modes (`debug_mode`)

Configured in `Avionics/Core/Src/main.cpp`:

```cpp
bool debug_mode = true;   // bench: USB serial telemetry
bool debug_mode = false;  // field: RFD900 radio telemetry
```

| Mode | Init | Main loop output |
|------|------|------------------|
| Debug (`true`) | GPS, IMU, heartbeat only | `telemetry_output()` → USB `[DEBUG]` + `[HB]` |
| Field (`false`) | Above + `RFD900_Init()` | `RFD900_Process()` → handshake + radio frames |

USB serial boot messages appear in **both** modes.

## RFD900x protocol

Hardware: transparent serial modem, default **57600 baud**, 8N1, 3.3 V logic.  
Optional hardware flow control on GPIO 14 (RTS) / 27 (CTS).

Application framing:

1. Send `Blivit,HELLO,1` or `PING`
2. Receive `ACK`, `ACK,<seq>`, or `Blivit,READY`
3. Send telemetry: `TELEMETRY,<seq>,<hex_payload>,<crc>`
4. Receive `ACK,<seq>`

The hex payload is the packed `HeartbeatPacket_t` (see `heartbeat.h`).

## Heartbeat packet

68-byte packed struct: sequence, uptime, system state, GPS fix/sats, lat/lon/alt/speed/course, accel/gyro/mag, Modbus-style CRC16.

- `system_state = 1` — debug mode (USB serial)
- `system_state = 2` — field mode (RFD900)

## Build and flash

From PlatformIO (project folder `Avionics/`):

1. **Build** — compile firmware
2. **Upload** — flash ESP32 over USB
3. **Monitor** — serial monitor @ **115200**

## Notes

Arduino/PlatformIO is the primary development path. ESP-IDF remains an option later if needed, but is not used today.
