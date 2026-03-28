/*
 * smart_read.c
 * Read SMART data directly from hardware via Win32 IOCTL.
 *
 * ATA/SATA (HDD & SSD):
 *   IOCTL_ATA_PASS_THROUGH  →  ATA SMART READ DATA command (0xB0 / 0xD0)
 *   IOCTL_ATA_PASS_THROUGH  →  ATA SMART READ THRESHOLDS  (0xB0 / 0xD1)
 *   IOCTL_ATA_PASS_THROUGH  →  ATA RETURN SMART STATUS    (0xB0 / 0xDA)
 *   IOCTL_ATA_PASS_THROUGH  →  ATA IDENTIFY DEVICE        (0xEC)
 *
 * NVMe:
 *   IOCTL_STORAGE_PROTOCOL_COMMAND  →  NVMe Get Log Page (0x02) Health/Info
 */

#include "../include/smart.h"
#include <stdio.h>
#include <string.h>
#include <winioctl.h>
#include <ntddscsi.h>   /* ATA_PASS_THROUGH_EX */
#include <nvme.h>       /* NVME_COMMAND, NVME_HEALTH_INFO_LOG */

/* ════════════════════════════════════════════════════════════════
 *  ATA SMART  (HDD / SATA SSD)
 * ════════════════════════════════════════════════════════════════ */

#define ATA_CMD_SMART           0xB0
#define ATA_SMART_READ_DATA     0xD0
#define ATA_SMART_READ_THRESH   0xD1
#define ATA_SMART_RETURN_STATUS 0xDA
#define ATA_CMD_IDENTIFY        0xEC
#define ATA_SMART_LBA_MID       0x4F
#define ATA_SMART_LBA_HIGH      0xC2

/* Raw SMART data sector is 512 bytes:
   6-byte attribute entry × 30 attributes starting at offset 2 */
#define SMART_ATTR_OFFSET   2
#define SMART_ATTR_SIZE     12
#define SMART_ATTR_COUNT    30

#pragma pack(push, 1)
typedef struct {
    BYTE  id;
    WORD  flags;
    BYTE  current;
    BYTE  worst;
    BYTE  raw[6];
    BYTE  reserved;
} RawSmartAttr;

typedef struct {
    BYTE  id;
    BYTE  reserved;
    BYTE  threshold;
} RawSmartThreshold;
#pragma pack(pop)

/* Build and send one ATA PASS-THROUGH command, return 1 on success */
static int ata_pass_through(HANDLE h,
                             BYTE cmd, BYTE feature,
                             BYTE lba_low, BYTE lba_mid, BYTE lba_high,
                             void *buf, DWORD buf_size,
                             int data_direction) /* 0=none,1=in,2=out */
{
#define APT_BUF_OFFSET 8  /* sizeof(ATA_PASS_THROUGH_EX) padded to 8 */

    DWORD struct_size = sizeof(ATA_PASS_THROUGH_EX);
    DWORD total      = struct_size + buf_size;
    BYTE *raw_buf    = (BYTE *)calloc(1, total);
    if (!raw_buf) return 0;

    ATA_PASS_THROUGH_EX *apt = (ATA_PASS_THROUGH_EX *)raw_buf;
    apt->Length             = sizeof(ATA_PASS_THROUGH_EX);
    apt->AtaFlags           = (data_direction == 1) ? ATA_FLAGS_DATA_IN
                            : (data_direction == 2) ? ATA_FLAGS_DATA_OUT
                            : 0;
    apt->DataTransferLength = buf_size;
    apt->DataBufferOffset   = struct_size;
    apt->TimeOutValue       = 10;

    apt->CurrentTaskFile[0] = feature;
    apt->CurrentTaskFile[1] = 0;        /* sector count */
    apt->CurrentTaskFile[2] = lba_low;
    apt->CurrentTaskFile[3] = lba_mid;
    apt->CurrentTaskFile[4] = lba_high;
    apt->CurrentTaskFile[5] = 0;        /* device */
    apt->CurrentTaskFile[6] = cmd;

    /* Copy outgoing data */
    if (data_direction == 2 && buf)
        memcpy(raw_buf + struct_size, buf, buf_size);

    DWORD returned = 0;
    BOOL ok = DeviceIoControl(h,
        IOCTL_ATA_PASS_THROUGH,
        raw_buf, total,
        raw_buf, total,
        &returned, NULL);

    if (ok && data_direction == 1 && buf)
        memcpy(buf, raw_buf + struct_size, buf_size);

    free(raw_buf);
    return ok ? 1 : 0;
}

/* Read SMART status: sets disk->smart_passed */
static void smart_check_status(HANDLE h, DiskInfo *disk)
{
    ATA_PASS_THROUGH_EX apt = {0};
    apt.Length             = sizeof(apt);
    apt.AtaFlags           = 0;
    apt.DataTransferLength = 0;
    apt.DataBufferOffset   = sizeof(apt);
    apt.TimeOutValue       = 10;
    apt.CurrentTaskFile[0] = ATA_SMART_RETURN_STATUS;
    apt.CurrentTaskFile[3] = ATA_SMART_LBA_MID;
    apt.CurrentTaskFile[4] = ATA_SMART_LBA_HIGH;
    apt.CurrentTaskFile[6] = ATA_CMD_SMART;

    DWORD returned = 0;
    if (!DeviceIoControl(h, IOCTL_ATA_PASS_THROUGH,
                         &apt, sizeof(apt),
                         &apt, sizeof(apt),
                         &returned, NULL)) {
        disk->smart_passed = -1;
        return;
    }

    /* ATA spec: if LBA_MID=0x4F and LBA_HIGH=0xC2 → threshold not exceeded */
    BYTE mid  = apt.CurrentTaskFile[3];
    BYTE high = apt.CurrentTaskFile[4];
    disk->smart_passed = (mid == 0x4F && high == 0xC2) ? 1 : 0;
}

/* Read SMART attributes and thresholds */
int smart_read_ata(HANDLE h, DiskInfo *disk)
{
    /* ── SMART READ DATA (512 bytes) ── */
    BYTE data[512] = {0};
    if (!ata_pass_through(h, ATA_CMD_SMART, ATA_SMART_READ_DATA,
                          0, ATA_SMART_LBA_MID, ATA_SMART_LBA_HIGH,
                          data, sizeof(data), 1))
        return -1;

    /* ── SMART READ THRESHOLDS (512 bytes) ── */
    BYTE thresh[512] = {0};
    ata_pass_through(h, ATA_CMD_SMART, ATA_SMART_READ_THRESH,
                     0, ATA_SMART_LBA_MID, ATA_SMART_LBA_HIGH,
                     thresh, sizeof(thresh), 1);

    /* ── Parse attributes ── */
    int count = 0;
    for (int i = 0; i < SMART_ATTR_COUNT && count < MAX_ATTR; i++) {
        int off = SMART_ATTR_OFFSET + i * SMART_ATTR_SIZE;
        RawSmartAttr  *a = (RawSmartAttr  *)(data   + off);
        RawSmartThreshold *t = (RawSmartThreshold *)(thresh + SMART_ATTR_OFFSET + i * 12);

        if (a->id == 0) continue;

        SmartAttr *sa = &disk->attrs[count++];
        sa->id        = a->id;
        sa->current   = a->current;
        sa->worst     = a->worst;
        sa->threshold = t->threshold;
        sa->failing   = (a->current <= t->threshold && t->threshold > 0) ? 1 : 0;

        /* Raw value: 6 bytes little-endian */
        sa->raw = 0;
        for (int b = 5; b >= 0; b--)
            sa->raw = (sa->raw << 8) | a->raw[b];

        strncpy(sa->name, smart_attr_name(a->id), sizeof(sa->name) - 1);

        /* Extract power-on hours from attr 9 */
        if (a->id == 9)
            disk->power_on_hours = (int)(sa->raw & 0xFFFFFFFF);

        /* Rotation rate (attr 0x01 = 1 is for SSD — check ID 3 RPM) */
    }
    disk->attr_count = count;

    /* ── Check SMART pass/fail ── */
    smart_check_status(h, disk);

    /* ── Detect SSD via SMART attr 1 (Raw Read Error Rate) absence
          and attr 204 / Wear Leveling Count presence ──
       Simpler: use IDENTIFY DEVICE word 217 (nominal media rotation rate)
       0x0001 = SSD, otherwise HDD RPM                                    */
    BYTE id_data[512] = {0};
    if (ata_pass_through(h, ATA_CMD_IDENTIFY, 0, 0, 0, 0,
                         id_data, sizeof(id_data), 1)) {
        WORD rotation = ((WORD *)id_data)[217];
        if (rotation == 0x0001)
            disk->type = DISK_TYPE_SSD;
        else if (rotation > 0x0001 && rotation != 0xFFFF)
            disk->type = DISK_TYPE_HDD;
    }

    return count;
}

/* ════════════════════════════════════════════════════════════════
 *  NVMe  — SMART / Health Information Log
 *
 *  Method A (primary):
 *    IOCTL_STORAGE_QUERY_PROPERTY + StorageDeviceProtocolSpecificProperty
 *    Works on ALL NVMe drivers (inbox, WD, Samsung, Intel, etc.)
 *
 *  Method B (fallback):
 *    IOCTL_STORAGE_PROTOCOL_COMMAND  (Get Log Page 0x02)
 *    Requires adapter-level pass-through; some drivers block it.
 * ════════════════════════════════════════════════════════════════ */

#define NVME_LOG_PAGE_SIZE  512

/* Parse 512-byte NVMe Health Information Log into disk->nvme */
static void nvme_parse_health_log(const BYTE *log, DiskInfo *disk)
{
    /* NVMe Base Spec 5.14.1.2 — SMART / Health Information (Log Page 02h)
       All offsets are byte offsets from start of log page.              */

    disk->nvme.critical_warning          = log[0];

    /* Composite Temperature: bytes 1-2, unsigned, in Kelvin */
    WORD temp_k = (WORD)log[1] | ((WORD)log[2] << 8);
    disk->nvme.temperature_c             = (temp_k > 0) ? (int)temp_k - 273 : 0;

    disk->nvme.available_spare           = log[3];   /* percent */
    disk->nvme.available_spare_threshold = log[4];   /* percent */
    disk->nvme.percentage_used           = log[5];   /* percent */

    /* Data Units Written: bytes 48-63 (128-bit LE), use low 64 bits */
    memcpy(&disk->nvme.data_units_written,  log + 48,  8);

    /* Power Cycles: bytes 112-127 (128-bit LE), low 32 bits */
    memcpy(&disk->nvme.power_cycles,        log + 112, 4);

    /* Power On Hours: bytes 128-143 (128-bit LE), low 64 bits */
    uint64_t poh = 0;
    memcpy(&poh, log + 128, 8);
    disk->nvme.power_on_hours  = poh;
    disk->power_on_hours       = (int)(poh & 0x7FFFFFFF);

    /* Unsafe Shutdowns: bytes 144-159, low 32 bits */
    memcpy(&disk->nvme.unsafe_shutdowns,    log + 144, 4);

    /* Media and Data Integrity Errors: bytes 160-175, low 32 bits */
    memcpy(&disk->nvme.media_errors,        log + 160, 4);

    /* Number of Error Information Log Entries: bytes 176-191, low 32 bits */
    memcpy(&disk->nvme.num_err_log_entries, log + 176, 4);

    disk->smart_passed = (disk->nvme.critical_warning == 0) ? 1 : 0;
    disk->type         = DISK_TYPE_NVME;
}

/* Method A: StorageDeviceProtocolSpecificProperty — most compatible */
static int nvme_read_via_query_property(HANDLE h, DiskInfo *disk)
{
    DWORD buf_size = sizeof(STORAGE_PROPERTY_QUERY)
                   + sizeof(STORAGE_PROTOCOL_SPECIFIC_DATA)
                   + NVME_LOG_PAGE_SIZE;

    BYTE *buf = (BYTE *)calloc(1, buf_size);
    if (!buf) return 0;

    STORAGE_PROPERTY_QUERY        *query = (STORAGE_PROPERTY_QUERY *)buf;
    STORAGE_PROTOCOL_SPECIFIC_DATA *psd  =
        (STORAGE_PROTOCOL_SPECIFIC_DATA *)(buf + sizeof(STORAGE_PROPERTY_QUERY)
                                               - sizeof(DWORD)); /* overlap AdditionalParameters */

    query->PropertyId = StorageDeviceProtocolSpecificProperty;
    query->QueryType  = PropertyStandardQuery;

    psd->ProtocolType               = ProtocolTypeNvme;
    psd->DataType                   = NVMeDataTypeLogPage;
    psd->ProtocolDataRequestValue   = 0x02;  /* Log Page: SMART/Health */
    psd->ProtocolDataRequestSubValue= 0;
    psd->ProtocolDataOffset         = sizeof(STORAGE_PROTOCOL_SPECIFIC_DATA);
    psd->ProtocolDataLength         = NVME_LOG_PAGE_SIZE;

    DWORD returned = 0;
    BOOL ok = DeviceIoControl(h,
        IOCTL_STORAGE_QUERY_PROPERTY,
        buf, buf_size,
        buf, buf_size,
        &returned, NULL);

    if (ok && returned > sizeof(STORAGE_PROPERTY_QUERY)) {
        BYTE *log = (BYTE *)psd + psd->ProtocolDataOffset;
        nvme_parse_health_log(log, disk);
        free(buf);
        return 1;
    }

    free(buf);
    return 0;
}

/* Method B: IOCTL_STORAGE_PROTOCOL_COMMAND (adapter pass-through) */
static int nvme_read_via_protocol_command(HANDLE h, DiskInfo *disk)
{
    DWORD cmd_len = sizeof(STORAGE_PROTOCOL_COMMAND)
                  + sizeof(NVME_COMMAND)
                  + NVME_LOG_PAGE_SIZE;

    BYTE *buf = (BYTE *)calloc(1, cmd_len);
    if (!buf) return 0;

    STORAGE_PROTOCOL_COMMAND *spc   = (STORAGE_PROTOCOL_COMMAND *)buf;
    spc->Version                    = STORAGE_PROTOCOL_STRUCTURE_VERSION;
    spc->Length                     = sizeof(STORAGE_PROTOCOL_COMMAND);
    spc->ProtocolType               = ProtocolTypeNvme;
    spc->Flags                      = STORAGE_PROTOCOL_COMMAND_FLAG_ADAPTER_REQUEST;
    spc->CommandLength              = sizeof(NVME_COMMAND);
    spc->DataFromDeviceTransferLength = NVME_LOG_PAGE_SIZE;
    spc->TimeOutValue               = 10;
    spc->CommandSpecific            = STORAGE_PROTOCOL_SPECIFIC_NVME_ADMIN_COMMAND;
    spc->DataFromDeviceBufferOffset = sizeof(STORAGE_PROTOCOL_COMMAND)
                                    + sizeof(NVME_COMMAND);

    NVME_COMMAND *cmd = (NVME_COMMAND *)(buf + sizeof(STORAGE_PROTOCOL_COMMAND));
    cmd->CDW0.OPC = 0x02;  /* Get Log Page */
    cmd->u.GETLOGPAGE.CDW10.AsUlong =
        (ULONG)(0x02 | ((NVME_LOG_PAGE_SIZE / 4 - 1) << 16));

    DWORD returned = 0;
    BOOL ok = DeviceIoControl(h,
        IOCTL_STORAGE_PROTOCOL_COMMAND,
        buf, cmd_len, buf, cmd_len, &returned, NULL);

    if (ok) {
        BYTE *log = buf + spc->DataFromDeviceBufferOffset;
        nvme_parse_health_log(log, disk);
        free(buf);
        return 1;
    }

    free(buf);
    return 0;
}

int smart_read_nvme(HANDLE h, DiskInfo *disk)
{
    /* Try the most-compatible method first */
    if (nvme_read_via_query_property(h, disk))   return 1;
    if (nvme_read_via_protocol_command(h, disk)) return 1;
    return 0;
}

/* ════════════════════════════════════════════════════════════════
 *  Health score  0-100
 * ════════════════════════════════════════════════════════════════ */

/* Find raw value of a specific SMART attr ID, returns -1 if not found */
static int64_t _attr_raw(const DiskInfo *disk, uint8_t id)
{
    for (int i = 0; i < disk->attr_count; i++)
        if (disk->attrs[i].id == id)
            return (int64_t)disk->attrs[i].raw;
    return -1;
}

/* Debug: print score deductions (define SMART_DEBUG to enable) */
#ifdef SMART_DEBUG
#define DBG(msg, val) printf("  [score] %-40s score=%d\n", msg, val)
#else
#define DBG(msg, val) (void)0
#endif

int disk_health_score(const DiskInfo *disk)
{
    int score = 100;

    /* SMART overall status */
    if (disk->smart_passed == 0)  score -= 60;

    if (disk->has_nvme) {
        /* ── NVMe ── */
        int used = disk->nvme.percentage_used;
        if (used >= 90)       score -= 40;
        else if (used >= 80)  score -= 15;

        int temp = disk->nvme.temperature_c;
        if (temp >= 70)       score -= 20;
        else if (temp >= 55)  score -= 5;

        if (disk->nvme.media_errors > 0)    score -= 30;
        if (disk->nvme.num_err_log_entries > 0) score -= 5;
        if (disk->nvme.unsafe_shutdowns > 50)   score -= 5;
        if (disk->nvme.critical_warning & 0x04) score -= 15; /* reliability degraded */

    } else {
        /* ── ATA (HDD / SATA SSD) ──
           Mirror Python logic: check raw values, not just threshold crossing */

        int64_t v;

        /* Reallocated Sectors (ID 5) — any > 0 is bad */
        v = _attr_raw(disk, 5);
        if (v > 0) score -= 35;

        /* Current Pending Sectors (ID 197) */
        v = _attr_raw(disk, 197);
        if (v > 0) score -= 15;

        /* Offline Uncorrectable (ID 198) */
        v = _attr_raw(disk, 198);
        if (v > 0) score -= 25;

        /* Reported Uncorrectable (ID 187) */
        v = _attr_raw(disk, 187);
        if (v > 0) score -= 20;

        /* Reallocation Event Count (ID 196) */
        v = _attr_raw(disk, 196);
        if (v > 0) score -= 20;

        /* Temperature (ID 194 or 190)
           Raw is encoded as: byte0=current, byte1=min, byte2=max (vendor varies)
           Low byte is current temperature in Celsius */
        v = _attr_raw(disk, 194);
        if (v < 0) v = _attr_raw(disk, 190);
        if (v >= 0) {
            /* Extract low byte — current temperature */
            int temp = (int)(v & 0xFF);
            /* Sanity: if > 100 the encoding is different, use current value field */
            if (temp > 100 || temp <= 0) {
                /* fallback: find the attr and use current value (normalized) */
                for (int i = 0; i < disk->attr_count; i++) {
                    if (disk->attrs[i].id == 194 || disk->attrs[i].id == 190) {
                        /* current field is normalized (higher=cooler for temp attrs)
                           actual temp = 100 - current roughly, but not reliable
                           Skip penalty if we can't determine */
                        temp = -1;
                        break;
                    }
                }
            }
            if (temp >= 70)      score -= 20;
            else if (temp >= 55) score -= 5;
        }

        /* Command Timeout (ID 188)
           Seagate encodes raw as: low 16 bits = count this power cycle,
                                   bits 16-31  = lifetime total count.
           Python smartctl reports the lifetime count in the raw string.
           Only penalize if lifetime count (bits 16-31) > 1 to avoid noise. */
        v = _attr_raw(disk, 188);
        if (v > 0) {
            uint32_t lifetime = (uint32_t)((v >> 16) & 0xFFFF);
            if (lifetime > 1) score -= 10;
            /* else: single timeout event is noise, no penalty (matches Python) */
        }

        /* Power-on hours (ID 9) */
        v = _attr_raw(disk, 9);
        if (v < 0 && disk->power_on_hours > 0) v = disk->power_on_hours;
        if (v >= 40000)      score -= 25;
        else if (v >= 20000) score -= 10;

        /* Seek Error Rate (ID 7)
           Seagate 48-bit encoding: bits 47-32 = error count, bits 31-0 = total seeks.
           A high raw value on Seagate is NORMAL (total seeks is large).
           True errors = high 16 bits of raw value.
           For non-Seagate the raw is a simple error count.
           We check the high 16 bits for actual errors. */
        v = _attr_raw(disk, 7);
        if (v > 0) {
            uint32_t seek_errors = (uint32_t)((v >> 32) & 0xFFFF);
            if (seek_errors > 0) score -= 10;
        }

        /* Spin Retry Count (ID 10) */
        v = _attr_raw(disk, 10);
        if (v > 0) score -= 10;
    }

    return score < 0 ? 0 : (score > 100 ? 100 : score);
}

/* ════════════════════════════════════════════════════════════════
 *  SMART attribute name table
 * ════════════════════════════════════════════════════════════════ */

const char *smart_attr_name(uint8_t id)
{
    switch (id) {
        case 1:   return "Raw Read Error Rate";
        case 2:   return "Throughput Performance";
        case 3:   return "Spin-Up Time";
        case 4:   return "Start/Stop Count";
        case 5:   return "Reallocated Sectors Count";
        case 7:   return "Seek Error Rate";
        case 8:   return "Seek Time Performance";
        case 9:   return "Power-On Hours";
        case 10:  return "Spin Retry Count";
        case 11:  return "Recalibration Retries";
        case 12:  return "Device Power Cycle Count";
        case 13:  return "Soft Read Error Rate";
        case 22:  return "Current Helium Level";
        case 100: return "Erase/Program Cycles";
        case 160: return "Uncorrectable Sector Count";
        case 161: return "Valid Spare Block Count";
        case 163: return "Initial Bad Block Count";
        case 164: return "Total Erase Count";
        case 165: return "Maximum Erase Count";
        case 166: return "Minimum Erase Count";
        case 167: return "Average Erase Count";
        case 168: return "Max NAND Erase Count";
        case 169: return "Remaining Life Percentage";
        case 170: return "Available Reserved Space";
        case 171: return "Program Fail Count";
        case 172: return "Erase Fail Count";
        case 173: return "Wear Leveling Count";
        case 174: return "Unexpected Power Loss Count";
        case 175: return "Program Fail Count (Chip)";
        case 176: return "Erase Fail Count (Chip)";
        case 177: return "Wear Range Delta";
        case 179: return "Used Reserved Block Count (Total)";
        case 180: return "Unused Reserved Block Count (Total)";
        case 181: return "Program Fail Count (Total)";
        case 182: return "Erase Fail Count (Total)";
        case 183: return "Runtime Bad Block";
        case 184: return "End-to-End Error Detection";
        case 187: return "Reported Uncorrectable Errors";
        case 188: return "Command Timeout";
        case 189: return "High Fly Writes";
        case 190: return "Airflow Temperature";
        case 191: return "G-Sense Error Rate";
        case 192: return "Unsafe Shutdown Count";
        case 193: return "Load/Unload Cycle Count";
        case 194: return "Temperature";
        case 195: return "Hardware ECC Recovered";
        case 196: return "Reallocation Event Count";
        case 197: return "Current Pending Sector Count";
        case 198: return "Uncorrectable Sector Count";
        case 199: return "UltraDMA CRC Error Count";
        case 200: return "Multi-Zone Error Rate";
        case 201: return "Soft Read Error Rate";
        case 202: return "Data Address Mark Errors";
        case 203: return "Run Out Cancel";
        case 204: return "Soft ECC Correction";
        case 205: return "Thermal Asperity Rate";
        case 206: return "Flying Height";
        case 207: return "Spin High Current";
        case 208: return "Spin Buzz";
        case 209: return "Offline Seek Performance";
        case 220: return "Disk Shift";
        case 221: return "G-Sense Error Rate";
        case 222: return "Loaded Hours";
        case 223: return "Load/Unload Retry Count";
        case 224: return "Load Friction";
        case 225: return "Load/Unload Cycle Count";
        case 226: return "Load-In Time";
        case 227: return "Torque Amplification Count";
        case 228: return "Power-Off Retract Cycle";
        case 230: return "GMR Head Amplitude";
        case 231: return "SSD Life Left";
        case 232: return "Endurance Remaining";
        case 233: return "Media Wearout Indicator";
        case 234: return "Average Erase Count";
        case 235: return "Good Block Count";
        case 240: return "Head Flying Hours";
        case 241: return "Total LBAs Written";
        case 242: return "Total LBAs Read";
        case 243: return "Total LBAs Written Expanded";
        case 244: return "Total LBAs Read Expanded";
        case 249: return "NAND Writes (1GiB)";
        case 250: return "Read Error Retry Rate";
        case 251: return "Minimum Spares Remaining";
        case 252: return "Newly Added Bad Flash Block";
        case 254: return "Free Fall Protection";
        default:  return "Vendor Specific";
    }
}
