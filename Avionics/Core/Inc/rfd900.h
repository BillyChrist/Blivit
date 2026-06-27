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
 * RFD900 telemetry radio interface.
 * ================================================================
 */
/* USER CODE END Header */

#ifndef RFD900_H
#define RFD900_H

#ifdef __cplusplus
extern "C" {
#endif

#include <stdbool.h>

bool RFD900_Init(void);
void RFD900_Process(void);

#ifdef __cplusplus
}
#endif

#endif // RFD900_H
