/* USER CODE BEGIN Header */
/** ================================================================
 * Blivit Avionics Project
 *
 * IMU module interface.
 * ================================================================
 */
/* USER CODE END Header */

#ifndef IMU_H
#define IMU_H

#include <stdint.h>

typedef struct
{
    float x;
    float y;
    float z;
} IMU_Vector3f;

typedef struct
{
    IMU_Vector3f accel;    // m/s²
    IMU_Vector3f gyro;     // deg/s
    IMU_Vector3f mag;      // raw sensor units (WitMotion protocol)
    float roll;            // degrees
    float pitch;           // degrees
    float yaw;             // degrees
    float temperature;     // degrees Celsius (if available)
} IMU_Data_t;

extern IMU_Data_t imuData;

bool IMU_Init(void);
void IMU_Update(void);
uint32_t IMU_GetFrameCount(void);
uint32_t IMU_GetByteCount(void);
bool IMU_GetTelemetrySnapshot(IMU_Data_t *out);
bool IMU_IsTelemetryReady(void);

#endif // IMU_H
