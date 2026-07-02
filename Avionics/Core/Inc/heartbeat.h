/* USER CODE BEGIN Header */
/** ================================================================
 * Blivit Avionics Project
 *
 * Heartbeat module interface.
 * ================================================================
 */
/* USER CODE END Header */

#ifndef HEARTBEAT_H
#define HEARTBEAT_H

#include <cstddef>
#include <cstdint>

#include "telemetry_sample.h"

#define HEARTBEAT_PACKET_SIZE (sizeof(HeartbeatPacket_t))

// Sensor sample + onboard CSV + USB debug cadence (Core 1 publish / queue).
#define TELEMETRY_OUTPUT_INTERVAL_MS 30U

// Field mode (RFD900 @ 57600): ASCII TELEMETRY frame is fixed ~190 B
//   (TELEMETRY,<seq>,<168 hex chars>,<crc>\\r\\n for 84-byte binary payload).
// At 30 ms (~33 Hz) that is ~6.3 KB/s — over 57600 wire budget (~5.8 KB/s).
// RFD uses a slower interval; high-rate data stays on onboard flash.
#define RFD900_TELEMETRY_INTERVAL_MS 100U

// Debug mode (USB @ 115200):
//   debug_binary_telemetry=false → human-readable [DEBUG] lines (default bench path)
//   debug_binary_telemetry=true  → TELEMETRY,<seq>,<hex>,<crc> (same wire format as RFD)
#define DEBUG_TELEMETRY_INTERVAL_MS TELEMETRY_OUTPUT_INTERVAL_MS
#define DEBUG_TEXT_TELEMETRY_INTERVAL_MS 100U

// During onboard log download, heartbeat continues at a slower rate so the ground
// station link indicator stays live while LOG,DATA chunks share the serial port.
#define TELEMETRY_DOWNLOAD_INTERVAL_MS 500U

typedef struct __attribute__((packed))
{
    uint16_t sequence;
    uint32_t uptime_ms;
    uint8_t system_state;
    uint8_t gps_fix;
    uint8_t gps_satellites;
    uint8_t reserved;
    float latitude;
    float longitude;
    float altitude;
    float speed;
    float course;
    float accel_x;
    float accel_y;
    float accel_z;
    float gyro_x;
    float gyro_y;
    float gyro_z;
    float mag_x;
    float mag_y;
    float mag_z;
    float roll;
    float pitch;
    float yaw;
    float temperature;
    uint16_t crc;
} HeartbeatPacket_t;

extern HeartbeatPacket_t heartbeatPacket;

bool Heartbeat_Init(void);
void Heartbeat_UpdateFromSample(const TelemetrySample_t *sample);
bool Heartbeat_HasSample(void);
bool Heartbeat_BuildPacket(uint8_t *buffer, size_t bufferLen, size_t *packetLen);
void telemetry_output(void);
void debug_output(void);

#endif // HEARTBEAT_H
