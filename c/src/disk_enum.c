/*
 * disk_enum.c
 * Enumerate physical disks and query identity/geometry via Win32 IOCTL.
 *
 * IOCTLs used:
 *   IOCTL_STORAGE_QUERY_PROPERTY  (StorageDeviceProperty)
 *   IOCTL_DISK_GET_DRIVE_GEOMETRY_EX
 */

#include "../include/smart.h"
#include <stdio.h>
#include <string.h>
#include <winioctl.h>

/* ── forward declarations ────────────────────────────────────── */
void disk_get_drive_letters(DiskInfo *disk);

/* ── helpers ─────────────────────────────────────────────────── */

HANDLE disk_open(int index)
{
    char path[32];
    snprintf(path, sizeof(path), "\\\\.\\PhysicalDrive%d", index);
    /* GENERIC_WRITE is required for IOCTL_ATA_PASS_THROUGH even in read-only mode.
       We never issue write commands — all ATA commands used are read-only. */
    return CreateFileA(
        path,
        GENERIC_READ | GENERIC_WRITE,
        FILE_SHARE_READ | FILE_SHARE_WRITE,
        NULL,
        OPEN_EXISTING,
        FILE_ATTRIBUTE_NORMAL,
        NULL
    );
}

/* ── identity (model / serial / firmware / bus type) ─────────── */

int disk_query_identity(HANDLE h, DiskInfo *disk)
{
    /* Descriptor header to get required size */
    STORAGE_PROPERTY_QUERY query = {0};
    query.PropertyId = StorageDeviceProperty;
    query.QueryType  = PropertyStandardQuery;

    /* First call: get size */
    STORAGE_DESCRIPTOR_HEADER hdr = {0};
    DWORD bytes = 0;
    if (!DeviceIoControl(h,
            IOCTL_STORAGE_QUERY_PROPERTY,
            &query, sizeof(query),
            &hdr,  sizeof(hdr),
            &bytes, NULL))
        return 0;

    if (hdr.Size == 0 || hdr.Size > 4096)
        return 0;

    /* Second call: get full descriptor */
    BYTE buf[4096] = {0};
    if (!DeviceIoControl(h,
            IOCTL_STORAGE_QUERY_PROPERTY,
            &query, sizeof(query),
            buf,   hdr.Size,
            &bytes, NULL))
        return 0;

    STORAGE_DEVICE_DESCRIPTOR *desc = (STORAGE_DEVICE_DESCRIPTOR *)buf;

    /* Model */
    if (desc->ProductIdOffset && desc->ProductIdOffset < hdr.Size) {
        const char *s = (const char *)buf + desc->ProductIdOffset;
        strncpy(disk->model, s, MODEL_LEN - 1);
        /* trim trailing spaces */
        for (int i = (int)strlen(disk->model) - 1; i >= 0 && disk->model[i] == ' '; i--)
            disk->model[i] = '\0';
    }

    /* Serial */
    if (desc->SerialNumberOffset && desc->SerialNumberOffset < hdr.Size) {
        const char *s = (const char *)buf + desc->SerialNumberOffset;
        strncpy(disk->serial, s, SERIAL_LEN - 1);
        for (int i = (int)strlen(disk->serial) - 1; i >= 0 && disk->serial[i] == ' '; i--)
            disk->serial[i] = '\0';
    }

    /* Firmware */
    if (desc->ProductRevisionOffset && desc->ProductRevisionOffset < hdr.Size) {
        const char *s = (const char *)buf + desc->ProductRevisionOffset;
        strncpy(disk->firmware, s, FW_LEN - 1);
        for (int i = (int)strlen(disk->firmware) - 1; i >= 0 && disk->firmware[i] == ' '; i--)
            disk->firmware[i] = '\0';
    }

    /* Bus type → disk type */
    switch (desc->BusType) {
        case BusTypeNvme:
            disk->type = DISK_TYPE_NVME;
            break;
        case BusTypeSata:
        case BusTypeAta:
        case BusTypeUsb:
            /* SSD vs HDD: check rotation rate later via SMART;
               default to HDD, smart_read_ata() will refine */
            disk->type = DISK_TYPE_HDD;
            break;
        default:
            disk->type = DISK_TYPE_UNKNOWN;
            break;
    }

    return 1;
}

/* ── geometry (size / sector size) ──────────────────────────── */

int disk_query_geometry(HANDLE h, DiskInfo *disk)
{
    DISK_GEOMETRY_EX geo = {0};
    DWORD bytes = 0;
    if (!DeviceIoControl(h,
            IOCTL_DISK_GET_DRIVE_GEOMETRY_EX,
            NULL, 0,
            &geo, sizeof(geo),
            &bytes, NULL))
        return 0;

    disk->size_bytes   = (uint64_t)geo.DiskSize.QuadPart;
    disk->sector_size  = geo.Geometry.BytesPerSector;

    /* Physical sector size from IOCTL_STORAGE_QUERY_PROPERTY (alignment) */
    STORAGE_PROPERTY_QUERY q2 = {0};
    q2.PropertyId = StorageAccessAlignmentProperty;
    q2.QueryType  = PropertyStandardQuery;

    STORAGE_ACCESS_ALIGNMENT_DESCRIPTOR align = {0};
    if (DeviceIoControl(h,
            IOCTL_STORAGE_QUERY_PROPERTY,
            &q2, sizeof(q2),
            &align, sizeof(align),
            &bytes, NULL))
        disk->sector_size_physical = align.BytesPerPhysicalSector;
    else
        disk->sector_size_physical = disk->sector_size;

    return 1;
}

/* ── enumerate all disks ─────────────────────────────────────── */

int disk_enumerate(DiskInfo disks[MAX_DISKS])
{
    int count = 0;

    for (int i = 0; i < MAX_DISKS && count < MAX_DISKS; i++) {
        DiskInfo *d = &disks[count];
        memset(d, 0, sizeof(*d));

        d->index = i;
        snprintf(d->path, sizeof(d->path), "\\\\.\\PhysicalDrive%d", i);
        d->smart_passed = -1; /* unknown until SMART is read */

        HANDLE h = disk_open(i);
        if (h == INVALID_HANDLE_VALUE) {
            /* Drive index gap — stop at first 3 consecutive misses */
            DWORD err = GetLastError();
            if (err == ERROR_FILE_NOT_FOUND || err == ERROR_PATH_NOT_FOUND)
                break;
            /* Access denied or other error — record and skip */
            snprintf(d->error, sizeof(d->error),
                     "Open failed: error %lu", (unsigned long)err);
            count++;
            continue;
        }

        disk_query_identity(h, d);
        disk_query_geometry(h, d);

        /* Read SMART based on detected type.
           For NVMe: try NVMe health log; if both methods fail, note it.
           For ATA/SSD: always attempt ATA SMART read. */
        if (d->type == DISK_TYPE_NVME) {
            d->has_nvme = smart_read_nvme(h, d);
            if (!d->has_nvme)
                snprintf(d->error, sizeof(d->error),
                         "NVMe health log unavailable (driver restriction)");
        } else {
            int n = smart_read_ata(h, d);
            if (n < 0)
                snprintf(d->error, sizeof(d->error),
                         "ATA SMART read failed");
        }

        CloseHandle(h);

        /* Map drive letters to this physical disk */
        disk_get_drive_letters(d);

        count++;
    }

    return count;
}

/* ── Drive letter mapping ────────────────────────────────────────
 *
 * Algorithm:
 *   1. GetLogicalDriveStrings()  → list all drive letters  (C:\, D:\, ...)
 *   2. For each letter open \\.\X:  and call
 *      IOCTL_STORAGE_GET_DEVICE_NUMBER to get PhysicalDrive index.
 *   3. If index matches disk->index, add letter to drive_letters[].
 */
void disk_get_drive_letters(DiskInfo *disk)
{
    disk->drive_letters[0] = '\0';

    char drives[256] = {0};
    DWORD len = GetLogicalDriveStringsA(sizeof(drives) - 1, drives);
    if (!len) return;

    char result[32] = {0};
    int  first = 1;

    for (char *p = drives; *p; p += strlen(p) + 1) {
        /* p is e.g. "C:\" — open as volume root */
        char vol[8];
        snprintf(vol, sizeof(vol), "\\\\.\\%c:", p[0]);

        HANDLE hv = CreateFileA(vol,
            0,  /* no read/write needed for IOCTL_STORAGE_GET_DEVICE_NUMBER */
            FILE_SHARE_READ | FILE_SHARE_WRITE,
            NULL, OPEN_EXISTING, 0, NULL);
        if (hv == INVALID_HANDLE_VALUE) continue;

        STORAGE_DEVICE_NUMBER sdn = {0};
        DWORD returned = 0;
        BOOL ok = DeviceIoControl(hv,
            IOCTL_STORAGE_GET_DEVICE_NUMBER,
            NULL, 0, &sdn, sizeof(sdn), &returned, NULL);
        CloseHandle(hv);

        if (ok && sdn.DeviceType == FILE_DEVICE_DISK &&
            (int)sdn.DeviceNumber == disk->index) {
            char entry[6];
            snprintf(entry, sizeof(entry), first ? "%c:" : ", %c:", p[0]);
            strncat(result, entry, sizeof(result) - strlen(result) - 1);
            first = 0;
        }
    }

    strncpy(disk->drive_letters, result, sizeof(disk->drive_letters) - 1);
}

/* ── utility ─────────────────────────────────────────────────── */

const char *disk_type_str(DiskType t)
{
    switch (t) {
        case DISK_TYPE_HDD:   return "HDD";
        case DISK_TYPE_SSD:   return "SATA SSD";
        case DISK_TYPE_NVME:  return "NVMe SSD";
        default:              return "Unknown";
    }
}
