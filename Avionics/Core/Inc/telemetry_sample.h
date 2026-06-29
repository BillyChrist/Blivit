/* USER CODE BEGIN Header */
/** Complete sensor snapshot — sole handoff object between Core 1 and Core 0. */
/* USER CODE END Header */

#ifndef TELEMETRY_SAMPLE_H
#define TELEMETRY_SAMPLE_H

#include <cstdint>

#define TELEMETRY_SOURCE_PERIODIC 0x00U
#define TELEMETRY_SOURCE_GPS 0x01U
#define TELEMETRY_SOURCE_IMU 0x02U

typedef struct
{
    uint32_t sample_time_ms;
    uint32_t uptime_ms;

    uint8_t source_mask;
    uint32_t gps_updates;
    uint8_t imu_frame_type;

    uint8_t gps_valid;
    uint8_t gps_satellites;
    float hdop;
    double latitude;
    double longitude;
    float altitude;
    float speed;
    float course;
    float vel_n;
    float vel_e;
    float vel_d;
    char utc_time[16];
    char date[12];

    float roll;
    float pitch;
    float yaw;
    float temperature;
    float accel_x;
    float accel_y;
    float accel_z;
    float gyro_x;
    float gyro_y;
    float gyro_z;
    float mag_x;
    float mag_y;
    float mag_z;
    uint32_t imu_frames;
    uint32_t imu_bytes;
} TelemetrySample_t;

bool TelemetrySample_BuildFromSensors(TelemetrySample_t *out);

#endif // TELEMETRY_SAMPLE_H
