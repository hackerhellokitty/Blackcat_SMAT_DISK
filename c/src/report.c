/*
 * report.c  —  BlackCat SMART  PDF Report Generator
 *
 * Uses PDFGen (single-file, public domain) — pdfgen/pdfgen.h
 *
 * Page layout (A4 portrait, points):
 *   Header bar  : top blue strip
 *   Summary box : score + verdict + identity
 *   Alerts      : risk/warning lines
 *   SMART table : attribute rows
 *   Footer      : timestamp + page number
 */

#include "../include/smart.h"
#include "../pdfgen/pdfgen.h"

#include <stdio.h>
#include <string.h>
#include <time.h>
#include <math.h>

/* ── Page constants (points, origin = bottom-left) ─────── */
#define PW   PDF_A4_WIDTH          /* 595 pt */
#define PH   PDF_A4_HEIGHT         /* 842 pt */
#define ML   40.0f                 /* margin left  */
#define MR   40.0f                 /* margin right */
#define CW   (PW - ML - MR)       /* content width */

/* ── Colours ────────────────────────────────────────────── */
#define C_BLUE    PDF_RGB(0x00, 0x66, 0xCC)
#define C_DBLUE   PDF_RGB(0x00, 0x33, 0x88)
#define C_GREEN   PDF_RGB(0x16, 0xa3, 0x4a)
#define C_AMBER   PDF_RGB(0xd9, 0x77, 0x06)
#define C_RED     PDF_RGB(0xdc, 0x26, 0x26)
#define C_DARK    PDF_RGB(0x11, 0x18, 0x27)
#define C_GRAY    PDF_RGB(0x4b, 0x55, 0x63)
#define C_LGRAY   PDF_RGB(0xd1, 0xd5, 0xdb)
#define C_HBG     PDF_RGB(0xe5, 0xe7, 0xeb)   /* table header bg */
#define C_ROW1    PDF_RGB(0xFF, 0xFF, 0xFF)
#define C_ROW2    PDF_RGB(0xf9, 0xfa, 0xfb)
#define C_WHITE   PDF_WHITE

/* ── Helpers ────────────────────────────────────────────── */

/* PDFGen origin is bottom-left; we work top-down, so convert */
static float y2pt(float y_from_top) { return PH - y_from_top; }

static uint32_t score_col(int score)
{
    if (score >= 80) return C_GREEN;
    if (score >= 50) return C_AMBER;
    return C_RED;
}

static const char *score_verdict(int score)
{
    if (score >= 85) return "Good  — disk is healthy";
    if (score >= 60) return "Monitor  — some issues found, keep watch";
    if (score >= 30) return "At Risk  — back up data, plan replacement";
    return              "Critical — disk may fail, back up immediately!";
}

static void size_str(uint64_t bytes, char *buf, int n)
{
    double gb = (double)bytes / (1024.0 * 1024.0 * 1024.0);
    if (gb >= 1000.0) snprintf(buf, n, "%.1f TB", gb / 1024.0);
    else              snprintf(buf, n, "%.0f GB", gb);
}

/* Draw a horizontal rule */
static void hrule(struct pdf_doc *pdf, struct pdf_object *pg,
                  float y, float thick, uint32_t col)
{
    pdf_add_line(pdf, pg, ML, y2pt(y), ML + CW, y2pt(y), thick, col);
}

/* Draw filled rectangle (top-down coords) */
static void filled_rect(struct pdf_doc *pdf, struct pdf_object *pg,
                        float x, float y, float w, float h, uint32_t col)
{
    pdf_add_filled_rectangle(pdf, pg, x, y2pt(y + h), w, h, 0, col, col);
}

/* Draw text at top-down Y, left-aligned */
static void text_at(struct pdf_doc *pdf, struct pdf_object *pg,
                    float x, float y, float sz, uint32_t col, const char *s)
{
    pdf_set_font(pdf, "Helvetica");
    pdf_add_text(pdf, pg, s, sz, x, y2pt(y + sz * 0.75f), col);
}

static void text_bold(struct pdf_doc *pdf, struct pdf_object *pg,
                      float x, float y, float sz, uint32_t col, const char *s)
{
    pdf_set_font(pdf, "Helvetica-Bold");
    pdf_add_text(pdf, pg, s, sz, x, y2pt(y + sz * 0.75f), col);
    pdf_set_font(pdf, "Helvetica");
}

/* Two-column label: value row */
static void kv_row(struct pdf_doc *pdf, struct pdf_object *pg,
                   float y, const char *key, const char *val,
                   uint32_t val_col, int even)
{
    float row_h = 14.0f;
    filled_rect(pdf, pg, ML, y, CW, row_h, even ? C_ROW2 : C_ROW1);
    text_bold(pdf, pg, ML + 4, y + 2, 8, C_GRAY, key);
    text_at  (pdf, pg, ML + 130, y + 2, 8, val_col, val);
}

/* ── Main export function ───────────────────────────────── */
int report_generate(const DiskInfo *disk, const char *out_path)
{
    struct pdf_info info = {
        .creator  = "BlackCat SMART",
        .producer = "BlackCat SMART C edition",
        .title    = "Disk Health Report",
        .author   = "BlackCat SMART",
        .subject  = "SMART Disk Health Report",
        .date     = "",
    };

    struct pdf_doc *pdf = pdf_create(PW, PH, &info);
    if (!pdf) return 0;

    struct pdf_object *pg = pdf_append_page(pdf);
    pdf_set_font(pdf, "Helvetica");

    int   score   = disk_health_score(disk);
    float cursor  = 0.0f;   /* tracks Y from top */

    /* ══════════════════════════════════════════════════════
     *  HEADER BAR
     * ══════════════════════════════════════════════════════ */
    filled_rect(pdf, pg, 0, 0, PW, 44, C_BLUE);
    text_bold(pdf, pg, ML, 10, 16, C_WHITE, "BlackCat SMART  -  Disk Health Report");

    char ts[48];
    time_t now = time(NULL);
    struct tm *tm_info = localtime(&now);
    strftime(ts, sizeof(ts), "Generated: %Y-%m-%d  %H:%M", tm_info);
    text_at(pdf, pg, ML, 28, 8, PDF_RGB(0xBB,0xDD,0xFF), ts);

    cursor = 52.0f;

    /* ══════════════════════════════════════════════════════
     *  HEALTH SCORE SUMMARY BOX
     * ══════════════════════════════════════════════════════ */
    filled_rect(pdf, pg, ML, cursor, CW, 56, C_HBG);
    pdf_add_rectangle(pdf, pg, ML, y2pt(cursor + 56), CW, 56, 0.5f, C_LGRAY);

    /* Big score number */
    char score_buf[16]; snprintf(score_buf, sizeof(score_buf), "%d", score);
    pdf_set_font(pdf, "Helvetica-Bold");
    pdf_add_text(pdf, pg, score_buf, 36,
                 ML + 8, y2pt(cursor + 38), score_col(score));

    pdf_set_font(pdf, "Helvetica");
    pdf_add_text(pdf, pg, "/ 100", 10,
                 ML + 8, y2pt(cursor + 52), C_GRAY);

    /* Verdict */
    text_bold(pdf, pg, ML + 70, cursor + 10, 11, score_col(score),
              score_verdict(score));

    /* Disk identity */
    char identity[128];
    snprintf(identity, sizeof(identity), "%s  |  %s",
             disk->model[0]  ? disk->model  : "Unknown",
             disk->serial[0] ? disk->serial : "N/A");
    text_at(pdf, pg, ML + 70, cursor + 26, 9, C_DARK, identity);

    char sz[16]; size_str(disk->size_bytes, sz, sizeof(sz));
    char identity2[128];
    snprintf(identity2, sizeof(identity2), "%s  |  %s  |  FW: %s",
             disk_type_str(disk->type), sz,
             disk->firmware[0] ? disk->firmware : "N/A");
    text_at(pdf, pg, ML + 70, cursor + 40, 9, C_GRAY, identity2);

    cursor += 64.0f;

    /* ══════════════════════════════════════════════════════
     *  IDENTITY TABLE
     * ══════════════════════════════════════════════════════ */
    text_bold(pdf, pg, ML, cursor + 2, 10, C_BLUE, "DISK IDENTITY");
    hrule(pdf, pg, cursor + 14, 0.5f, C_BLUE);
    cursor += 18.0f;

    char poh[48];
    if (disk->power_on_hours > 0)
        snprintf(poh, sizeof(poh), "%d h  (%d days)",
                 disk->power_on_hours, disk->power_on_hours / 24);
    else snprintf(poh, sizeof(poh), "N/A");

    char sectors[64];
    snprintf(sectors, sizeof(sectors), "%u B logical / %u B physical",
             disk->sector_size, disk->sector_size_physical);

    const char *smart_str = disk->smart_passed == 1 ? "PASSED"
                          : disk->smart_passed == 0 ? "FAILED"
                          :                           "Unknown";
    uint32_t smart_col = disk->smart_passed == 1 ? C_GREEN
                       : disk->smart_passed == 0 ? C_RED
                       :                           C_GRAY;

    struct { const char *k; const char *v; uint32_t c; } id_rows[] = {
        { "Model",         disk->model[0]    ? disk->model    : "N/A", C_DARK },
        { "Serial Number", disk->serial[0]   ? disk->serial   : "N/A", C_DARK },
        { "Firmware",      disk->firmware[0] ? disk->firmware : "N/A", C_DARK },
        { "Type",          disk_type_str(disk->type),                  C_DARK },
        { "Capacity",      sz,                                          C_DARK },
        { "Sector Size",   sectors,                                     C_DARK },
        { "Power-On Time", poh,                                         C_DARK },
        { "SMART Status",  smart_str,                                  smart_col },
    };
    int n_id = sizeof(id_rows) / sizeof(id_rows[0]);
    for (int i = 0; i < n_id; i++) {
        kv_row(pdf, pg, cursor, id_rows[i].k, id_rows[i].v, id_rows[i].c, i & 1);
        cursor += 14.0f;
    }
    cursor += 6.0f;

    /* ══════════════════════════════════════════════════════
     *  NVMe HEALTH (if applicable)
     * ══════════════════════════════════════════════════════ */
    if (disk->has_nvme) {
        const NvmeHealth *n = &disk->nvme;

        text_bold(pdf, pg, ML, cursor + 2, 10, C_BLUE, "NVMe HEALTH LOG");
        hrule(pdf, pg, cursor + 14, 0.5f, C_BLUE);
        cursor += 18.0f;

        char buf[64];
        int health_pct = 100 - n->percentage_used;
        snprintf(buf, sizeof(buf), "%d %%", health_pct);
        uint32_t hcol = health_pct <= 10 ? C_RED : health_pct <= 20 ? C_AMBER : C_GREEN;
        kv_row(pdf, pg, cursor, "Life Remaining", buf, hcol, 0); cursor += 14;

        snprintf(buf, sizeof(buf), "%d C", n->temperature_c);
        uint32_t tcol = n->temperature_c >= 70 ? C_RED : n->temperature_c >= 55 ? C_AMBER : C_GREEN;
        kv_row(pdf, pg, cursor, "Temperature", buf, tcol, 1); cursor += 14;

        double wtb = (double)n->data_units_written * 512.0 * 1000.0
                   / (1024.0 * 1024.0 * 1024.0 * 1024.0);
        snprintf(buf, sizeof(buf), "%.2f TB", wtb);
        kv_row(pdf, pg, cursor, "Data Written", buf, C_DARK, 0); cursor += 14;

        snprintf(buf, sizeof(buf), "%u", n->power_cycles);
        kv_row(pdf, pg, cursor, "Power Cycles", buf, C_DARK, 1); cursor += 14;

        snprintf(buf, sizeof(buf), "%u", n->unsafe_shutdowns);
        kv_row(pdf, pg, cursor, "Unsafe Shutdowns", buf,
               n->unsafe_shutdowns > 50 ? C_AMBER : C_DARK, 0); cursor += 14;

        snprintf(buf, sizeof(buf), "%u", n->media_errors);
        kv_row(pdf, pg, cursor, "Media Errors", buf,
               n->media_errors > 0 ? C_RED : C_GREEN, 1); cursor += 14;

        snprintf(buf, sizeof(buf), "%d %% (threshold %d %%)",
                 n->available_spare, n->available_spare_threshold);
        kv_row(pdf, pg, cursor, "Available Spare", buf,
               n->available_spare <= n->available_spare_threshold ? C_RED : C_GREEN, 0);
        cursor += 14;

        cursor += 6.0f;
    }

    /* ══════════════════════════════════════════════════════
     *  SMART ATTRIBUTES TABLE  (ATA)
     * ══════════════════════════════════════════════════════ */
    if (!disk->has_nvme && disk->attr_count > 0) {
        /* New page if running out of space */
        if (cursor > PH - 120) {
            pg = pdf_append_page(pdf);
            cursor = 20.0f;
        }

        text_bold(pdf, pg, ML, cursor + 2, 10, C_BLUE, "SMART ATTRIBUTES");
        hrule(pdf, pg, cursor + 14, 0.5f, C_BLUE);
        cursor += 18.0f;

        /* Column widths */
        float col_x[]  = { ML,      ML+32,  ML+220, ML+252, ML+286 };
        float col_w[]  = { 30,      186,    30,     32,     70     };
        const char *col_hdr[] = { "ID", "Attribute", "Cur", "Wst", "Raw" };

        /* Header row */
        filled_rect(pdf, pg, ML, cursor, CW, 14, PDF_RGB(0x00,0x55,0xAA));
        for (int c = 0; c < 5; c++)
            text_bold(pdf, pg, col_x[c] + 2, cursor + 2, 8, C_WHITE, col_hdr[c]);
        cursor += 14.0f;

        for (int i = 0; i < disk->attr_count; i++) {
            const SmartAttr *a = &disk->attrs[i];

            /* Overflow to next page */
            if (cursor + 12 > PH - 30) {
                /* Footer on current page */
                hrule(pdf, pg, PH - 24, 0.3f, C_LGRAY);
                text_at(pdf, pg, ML, PH - 22, 7, C_GRAY,
                        "BlackCat SMART  -  Disk Health Report  (continued)");

                pg = pdf_append_page(pdf);
                cursor = 20.0f;

                /* Repeat header on new page */
                filled_rect(pdf, pg, ML, cursor, CW, 14, PDF_RGB(0x00,0x55,0xAA));
                for (int c = 0; c < 5; c++)
                    text_bold(pdf, pg, col_x[c] + 2, cursor + 2, 8, C_WHITE, col_hdr[c]);
                cursor += 14.0f;
            }

            int even    = (i & 1);
            int failing = (a->failing != 0);
            int notable = !failing &&
                          (a->id == 5 || a->id == 196 || a->id == 197 ||
                           a->id == 198 || a->id == 187) && a->raw > 0;
            uint32_t txt_col = failing ? C_RED : notable ? C_AMBER : C_DARK;
            uint32_t bg_col  = failing ? PDF_RGB(0xFF,0xEE,0xEE)
                             : notable ? PDF_RGB(0xFF,0xF8,0xE0)
                             : even    ? C_ROW2 : C_ROW1;

            filled_rect(pdf, pg, ML, cursor, CW, 12, bg_col);

            char id_buf[8];    snprintf(id_buf,  sizeof(id_buf),  "%d",   a->id);
            char cur_buf[8];   snprintf(cur_buf, sizeof(cur_buf), "%d",   a->current);
            char wst_buf[8];   snprintf(wst_buf, sizeof(wst_buf), "%d",   a->worst);
            char raw_buf[24];  snprintf(raw_buf, sizeof(raw_buf), "%llu", (unsigned long long)a->raw);

            text_at(pdf, pg, col_x[0]+2, cursor+2, 7, C_GRAY,    id_buf);
            text_at(pdf, pg, col_x[1]+2, cursor+2, 7, txt_col,   a->name);
            text_at(pdf, pg, col_x[2]+2, cursor+2, 7, txt_col,   cur_buf);
            text_at(pdf, pg, col_x[3]+2, cursor+2, 7, C_GRAY,    wst_buf);
            text_at(pdf, pg, col_x[4]+2, cursor+2, 7, txt_col,   raw_buf);

            /* Row border */
            pdf_add_line(pdf, pg, ML, y2pt(cursor+12), ML+CW, y2pt(cursor+12), 0.2f, C_LGRAY);

            cursor += 12.0f;
        }
        cursor += 6.0f;
    }

    /* ══════════════════════════════════════════════════════
     *  FOOTER
     * ══════════════════════════════════════════════════════ */
    hrule(pdf, pg, PH - 24, 0.5f, C_LGRAY);
    text_at(pdf, pg, ML, PH - 22, 7, C_GRAY,
            "BlackCat SMART  |  Direct hardware access via Win32 IOCTL  |  Read-only, no disk writes");
    text_at(pdf, pg, PW - MR - 60, PH - 22, 7, C_GRAY, ts);

    int ok = (pdf_save(pdf, out_path) == 0);
    pdf_destroy(pdf);
    return ok;
}
