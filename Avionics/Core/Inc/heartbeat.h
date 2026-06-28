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

// Field mode (RFD900 @ 57600): binary TELEMETRY frame ~160 B -> 30 ms (~33 Hz) max.
// Onboard CSV logging on Core 1 is NOT gated by this — it runs every sensor loop (~5 ms).
#define TELEMETRY_OUTPUT_INTERVAL_MS 30U

// Debug mode (USB @ 115200): same cadence as field when using one line or binary TELEMETRY.
// Two-line text @ 33 Hz exceeds 115200 (~11.5 KB/s); use DEBUG_TELEMETRY_BINARY or one line.
#define DEBUG_TELEMETRY_INTERVAL_MS TELEMETRY_OUTPUT_INTERVAL_MS

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
    uint16_t crc;
} HeartbeatPacket_t;

extern HeartbeatPacket_t heartbeatPacket;

bool Heartbeat_Init(void);
void Heartbeat_UpdateFromSample(const TelemetrySample_t *sample);
bool Heartbeat_HasSample(void);
bool Heartbeat_BuildPacket(uint8_t *buffer, size_t bufferLen, size_t *packetLen);
void telemetry_output(void);
void debug_output(void);
void heartbeat_output(void);

#endif // HEARTBEAT_H
