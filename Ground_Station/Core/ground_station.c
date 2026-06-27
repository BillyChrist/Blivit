/* USER CODE BEGIN Header */
/** ================================================================
 * Blivit Ground Station
 *
 * @attention
 * Copyright (c) 2026 Geofabrica. All rights reserved.
 *
 * License: MIT License
 *
 * Author: BillyChrist
 *
 * Ground station application entry and loop.
 * ================================================================
 */
/* USER CODE END Header */

#include "ground_station.h"

int main(void)
{
    GroundStation_Init();

    while (1)
    {
        GroundStation_Run();
    }

    return 0;
}

void GroundStation_Init(void)
{
    /* TODO: initialize ground station systems */
}

void GroundStation_Run(void)
{
    /* TODO: poll received data and process telemetry */
}
