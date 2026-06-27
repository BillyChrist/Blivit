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
 * IMU module interface.
 * ================================================================
 */
/* USER CODE END Header */

#ifndef IMU_H
#define IMU_H

#ifdef __cplusplus
extern "C" {
#endif

#include <stdbool.h>

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
    IMU_Vector3f mag;      // µT or arbitrary units
    float roll;            // degrees
    float pitch;           // degrees
    float yaw;             // degrees
    float temperature;     // degrees Celsius (if available)
} IMU_Data_t;

extern IMU_Data_t imuData;

bool IMU_Init(void);
void IMU_Update(void);

#ifdef __cplusplus
}
#endif

#endif // IMU_H
