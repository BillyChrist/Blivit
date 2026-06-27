# ESP32 Build and Library Options

## Chosen path: Arduino framework with PlatformIO

For fastest development and the most pre-built library support, this project is using the Arduino framework on ESP32 via PlatformIO.

- Keeps the setup simple and easy to install
- Uses existing ESP32 Arduino libraries for GPS and IMU
- Avoids needing a deeper ESP-IDF learning curve right now
- Still allows your C modules to remain the main logic

## Keep `blivit_main.c`

Your existing `Avionics/Core/Src/blivit_main.c` can remain the main entry point.
It is fine to keep the core application in C while using Arduino-style libraries for peripherals.

This means:
- Continue writing the main logic in C
- Use C++ Arduino libraries only for peripheral drivers
- If needed, add minimal C++ glue wrappers around those libraries

## Libraries and packages for your peripherals

### GPS

- `TinyGPSPlus`
- `SparkFun_Ublox_Arduino_Library`
- `NMEAGPS`

### IMU / AHRS

- `MPU9250_asukiaaa`
- `SparkFun 9DoF IMU`
- `MadgwickAHRS` / `MahonyAHRS`

### RFD900x

- No dedicated library is required.
- Use UART and implement a small handshake protocol.
- If desired, use a general serial packet framing library like `RadioHead`.

## RFD900x handshake protocol (basic)

1. Open the UART port to the radio.
2. Send a short initialization packet such as `HELLO` or `PING`.
3. Wait for a reply such as `ACK` or `READY`.
4. After acknowledgement, begin telemetry send/receive.

### Example protocol outline

- Send: `Blivit,HELLO,1` or `PING`
- Receive: `ACK` or `Blivit,READY`
- Then begin telemetry frames:
  - `TELEMETRY,<seq>,<payload>,<crc>`
  - `ACK,<seq>`

## Notes

This document now assumes Arduino/PlatformIO is the primary development path.
If you later we want a more embedded C workflow, ESP-IDF can still be considered, but only after the prototype stage.
