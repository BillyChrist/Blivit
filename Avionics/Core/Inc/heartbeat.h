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

bool Heartbeat_Init(void);
void Heartbeat_Update(void);

#ifdef __cplusplus
}
#endif

#endif // HEARTBEAT_H
