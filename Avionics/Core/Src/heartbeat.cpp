/* USER CODE BEGIN Header */
/** Heartbeat / telemetry output — runs on Core 0 from queued TelemetrySample_t only. */
/* USER CODE END Header */

#include "heartbeat.h"
#include "gps.h"
#include "main.h"
#include "serial_debug.h"

#include <cstring>
#include <cstdio>

#define DEBUG_OUTPUT_INTERVAL_MS DEBUG_TELEMETRY_INTERVAL_MS
#define HEARTBEAT_OUTPUT_INTERVAL_MS 5000U
#define HEARTBEAT_GRAVITY_MS2 9.80665f
#define DEBUG_BINARY_HEX_MAX ((HEARTBEAT_PACKET_SIZE * 2U) + 1U)

static float Heartbeat_AccelToG(float accel);

HeartbeatPacket_t heartbeatPacket{};

static TelemetrySample_t heartbeatSample{};
static bool heartbeatSampleValid = false;

static uint16_t Heartbeat_CalculateCRC(const uint8_t *data, size_t length);
static bool Heartbeat_ShouldPrint(uint32_t intervalMs, uint32_t *lastPrintMs);
static void Heartbeat_BytesToHex(const uint8_t *data, size_t length, char *out, size_t out_length);
static void Heartbeat_DebugBinaryOutput(void);

bool Heartbeat_Init(void)
{
    heartbeatPacket = {};
    heartbeatPacket.system_state = 1;
    heartbeatSample = {};
    heartbeatSampleValid = false;
    return true;
}

bool Heartbeat_HasSample(void)
{
    return heartbeatSampleValid;
}

void Heartbeat_UpdateFromSample(const TelemetrySample_t *sample)
{
    if (!sample)
    {
        return;
    }

    heartbeatSample = *sample;
    heartbeatSampleValid = true;

    heartbeatPacket.uptime_ms = sample->uptime_ms;
    heartbeatPacket.system_state = debug_mode ? 1U : 2U;
    heartbeatPacket.gps_fix = sample->gps_valid;
    heartbeatPacket.gps_satellites = sample->gps_satellites;
    heartbeatPacket.latitude = static_cast<float>(sample->latitude);
    heartbeatPacket.longitude = static_cast<float>(sample->longitude);
    heartbeatPacket.altitude = sample->altitude;
    heartbeatPacket.speed = sample->speed;
    heartbeatPacket.course = sample->course;
    heartbeatPacket.accel_x = sample->accel_x;
    heartbeatPacket.accel_y = sample->accel_y;
    heartbeatPacket.accel_z = sample->accel_z;
    heartbeatPacket.gyro_x = sample->gyro_x;
    heartbeatPacket.gyro_y = sample->gyro_y;
    heartbeatPacket.gyro_z = sample->gyro_z;
    heartbeatPacket.mag_x = sample->mag_x;
    heartbeatPacket.mag_y = sample->mag_y;
    heartbeatPacket.mag_z = sample->mag_z;
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

    if (!heartbeatSampleValid || !Heartbeat_ShouldPrint(HEARTBEAT_OUTPUT_INTERVAL_MS, &lastPrintMs))
    {
        return;
    }

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
        heartbeatSample.vel_n,
        heartbeatSample.vel_e,
        heartbeatSample.vel_d,
        -heartbeatSample.vel_d);

    SerialDebug_Print(
        "[HB] imu r=%.2f p=%.2f y=%.2f temp=%.2f "
        "accel_g=(%.3f,%.3f,%.3f) gyro=(%.2f,%.2f,%.2f) mag=(%.1f,%.1f,%.1f)",
        heartbeatSample.roll,
        heartbeatSample.pitch,
        heartbeatSample.yaw,
        heartbeatSample.temperature,
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

    if (!heartbeatSampleValid || !Heartbeat_ShouldPrint(DEBUG_OUTPUT_INTERVAL_MS, &lastPrintMs))
    {
        return;
    }

    if (debug_mode && debug_binary_telemetry)
    {
        Heartbeat_DebugBinaryOutput();
        return;
    }

    heartbeatPacket.sequence++;

    const TelemetrySample_t &s = heartbeatSample;

    SerialDebug_Print(
        "[DEBUG] t=%lums seq=%u gps_ready=%d gps valid=%d sats=%d hdop=%.1f lat=%.6f lon=%.6f alt=%.1f "
        "spd=%.2f crs=%.1f vn=%.2f ve=%.2f vd=%.2f climb=%.2f utc=%s date=%s "
        "imu frames=%lu bytes=%lu r=%.2f p=%.2f y=%.2f temp=%.2f "
        "accel_g=(%.3f,%.3f,%.3f) gyro=(%.2f,%.2f,%.2f) mag=(%.1f,%.1f,%.1f)",
        heartbeatPacket.uptime_ms,
        heartbeatPacket.sequence,
        GPS_IsReady() ? 1 : 0,
        s.gps_valid,
        s.gps_satellites,
        s.hdop,
        s.latitude,
        s.longitude,
        s.altitude,
        s.speed,
        s.course,
        s.vel_n,
        s.vel_e,
        s.vel_d,
        -s.vel_d,
        s.utc_time[0] ? s.utc_time : "--",
        s.date[0] ? s.date : "--",
        static_cast<unsigned long>(s.imu_frames),
        static_cast<unsigned long>(s.imu_bytes),
        s.roll,
        s.pitch,
        s.yaw,
        s.temperature,
        Heartbeat_AccelToG(s.accel_x),
        Heartbeat_AccelToG(s.accel_y),
        Heartbeat_AccelToG(s.accel_z),
        s.gyro_x,
        s.gyro_y,
        s.gyro_z,
        s.mag_x,
        s.mag_y,
        s.mag_z);
}

bool Heartbeat_BuildPacket(uint8_t *buffer, size_t bufferLen, size_t *packetLen)
{
    if (!buffer || !packetLen || bufferLen < HEARTBEAT_PACKET_SIZE || !heartbeatSampleValid)
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

static void Heartbeat_BytesToHex(const uint8_t *data, size_t length, char *out, size_t out_length)
{
    if (!data || !out || out_length == 0)
    {
        return;
    }

    size_t write_index = 0;
    for (size_t i = 0; i < length; ++i)
    {
        if ((write_index + 3U) > out_length)
        {
            break;
        }

        std::snprintf(out + write_index, out_length - write_index, "%02X", data[i]);
        write_index += 2U;
    }

    out[write_index] = '\0';
}

static void Heartbeat_DebugBinaryOutput(void)
{
    heartbeatPacket.sequence++;

    uint8_t packet[HEARTBEAT_PACKET_SIZE];
    size_t packet_length = 0;

    if (!Heartbeat_BuildPacket(packet, sizeof(packet), &packet_length))
    {
        return;
    }

    char hex_payload[DEBUG_BINARY_HEX_MAX];
    Heartbeat_BytesToHex(packet, packet_length, hex_payload, sizeof(hex_payload));

    SerialDebug_Print(
        "TELEMETRY,%u,%s,%04X",
        heartbeatPacket.sequence,
        hex_payload,
        heartbeatPacket.crc);
}
