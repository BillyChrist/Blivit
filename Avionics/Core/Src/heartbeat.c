/* USER CODE BEGIN Header */
/** ================================================================
 * Blivit Avionics Project
 *
 * Component: System heartbeat / health monitor
 *
 * Tracks system alive status, heartbeat signaling, and health state.
 *
 * @attention
 * Copyright (c) 2026 Geofabrica. All rights reserved.
 *
 * License: MIT License
 *
 * Author: BillyChrist
 *
 * Heartbeat module implementation.
 * ================================================================
 */
/* USER CODE END Header */

#include "heartbeat.h"
#include <string.h>

HeartbeatPacket_t heartbeatPacket = {
    .sequence = 0,
    .uptime_ms = 0,
    .system_state = 0,
    .gps_fix = 0,
    .gps_satellites = 0,
    .reserved = 0,
    .latitude = 0.0f,
    .longitude = 0.0f,
    .altitude = 0.0f,
    .speed = 0.0f,
    .course = 0.0f,
    .accel_x = 0.0f,
    .accel_y = 0.0f,
    .accel_z = 0.0f,
    .gyro_x = 0.0f,
    .gyro_y = 0.0f,
    .gyro_z = 0.0f,
    .mag_x = 0.0f,
    .mag_y = 0.0f,
    .mag_z = 0.0f,
    .crc = 0,
};

static uint16_t Heartbeat_CalculateCRC(const uint8_t *data, size_t length);

bool Heartbeat_Init(void)
{
    memset(&heartbeatPacket, 0, sizeof(heartbeatPacket));
    heartbeatPacket.sequence = 0;
    heartbeatPacket.uptime_ms = 0;
    return true;
}

void Heartbeat_Update(void)
{
    /* TODO: update heartbeatPacket fields from system state, GPS, and IMU modules */
}

void heartbeat_output(void)
{
    // TODO: use USB serial or console output to inspect heartbeat packet state
    // Example: print current packet fields for debug validation
}

void debug_output(void)
{
    // TODO: expose runtime telemetry state over USB serial for Putty / serial monitor
}

bool Heartbeat_BuildPacket(uint8_t *buffer, size_t bufferLen, size_t *packetLen)
{
    if (!buffer || !packetLen || bufferLen < HEARTBEAT_PACKET_SIZE)
    {
        return false;
    }

    heartbeatPacket.crc = 0;
    heartbeatPacket.crc = Heartbeat_CalculateCRC((const uint8_t *)&heartbeatPacket, HEARTBEAT_PACKET_SIZE - sizeof(heartbeatPacket.crc));

    memcpy(buffer, &heartbeatPacket, HEARTBEAT_PACKET_SIZE);
    *packetLen = HEARTBEAT_PACKET_SIZE;
    return true;
}

static uint16_t Heartbeat_CalculateCRC(const uint8_t *data, size_t length)
{
    uint16_t crc = 0xFFFF;
    for (size_t i = 0; i < length; ++i)
    {
        crc ^= (uint16_t)data[i];
        for (int bit = 0; bit < 8; ++bit)
        {
            if (crc & 0x0001)
            {
                crc = (crc >> 1) ^ 0xA001;
            }
            else
            {
                crc >>= 1;
            }
        }
    }
    return crc;
}
