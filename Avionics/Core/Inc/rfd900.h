/* USER CODE BEGIN Header */
/** ================================================================
 * Blivit Avionics Project
 *
 * RFD900 telemetry radio interface.
 * ================================================================
 */
/* USER CODE END Header */

#ifndef RFD900_H
#define RFD900_H

bool RFD900_Init(void);
void RFD900_Process(void);
bool RFD900_SendFrame(const char *payload);
bool RFD900_ReceiveFrame(char *frame, int length);

#endif // RFD900_H
