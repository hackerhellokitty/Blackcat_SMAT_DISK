/*
 * BlackCat SMART — Hardware Core
 * smart.h  —  shared types & function declarations
 *
 * Communicates with disk hardware directly via Win32 IOCTL:
 *   IOCTL_STORAGE_QUERY_PROPERTY  — identity / device type
 *   SMART_RCV_DRIVE_DATA          — ATA SMART attributes (HDD/SSD)
 *   IOCTL_STORAGE_PROTOCOL_COMMAND — NVMe health log
 *   IOCTL_DISK_GET_DRIVE_GEOMETRY_EX — disk size / sector size
 */

#ifndef SMART_H
#define SMART_H

#include <windows.h>
#include <stdint.h>

/* ── Limits ─────────────────────────────────────────── */
#define MAX_DISKS        32
#define MAX_ATTR         64
#define MODEL_LEN        64
#define SERIAL_LEN       32
#define FW_LEN           16

/* ── Disk type ──────────────────────────────────────── */
typedef enum {
    DISK_TYPE_UNKNOWN = 0,
    DISK_TYPE_HDD,
    DISK_TYPE_SSD,      /* SATA SSD  */
    DISK_TYPE_NVME,
} DiskType;

/* ── One SMART attribute (ATA) ──────────────────────── */
typedef struct {
    uint8_t  id;
    char     name[48];
    uint8_t  current;
    uint8_t  worst;
    uint8_t  threshold;
    uint64_t raw;
    int      failing;   /* 1 = below threshold */
} SmartAttr;

/* ── NVMe health snapshot ───────────────────────────── */
typedef struct {
    uint8_t  critical_warning;
    int      temperature_c;     /* composite temp */
    int      percentage_used;   /* 0-100 */
    uint64_t data_units_written;/* 512-byte units × 1000 */
    uint64_t power_on_hours;
    uint32_t power_cycles;
    uint32_t unsafe_shutdowns;
    uint32_t media_errors;
    uint32_t num_err_log_entries;
    int      available_spare;   /* percent */
    int      available_spare_threshold;
} NvmeHealth;

/* ── Full disk info ─────────────────────────────────── */
typedef struct {
    int      index;                 /* 0 = PhysicalDrive0 */
    char     path[32];              /* \\.\PhysicalDriveN  */
    char     model[MODEL_LEN];
    char     serial[SERIAL_LEN];
    char     firmware[FW_LEN];
    DiskType type;
    uint64_t size_bytes;
    uint32_t sector_size;           /* logical sector bytes */
    uint32_t sector_size_physical;

    /* Drive letters on this disk e.g. "C:, D:"  */
    char     drive_letters[32];

    /* SMART status */
    int      smart_passed;          /* 1=pass, 0=fail, -1=unknown */
    int      power_on_hours;

    /* ATA attributes (HDD / SATA SSD) */
    int      attr_count;
    SmartAttr attrs[MAX_ATTR];

    /* NVMe */
    int        has_nvme;
    NvmeHealth nvme;

    /* error string if open failed */
    char     error[128];
} DiskInfo;

/* ── API ────────────────────────────────────────────── */

/*
 * Enumerate all physical disks (PhysicalDrive0..31).
 * Fills disks[], returns count found.
 * Caller must pass array of at least MAX_DISKS DiskInfo structs.
 */
int  disk_enumerate(DiskInfo disks[MAX_DISKS]);

/*
 * Open a disk handle for reading (no write access).
 * Returns INVALID_HANDLE_VALUE on failure.
 */
HANDLE disk_open(int index);

/*
 * Fill disk->model, serial, firmware, type, size via
 * IOCTL_STORAGE_QUERY_PROPERTY.
 */
int  disk_query_identity(HANDLE h, DiskInfo *disk);

/*
 * Fill disk->size_bytes, sector_size via
 * IOCTL_DISK_GET_DRIVE_GEOMETRY_EX.
 */
int  disk_query_geometry(HANDLE h, DiskInfo *disk);

/*
 * Read ATA SMART attributes (HDD / SATA SSD) via
 * SMART_RCV_DRIVE_DATA IOCTL.
 * Returns number of attributes read, -1 on error.
 */
int  smart_read_ata(HANDLE h, DiskInfo *disk);

/*
 * Read NVMe health log via IOCTL_STORAGE_PROTOCOL_COMMAND.
 * Returns 1 on success, 0 on failure.
 */
int  smart_read_nvme(HANDLE h, DiskInfo *disk);

/*
 * Compute health score 0-100 from disk data.
 */
int  disk_health_score(const DiskInfo *disk);

/*
 * Human-readable name for a SMART attribute ID.
 */
const char *smart_attr_name(uint8_t id);

/*
 * Disk type string.
 */
const char *disk_type_str(DiskType t);

/*
 * Generate PDF report for one disk.
 * Returns 1 on success, 0 on failure.
 */
int report_generate(const DiskInfo *disk, const char *out_path);

#endif /* SMART_H */
