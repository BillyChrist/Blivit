#ifndef AVIONICS_LOG_H
#define AVIONICS_LOG_H

#include "telemetry_sample.h"

#include <cstddef>
#include <cstdint>

#define AVIONICS_LOG_MAX_BYTES (1536U * 1024U)

bool AvionicsLog_Init(void);
bool AvionicsLog_Start(void);
bool AvionicsLog_Stop(void);
bool AvionicsLog_IsRecording(void);
bool AvionicsLog_Append(const TelemetrySample_t *sample);
bool AvionicsLog_BeginDownload(void);
bool AvionicsLog_SendNextChunk(void);
void AvionicsLog_CancelDownload(void);
bool AvionicsLog_IsDownloading(void);

bool AvionicsLog_Clear(void);

uint32_t AvionicsLog_GetFileBytes(void);
uint32_t AvionicsLog_GetRowCount(void);
bool AvionicsLog_GetStorageInfo(uint32_t *total_bytes, uint32_t *used_bytes, uint32_t *free_bytes);

#endif // AVIONICS_LOG_H
