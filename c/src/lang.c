/*
 * lang.c  —  Localisation string table  (EN / TH)
 *
 * Thai strings are UTF-8 encoded.
 * ImGui renders UTF-8 natively when a Thai-capable font is loaded;
 * if no Thai font is loaded the strings fall back to romanised labels.
 */

#include "../include/lang.h"
#include <string.h>

LangID g_lang = LANG_EN;

/* ── String table ─────────────────────────────────────────────── */
typedef struct { const char *key; const char *en; const char *th; } Entry;

static const Entry TABLE[] = {
    /* App */
    { "app_name",       "BLACKCAT SMART",           "แบล็คแคท สมาร์ท"       },
    { "app_sub",        "Hardware Analyzer",         "วิเคราะห์ฮาร์ดแวร์"    },

    /* Buttons */
    { "btn_scan",       "  Scan Disks",              "  สแกนดิสก์"            },
    { "btn_scanning",   "  Scanning...",             "  กำลังสแกน..."         },
    { "btn_export",     "  Export PDF",              "  ออกรายงาน PDF"        },

    /* Disk list */
    { "no_disks",       "Click 'Scan Disks' to start", "กด 'สแกนดิสก์' เพื่อเริ่ม" },
    { "drives",         "Drives",                    "ไดรฟ์"                  },
    { "no_drives",      "No drive letters",          "ไม่มีอักษรไดรฟ์"       },

    /* Identity labels */
    { "lbl_type",       "Type",                      "ประเภท"                 },
    { "lbl_model",      "Model",                     "รุ่น"                   },
    { "lbl_serial",     "Serial",                    "ซีเรียล"                },
    { "lbl_firmware",   "Firmware",                  "เฟิร์มแวร์"             },
    { "lbl_capacity",   "Capacity",                  "ความจุ"                 },
    { "lbl_sector",     "Sector Size",               "ขนาดเซกเตอร์"          },
    { "lbl_poweron",    "Power-On",                  "เวลาใช้งาน"             },
    { "lbl_smart",      "SMART Status",              "สถานะ SMART"            },
    { "lbl_verdict",    "Verdict",                   "สรุป"                   },
    { "lbl_drives",     "Drive Letters",             "อักษรไดรฟ์"             },
    { "lbl_health",     "Health",                    "สุขภาพ"                 },

    /* SMART status */
    { "smart_pass",     "PASSED",                    "ผ่าน"                   },
    { "smart_fail",     "FAILED",                    "ล้มเหลว"                },
    { "smart_unk",      "Unknown",                   "ไม่ทราบ"               },

    /* Verdict */
    { "v_good",         "Good",                      "ดี"                     },
    { "v_monitor",      "Monitor",                   "เฝ้าระวัง"              },
    { "v_risk",         "At Risk",                   "เสี่ยง"                 },
    { "v_crit",         "Critical",                  "วิกฤต"                  },

    /* Verdict detail */
    { "vd_good",        "Disk is healthy",           "ดิสก์อยู่ในสภาพดี"      },
    { "vd_monitor",     "Some issues, keep watch",   "พบปัญหาบางส่วน ควรติดตาม" },
    { "vd_risk",        "Back up data, plan replacement", "ควรสำรองข้อมูลด่วน" },
    { "vd_crit",        "Disk may fail soon!",       "ดิสก์อาจพังเร็วๆ นี้!" },

    /* NVMe section */
    { "nvme_title",     "NVMe Health Log",           "ข้อมูลสุขภาพ NVMe"      },
    { "nvme_life",      "Life Remaining",            "อายุการใช้งานเหลือ"     },
    { "nvme_temp",      "Temperature",               "อุณหภูมิ"               },
    { "nvme_written",   "Data Written",              "ข้อมูลที่เขียนสะสม"     },
    { "nvme_cycles",    "Power Cycles",              "รอบเปิด-ปิด"            },
    { "nvme_unsafe",    "Unsafe Shutdowns",          "ปิดเครื่องผิดปกติ"      },
    { "nvme_merr",      "Media Errors",              "ข้อผิดพลาดมีเดีย"       },
    { "nvme_elog",      "Error Log",                 "บันทึกข้อผิดพลาด"       },
    { "nvme_spare",     "Avail. Spare",              "สำรองเหลือ"             },
    { "nvme_err",       "NVMe Health Log unavailable", "ไม่สามารถอ่านข้อมูล NVMe" },

    /* SMART table */
    { "tbl_attrs",      "SMART Attributes",          "แอตทริบิวต์ SMART"      },
    { "tbl_id",         "ID",                        "ID"                     },
    { "tbl_attr",       "Attribute",                 "แอตทริบิวต์"            },
    { "tbl_cur",        "Cur",                       "ปัจจุบัน"               },
    { "tbl_wst",        "Wst",                       "ต่ำสุด"                 },
    { "tbl_raw",        "Raw",                       "ค่าดิบ"                 },

    /* Status bar */
    { "status_ready",   "Ready",                     "พร้อม"                  },
    { "status_found",   "Found %d disk(s)",          "พบ %d ดิสก์"            },
    { "status_saving",  "Generating PDF...",         "กำลังสร้าง PDF..."      },
    { "status_saved",   "Saved: %s",                 "บันทึกแล้ว: %s"         },
    { "status_fail",    "PDF export failed.",        "สร้าง PDF ไม่สำเร็จ"   },

    /* Hours/days */
    { "hours_days",     "%d h  (%d days)",           "%d ชม.  (%d วัน)"       },
};

#define TABLE_SIZE (sizeof(TABLE) / sizeof(TABLE[0]))

/* ── API ─────────────────────────────────────────────────────── */

const char *L(const char *key)
{
    for (int i = 0; i < (int)TABLE_SIZE; i++) {
        if (strcmp(TABLE[i].key, key) == 0)
            return g_lang == LANG_TH ? TABLE[i].th : TABLE[i].en;
    }
    return key; /* fallback: return key itself */
}

void lang_toggle(void)
{
    g_lang = (g_lang == LANG_EN) ? LANG_TH : LANG_EN;
}

const char *lang_name(void)
{
    return g_lang == LANG_EN ? "TH" : "EN";  /* show what pressing will switch TO */
}
