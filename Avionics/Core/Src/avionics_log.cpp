#include "avionics_log.h"

#include "avionics_command.h"
#include "serial_debug.h"

#include <Arduino.h>
#include <LittleFS.h>

#include <cstdio>
#include <cstring>

#define AVIONICS_LOG_PATH "/avionics_telem.csv"
#define AVIONICS_LOG_FLUSH_ROWS 64U
#define AVIONICS_LOG_CHUNK_BYTES 64U

static File log_file;
static bool fs_ready = false;
static bool recording = false;
static bool downloading = false;
static uint32_t log_row_count = 0;
static uint32_t log_sequence = 0;
static size_t download_offset = 0;
static uint32_t download_seq = 0;

static bool AvionicsLog_OpenFresh(void)
{
    if (LittleFS.exists(AVIONICS_LOG_PATH))
    {
        LittleFS.remove(AVIONICS_LOG_PATH);
    }

    log_file = LittleFS.open(AVIONICS_LOG_PATH, "w");
    if (!log_file)
    {
        return false;
    }

    static const char *header =
        "sequence,uptime_ms,source,gps_valid,gps_satellites,hdop,latitude,longitude,altitude,"
        "speed,course,vel_n,vel_e,vel_d,climb_rate,roll,pitch,yaw,temperature,imu_frames,imu_bytes,"
        "accel_x,accel_y,accel_z,gyro_x,gyro_y,gyro_z,mag_x,mag_y,mag_z,utc,date\n";
    log_file.print(header);
    log_file.flush();
    log_row_count = 0;
    log_sequence = 0;
    return true;
}

bool AvionicsLog_Init(void)
{
    if (!LittleFS.begin(true))
    {
        SerialDebug_Print("[LOG] LittleFS mount failed");
        fs_ready = false;
        return false;
    }

    fs_ready = true;
    SerialDebug_Print("[LOG] LittleFS ready (max %u KB per session)", AVIONICS_LOG_MAX_BYTES / 1024U);
    return true;
}

bool AvionicsLog_Start(void)
{
    if (!fs_ready || downloading)
    {
        return false;
    }

    if (log_file)
    {
        log_file.close();
    }

    if (!AvionicsLog_OpenFresh())
    {
        SerialDebug_Print("[LOG] failed to create %s", AVIONICS_LOG_PATH);
        return false;
    }

    recording = true;
    SerialDebug_Print("[LOG] recording @ sensor-loop rate (independent of RFD/telemetry cadence)");
    return true;
}

bool AvionicsLog_Stop(void)
{
    if (!recording)
    {
        return false;
    }

    recording = false;
    if (log_file)
    {
        log_file.flush();
        log_file.close();
    }

    SerialDebug_Print("[LOG] recording stopped rows=%lu bytes=%lu",
                      static_cast<unsigned long>(log_row_count),
                      static_cast<unsigned long>(AvionicsLog_GetFileBytes()));
    return true;
}

bool AvionicsLog_IsRecording(void)
{
    return recording;
}

bool AvionicsLog_Append(const TelemetrySample_t *sample)
{
    if (!recording || !sample || !log_file)
    {
        return false;
    }

    if (log_file.size() >= static_cast<int>(AVIONICS_LOG_MAX_BYTES))
    {
        SerialDebug_Print("[LOG] file size limit reached — stopping");
        AvionicsLog_Stop();
        return false;
    }

    log_sequence++;
    char line[512];
    const int written = std::snprintf(
        line,
        sizeof(line),
        "%lu,%lu,avionics,%u,%u,%.1f,%.6f,%.6f,%.1f,%.2f,%.1f,%.2f,%.2f,%.2f,%.2f,"
        "%.2f,%.2f,%.2f,%.2f,%lu,%lu,%.5f,%.5f,%.5f,%.2f,%.2f,%.2f,%.1f,%.1f,%.1f,%s,%s\n",
        static_cast<unsigned long>(log_sequence),
        static_cast<unsigned long>(sample->uptime_ms),
        sample->gps_valid,
        sample->gps_satellites,
        sample->hdop,
        sample->latitude,
        sample->longitude,
        sample->altitude,
        sample->speed,
        sample->course,
        sample->vel_n,
        sample->vel_e,
        sample->vel_d,
        -sample->vel_d,
        sample->roll,
        sample->pitch,
        sample->yaw,
        sample->temperature,
        static_cast<unsigned long>(sample->imu_frames),
        static_cast<unsigned long>(sample->imu_bytes),
        sample->accel_x,
        sample->accel_y,
        sample->accel_z,
        sample->gyro_x,
        sample->gyro_y,
        sample->gyro_z,
        sample->mag_x,
        sample->mag_y,
        sample->mag_z,
        sample->utc_time[0] ? sample->utc_time : "--",
        sample->date[0] ? sample->date : "--");

    if (written <= 0 || written >= static_cast<int>(sizeof(line)))
    {
        return false;
    }

    log_file.print(line);
    log_row_count++;
    if ((log_row_count % AVIONICS_LOG_FLUSH_ROWS) == 0U)
    {
        log_file.flush();
    }
    return true;
}

uint32_t AvionicsLog_GetFileBytes(void)
{
    if (!fs_ready || !LittleFS.exists(AVIONICS_LOG_PATH))
    {
        return 0;
    }

    File f = LittleFS.open(AVIONICS_LOG_PATH, "r");
    if (!f)
    {
        return 0;
    }
    const size_t sz = f.size();
    f.close();
    return static_cast<uint32_t>(sz);
}

uint32_t AvionicsLog_GetRowCount(void)
{
    return log_row_count;
}

bool AvionicsLog_GetStorageInfo(uint32_t *total_bytes, uint32_t *used_bytes, uint32_t *free_bytes)
{
    if (!fs_ready || !total_bytes || !used_bytes || !free_bytes)
    {
        return false;
    }

    const size_t total = LittleFS.totalBytes();
    const size_t used = LittleFS.usedBytes();
    *total_bytes = static_cast<uint32_t>(total);
    *used_bytes = static_cast<uint32_t>(used);
    *free_bytes = static_cast<uint32_t>(total > used ? total - used : 0U);
    return true;
}

bool AvionicsLog_BeginDownload(void)
{
    if (recording || downloading || !fs_ready)
    {
        return false;
    }

    if (!LittleFS.exists(AVIONICS_LOG_PATH) || AvionicsLog_GetFileBytes() == 0U)
    {
        return false;
    }

    downloading = true;
    download_offset = 0;
    download_seq = 0;
    return true;
}

void AvionicsLog_CancelDownload(void)
{
    downloading = false;
}

bool AvionicsLog_IsDownloading(void)
{
    return downloading;
}

bool AvionicsLog_Clear(void)
{
    if (!fs_ready || recording || downloading)
    {
        return false;
    }

    if (log_file)
    {
        log_file.close();
    }

    if (LittleFS.exists(AVIONICS_LOG_PATH) && !LittleFS.remove(AVIONICS_LOG_PATH))
    {
        return false;
    }

    log_row_count = 0;
    log_sequence = 0;
    SerialDebug_Print("[LOG] onboard flight data cleared from flash");
    return true;
}

bool AvionicsLog_SendNextChunk(void)
{
    if (!downloading)
    {
        return false;
    }

    File f = LittleFS.open(AVIONICS_LOG_PATH, "r");
    if (!f)
    {
        downloading = false;
        return false;
    }

    const size_t total = f.size();
    if (download_offset >= total)
    {
        f.close();
        char end_line[48];
        std::snprintf(end_line, sizeof(end_line), "Blivit,LOG,END,%u", static_cast<unsigned>(total));
        Blivit_SendLine(end_line);
        downloading = false;
        return true;
    }

    f.seek(download_offset);
    uint8_t buffer[AVIONICS_LOG_CHUNK_BYTES];
    const size_t to_read = std::min(static_cast<size_t>(AVIONICS_LOG_CHUNK_BYTES), total - download_offset);
    const size_t nbytes = f.read(buffer, to_read);
    f.close();

    if (nbytes == 0)
    {
        char end_line[48];
        std::snprintf(end_line, sizeof(end_line), "Blivit,LOG,END,%u", static_cast<unsigned>(total));
        Blivit_SendLine(end_line);
        downloading = false;
        return true;
    }

    char hex[(AVIONICS_LOG_CHUNK_BYTES * 2U) + 1U];
    size_t hex_index = 0;
    for (size_t i = 0; i < nbytes && (hex_index + 2U) < sizeof(hex); ++i)
    {
        hex_index += static_cast<size_t>(
            std::snprintf(hex + hex_index, sizeof(hex) - hex_index, "%02X", buffer[i]));
    }
    hex[hex_index] = '\0';

    char frame[320];
    std::snprintf(frame, sizeof(frame), "Blivit,LOG,DATA,%u,%s", download_seq, hex);
    Blivit_SendLine(frame);
    download_seq++;
    download_offset += nbytes;
    return true;
}
