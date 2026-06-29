#include "avionics_command.h"

#include "avionics_log.h"
#include "log_queue.h"
#include "main.h"
#include "rfd900.h"
#include "serial_debug.h"

#include <Arduino.h>

#include <cstdarg>
#include <cstdio>
#include <cstring>

static char usb_line[128];
static size_t usb_line_length = 0;
static uint32_t last_download_chunk_ms = 0;

void Blivit_SendLine(const char *line)
{
    if (!line || line[0] == '\0')
    {
        return;
    }

    if (debug_mode)
    {
        Serial.println(line);
    }
    else
    {
        RFD900_SendFrame(line);
    }
}

static void CommandReply(const char *fmt, ...)
{
    char buffer[320];
    va_list args;
    va_start(args, fmt);
    std::vsnprintf(buffer, sizeof(buffer), fmt, args);
    va_end(args);
    Blivit_SendLine(buffer);
}

static void CommandReplyStorageInfo(void)
{
    uint32_t total_bytes = 0;
    uint32_t used_bytes = 0;
    uint32_t free_bytes = 0;
    if (AvionicsLog_GetStorageInfo(&total_bytes, &used_bytes, &free_bytes))
    {
        CommandReply(
            "Blivit,LOG,ACK,Flash storage: %.1f MB total, %.1f MB used, %.1f MB free "
            "(%u KB max per recording session)",
            static_cast<double>(total_bytes) / (1024.0 * 1024.0),
            static_cast<double>(used_bytes) / (1024.0 * 1024.0),
            static_cast<double>(free_bytes) / (1024.0 * 1024.0),
            static_cast<unsigned>(AVIONICS_LOG_MAX_BYTES / 1024U));
    }
    else
    {
        CommandReply("Blivit,LOG,ACK,Flash storage: unavailable (LittleFS not mounted)");
    }
}

bool AvionicsCommand_HandleLine(const char *line)
{
    if (!line || std::strncmp(line, "Blivit,LOG,", 11) != 0)
    {
        return false;
    }

    const char *cmd = line + 11;
    if (std::strcmp(cmd, "START") == 0)
    {
        if (AvionicsLog_Start())
        {
            CommandReply("Blivit,LOG,ACK,Start recording trigger received!");
            CommandReplyStorageInfo();
        }
        else
        {
            CommandReply("Blivit,LOG,ERR,START");
        }
        return true;
    }

    if (std::strcmp(cmd, "STOP") == 0)
    {
        if (AvionicsLog_Stop())
        {
            const uint32_t bytes = AvionicsLog_GetFileBytes();
            const uint32_t rows = AvionicsLog_GetRowCount();
            const float kb = static_cast<float>(bytes) / 1024.0f;
            CommandReply(
                "Blivit,LOG,OK,STOP,%lu,%lu",
                static_cast<unsigned long>(bytes),
                static_cast<unsigned long>(rows));
            CommandReply(
                "Blivit,LOG,ACK,Stop recording trigger received! File size: %.1f KB",
                kb);
        }
        else
        {
            CommandReply("Blivit,LOG,ERR,STOP");
        }
        return true;
    }

    if (std::strcmp(cmd, "STAT") == 0)
    {
        CommandReply(
            "Blivit,LOG,STAT,recording=%u,rows=%lu,bytes=%lu,dropped=%lu",
            AvionicsLog_IsRecording() ? 1U : 0U,
            static_cast<unsigned long>(AvionicsLog_GetRowCount()),
            static_cast<unsigned long>(AvionicsLog_GetFileBytes()),
            static_cast<unsigned long>(LogQueue_GetDroppedCount()));
        CommandReplyStorageInfo();
        return true;
    }

    if (std::strcmp(cmd, "DL") == 0)
    {
        if (AvionicsLog_BeginDownload())
        {
            last_download_chunk_ms = 0;
            CommandReply(
                "Blivit,LOG,OK,DL,%lu",
                static_cast<unsigned long>(AvionicsLog_GetFileBytes()));
            CommandReply(
                "Blivit,LOG,ACK,Download accepted — streaming onboard CSV over serial "
                "(heartbeat slowed to 500 ms during download)");
        }
        else
        {
            CommandReply("Blivit,LOG,ERR,DL");
        }
        return true;
    }

    if (std::strcmp(cmd, "ABORT") == 0)
    {
        AvionicsLog_CancelDownload();
        CommandReply("Blivit,LOG,OK,ABORT");
        return true;
    }

    if (std::strcmp(cmd, "CLEAR") == 0)
    {
        if (AvionicsLog_Clear())
        {
            CommandReply("Blivit,LOG,ACK,Onboard flight data cleared from flash");
            CommandReplyStorageInfo();
        }
        else
        {
            CommandReply("Blivit,LOG,ERR,CLEAR");
        }
        return true;
    }

    CommandReply("Blivit,LOG,ERR,UNKNOWN");
    return true;
}

void AvionicsCommand_PollUsb(void)
{
    if (!debug_mode)
    {
        return;
    }

    while (Serial.available() > 0)
    {
        const char c = static_cast<char>(Serial.read());
        if (c == '\n' || c == '\r')
        {
            if (usb_line_length > 0)
            {
                usb_line[usb_line_length] = '\0';
                AvionicsCommand_HandleLine(usb_line);
                usb_line_length = 0;
            }
            continue;
        }

        if (usb_line_length + 1U < sizeof(usb_line))
        {
            usb_line[usb_line_length++] = c;
        }
    }
}

void AvionicsCommand_Tick(void)
{
    if (!AvionicsLog_IsDownloading())
    {
        return;
    }

    const uint32_t now = millis();
    /* 128 B chunk ≈ 300 B/line @ 115200 → ~12 ms/chunk with margin */
    const uint32_t interval_ms = debug_mode ? 12U : 35U;
    if ((now - last_download_chunk_ms) < interval_ms)
    {
        return;
    }

    last_download_chunk_ms = now;
    AvionicsLog_SendNextChunk();
}
