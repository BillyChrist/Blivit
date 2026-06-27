/* USER CODE BEGIN Header */
/** ================================================================
 * Blivit Avionics Project
 *
 * @attention
 * Copyright (c) 2026 Geofabrica. All rights reserved.
 *
 * License: MIT License
 *
 * Author: BillyChrist
 *
 * Heartbeat module interface.
 * ================================================================
 */
/* USER CODE END Header */

#ifndef HEARTBEAT_H
#define HEARTBEAT_H

#ifdef __cplusplus
extern "C" {
#endif

#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>

#define HEARTBEAT_PACKET_SIZE 48

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
void Heartbeat_Update(void);
bool Heartbeat_BuildPacket(uint8_t *buffer, size_t bufferLen, size_t *packetLen);
void heartbeat_output(void);
void debug_output(void);

#ifdef __cplusplus
}
#endif

#endif // HEARTBEAT_H
