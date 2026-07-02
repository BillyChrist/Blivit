#include "telemetry_sample.h"

#include "gps.h"
#include "imu.h"
#include "serial_debug.h"

#include <cstring>

bool TelemetrySample_BuildFromSensors(TelemetrySample_t *out)
{
    if (!out)
    {
        return false;
    }

    GPS_Data_t gps{};
    const bool gps_ready = GPS_IsReady();
    if (gps_ready)
    {
        GPS_CopyData(&gps);
    }

    IMU_Data_t imu{};
    const bool imu_ready = IMU_GetTelemetrySnapshot(&imu);

    if (!gps_ready && !imu_ready)
    {
        return false;
    }

    std::memset(out, 0, sizeof(*out));

    out->sample_time_ms = SerialDebug_Millis();
    out->uptime_ms = out->sample_time_ms;

    out->gps_valid = gps.fix.valid ? 1U : 0U;
    out->gps_satellites = static_cast<uint8_t>(gps.fix.satellites);
    out->hdop = gps.fix.hdop;

    if (gps.fix.valid)
    {
        out->latitude = gps.position.latitude;
        out->longitude = gps.position.longitude;
        out->altitude = gps.position.altitude;
        out->speed = gps.position.speed;
        out->course = gps.position.course;
        out->vel_n = gps.position.vel_n;
        out->vel_e = gps.position.vel_e;
        out->vel_d = gps.position.vel_d;
    }

    std::strncpy(out->utc_time, gps.utc_time, sizeof(out->utc_time) - 1U);
    std::strncpy(out->date, gps.date, sizeof(out->date) - 1U);

    if (imu_ready)
    {
        out->roll = imu.roll;
        out->pitch = imu.pitch;
        out->yaw = imu.yaw;
        out->temperature = imu.temperature;
        out->accel_x = imu.accel.x;
        out->accel_y = imu.accel.y;
        out->accel_z = imu.accel.z;
        out->gyro_x = imu.gyro.x;
        out->gyro_y = imu.gyro.y;
        out->gyro_z = imu.gyro.z;
        out->mag_x = imu.mag.x;
        out->mag_y = imu.mag.y;
        out->mag_z = imu.mag.z;
    }

    out->gps_updates = GPS_GetUpdateCount();
    out->imu_frames = IMU_GetFrameCount();
    out->imu_bytes = IMU_GetByteCount();

    return true;
}
