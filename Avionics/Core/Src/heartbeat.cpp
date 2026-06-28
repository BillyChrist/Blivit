/* USER CODE BEGIN Header */
/** ================================================================
 * Blivit Avionics Project
 *
 * Component: System heartbeat / health monitor
 *
 * Aggregates sensor data into HeartbeatPacket_t and routes telemetry:
 *   debug_mode true  -> human-readable USB serial output
 *   debug_mode false -> RFD900 radio (handled by rfd900.cpp / main loop)
 * ================================================================
 */
/* USER CODE END Header */

#include "heartbeat.h"
#include "gps.h"
#include "imu.h"
#include "main.h"
#include "serial_debug.h"

#include <cstring>

#define DEBUG_OUTPUT_INTERVAL_MS TELEMETRY_OUTPUT_INTERVAL_MS
#define HEARTBEAT_OUTPUT_INTERVAL_MS 5000U
#define HEARTBEAT_GRAVITY_MS2 9.80665f

static float Heartbeat_AccelToG(float accel);

HeartbeatPacket_t heartbeatPacket{};

// Frozen IMU sample used for telemetry output (debug + RFD900)
static IMU_Data_t telemetryImu{};

static uint16_t Heartbeat_CalculateCRC(const uint8_t *data, size_t length);
static bool Heartbeat_ShouldPrint(uint32_t intervalMs, uint32_t *lastPrintMs);
static void Heartbeat_ApplyImuToPacket(const IMU_Data_t &imu);

bool Heartbeat_Init(void)
{
    heartbeatPacket = {};
    heartbeatPacket.system_state = 1;
    return true;
}

void Heartbeat_Update(void)
{
    heartbeatPacket.uptime_ms = SerialDebug_Millis();
    heartbeatPacket.system_state = debug_mode ? 1U : 2U;
    heartbeatPacket.gps_fix = gpsData.fix.valid ? 1U : 0U;
    heartbeatPacket.gps_satellites = static_cast<uint8_t>(gpsData.fix.satellites);
    heartbeatPacket.latitude = static_cast<float>(gpsData.position.latitude);
    heartbeatPacket.longitude = static_cast<float>(gpsData.position.longitude);
    heartbeatPacket.altitude = gpsData.position.altitude;
    heartbeatPacket.speed = gpsData.position.speed;
    heartbeatPacket.course = gpsData.position.course;
}

void Heartbeat_CaptureSnapshot(void)
{
    telemetryImu = imuData;
    Heartbeat_ApplyImuToPacket(telemetryImu);
}

static void Heartbeat_ApplyImuToPacket(const IMU_Data_t &imu)
{
    heartbeatPacket.accel_x = imu.accel.x;
    heartbeatPacket.accel_y = imu.accel.y;
    heartbeatPacket.accel_z = imu.accel.z;
    heartbeatPacket.gyro_x = imu.gyro.x;
    heartbeatPacket.gyro_y = imu.gyro.y;
    heartbeatPacket.gyro_z = imu.gyro.z;
    heartbeatPacket.mag_x = imu.mag.x;
    heartbeatPacket.mag_y = imu.mag.y;
    heartbeatPacket.mag_z = imu.mag.z;
}

void telemetry_output(void)
{
    debug_output();
    heartbeat_output();
}

void heartbeat_output(void)
{
    static uint32_t lastPrintMs = 0;
    uint8_t buffer[HEARTBEAT_PACKET_SIZE];
    size_t packetLen = 0;

    if (!Heartbeat_ShouldPrint(HEARTBEAT_OUTPUT_INTERVAL_MS, &lastPrintMs))
    {
        return;
    }

    Heartbeat_CaptureSnapshot();

    if (!Heartbeat_BuildPacket(buffer, sizeof(buffer), &packetLen))
    {
        SerialDebug_Print("[HB] ERROR: failed to build packet");
        return;
    }

    uint16_t storedCrc = heartbeatPacket.crc;
    heartbeatPacket.crc = 0;
    uint16_t recalcCrc = Heartbeat_CalculateCRC(
        reinterpret_cast<const uint8_t *>(&heartbeatPacket),
        HEARTBEAT_PACKET_SIZE - sizeof(heartbeatPacket.crc));
    heartbeatPacket.crc = storedCrc;

    SerialDebug_Print(
        "[HB] seq=%u uptime=%lums size=%u crc=0x%04X valid=%s fix=%u sats=%u lat=%.6f lon=%.6f alt=%.1f "
        "spd=%.2f crs=%.1f vn=%.2f ve=%.2f vd=%.2f climb=%.2f",
        heartbeatPacket.sequence,
        heartbeatPacket.uptime_ms,
        static_cast<unsigned>(packetLen),
        heartbeatPacket.crc,
        recalcCrc == storedCrc ? "yes" : "no",
        heartbeatPacket.gps_fix,
        heartbeatPacket.gps_satellites,
        heartbeatPacket.latitude,
        heartbeatPacket.longitude,
        heartbeatPacket.altitude,
        heartbeatPacket.speed,
        heartbeatPacket.course,
        gpsData.position.vel_n,
        gpsData.position.vel_e,
        gpsData.position.vel_d,
        -gpsData.position.vel_d);

    SerialDebug_Print(
        "[HB] imu r=%.2f p=%.2f y=%.2f temp=%.2f "
        "accel_g=(%.3f,%.3f,%.3f) gyro=(%.2f,%.2f,%.2f) mag=(%.1f,%.1f,%.1f)",
        telemetryImu.roll,
        telemetryImu.pitch,
        telemetryImu.yaw,
        telemetryImu.temperature,
        Heartbeat_AccelToG(heartbeatPacket.accel_x),
        Heartbeat_AccelToG(heartbeatPacket.accel_y),
        Heartbeat_AccelToG(heartbeatPacket.accel_z),
        heartbeatPacket.gyro_x,
        heartbeatPacket.gyro_y,
        heartbeatPacket.gyro_z,
        heartbeatPacket.mag_x,
        heartbeatPacket.mag_y,
        heartbeatPacket.mag_z);
}

void debug_output(void)
{
    static uint32_t lastPrintMs = 0;

    if (!Heartbeat_ShouldPrint(DEBUG_OUTPUT_INTERVAL_MS, &lastPrintMs))
    {
        return;
    }

    Heartbeat_CaptureSnapshot();

    heartbeatPacket.sequence++;

    SerialDebug_Print(
        "[DEBUG] t=%lums seq=%u gps valid=%d sats=%d hdop=%.1f lat=%.6f lon=%.6f alt=%.1f "
        "spd=%.2f crs=%.1f vn=%.2f ve=%.2f vd=%.2f climb=%.2f utc=%s date=%s",
        heartbeatPacket.uptime_ms,
        heartbeatPacket.sequence,
        gpsData.fix.valid,
        gpsData.fix.satellites,
        gpsData.fix.hdop,
        gpsData.position.latitude,
        gpsData.position.longitude,
        gpsData.position.altitude,
        gpsData.position.speed,
        gpsData.position.course,
        gpsData.position.vel_n,
        gpsData.position.vel_e,
        gpsData.position.vel_d,
        -gpsData.position.vel_d,
        gpsData.utc_time[0] ? gpsData.utc_time : "--",
        gpsData.date[0] ? gpsData.date : "--");

    SerialDebug_Print(
        "[DEBUG] imu frames=%lu bytes=%lu r=%.2f p=%.2f y=%.2f temp=%.2f "
        "accel_g=(%.3f,%.3f,%.3f) gyro=(%.2f,%.2f,%.2f) mag=(%.1f,%.1f,%.1f)",
        static_cast<unsigned long>(IMU_GetFrameCount()),
        static_cast<unsigned long>(IMU_GetByteCount()),
        telemetryImu.roll,
        telemetryImu.pitch,
        telemetryImu.yaw,
        telemetryImu.temperature,
        Heartbeat_AccelToG(telemetryImu.accel.x),
        Heartbeat_AccelToG(telemetryImu.accel.y),
        Heartbeat_AccelToG(telemetryImu.accel.z),
        telemetryImu.gyro.x,
        telemetryImu.gyro.y,
        telemetryImu.gyro.z,
        telemetryImu.mag.x,
        telemetryImu.mag.y,
        telemetryImu.mag.z);
}

bool Heartbeat_BuildPacket(uint8_t *buffer, size_t bufferLen, size_t *packetLen)
{
    if (!buffer || !packetLen || bufferLen < HEARTBEAT_PACKET_SIZE)
    {
        return false;
    }

    if (!debug_mode)
    {
        heartbeatPacket.sequence++;
    }

    heartbeatPacket.crc = 0;
    heartbeatPacket.crc = Heartbeat_CalculateCRC(
        reinterpret_cast<const uint8_t *>(&heartbeatPacket),
        HEARTBEAT_PACKET_SIZE - sizeof(heartbeatPacket.crc));

    std::memcpy(buffer, &heartbeatPacket, HEARTBEAT_PACKET_SIZE);
    *packetLen = HEARTBEAT_PACKET_SIZE;
    return true;
}

static uint16_t Heartbeat_CalculateCRC(const uint8_t *data, size_t length)
{
    uint16_t crc = 0xFFFF;
    for (size_t i = 0; i < length; ++i)
    {
        crc ^= static_cast<uint16_t>(data[i]);
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

static float Heartbeat_AccelToG(float accel)
{
    return accel / HEARTBEAT_GRAVITY_MS2;
}

static bool Heartbeat_ShouldPrint(uint32_t intervalMs, uint32_t *lastPrintMs)
{
    uint32_t now = SerialDebug_Millis();

    if ((now - *lastPrintMs) < intervalMs)
    {
        return false;
    }

    *lastPrintMs = now;
    return true;
}
