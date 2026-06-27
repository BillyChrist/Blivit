/* USER CODE BEGIN Header */
/** ================================================================
 * Blivit Avionics Project
 *
 * Component: RFD900x US long-range modem
 *
 * 902–928 MHz modem supporting up to 500 kbps air data rate.
 * USART interface with 3.3 V logic compatibility to ESP32 UART.
 *
 * @attention
 * Copyright (c) 2026 Geofabrica. All rights reserved.
 *
 * License: MIT License
 *
 * Author: BillyChrist
 *
 * RFD900 telemetry radio implementation.
 * ================================================================
 */
/* USER CODE END Header */

#include "rfd900.h"
#include <stdarg.h>
#include <stdio.h>
#include <string.h>

#define RFD900_BUFFER_SIZE 256

static char rfd900_tx_buffer[RFD900_BUFFER_SIZE];
static char rfd900_rx_buffer[RFD900_BUFFER_SIZE];

static bool RFD900_Write(const char *data);
static int RFD900_Read(char *buffer, int maxLength);

bool RFD900_Init(void)
{
    memset(rfd900_tx_buffer, 0, sizeof(rfd900_tx_buffer));
    memset(rfd900_rx_buffer, 0, sizeof(rfd900_rx_buffer));
    return true;
}

bool RFD900_SendFrame(const char *payload)
{
    if (!payload)
    {
        return false;
    }

    int written = snprintf(rfd900_tx_buffer, RFD900_BUFFER_SIZE, "%s\r\n", payload);
    if (written <= 0 || written >= RFD900_BUFFER_SIZE)
    {
        return false;
    }

    return RFD900_Write(rfd900_tx_buffer);
}

bool RFD900_ReceiveFrame(char *frame, int length)
{
    if (!frame || length <= 0)
    {
        return false;
    }

    int received = RFD900_Read(rfd900_rx_buffer, RFD900_BUFFER_SIZE - 1);
    if (received <= 0)
    {
        return false;
    }

    rfd900_rx_buffer[received] = '\0';
    strncpy(frame, rfd900_rx_buffer, length);
    frame[length - 1] = '\0';
    return true;
}

void RFD900_Process(void)
{
    char incoming[RFD900_BUFFER_SIZE];

    if (RFD900_ReceiveFrame(incoming, sizeof(incoming)))
    {
        /* TODO: parse incoming telemetry or acknowledgment frames */
    }

    /* TODO: send telemetry or heartbeat frames when ready.
     * Example: RFD900_SendFrame("TELEMETRY,1,OK");
     */
}

static bool RFD900_Write(const char *data)
{
    /* TODO: replace this stub with actual UART transmit code,
     * for example using Serial1.write() or a hardware-specific wrapper.
     */
    (void)data;
    return false;
}

static int RFD900_Read(char *buffer, int maxLength)
{
    /* TODO: replace this stub with actual UART receive code,
     * for example using Serial1.readBytes() or a hardware-specific wrapper.
     */
    (void)buffer;
    (void)maxLength;
    return 0;
}
