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

bool IMU_Init(void);
void IMU_Update(void);

#ifdef __cplusplus
}
#endif

#endif // IMU_H
