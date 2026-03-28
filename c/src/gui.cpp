/*
 * gui.cpp  —  BlackCat SMART GUI
 * Dear ImGui + DirectX 11 + Win32
 *
 * Layout:
 *   Left panel  : disk list (card per disk)
 *   Right panel : selected disk detail + SMART attributes table
 *   Bottom bar  : status / export PDF button / language toggle
 */

#include "../imgui/imgui.h"
#include "../imgui/backends/imgui_impl_win32.h"
#include "../imgui/backends/imgui_impl_dx11.h"

#include <d3d11.h>
#include <windows.h>
#include <shlobj.h>
#include <commdlg.h>
#include <stdio.h>
#include <string.h>
#include <time.h>

extern "C" {
#include "../include/smart.h"
#include "../include/lang.h"
}

/* ── forward declarations ─────────────────────────────────── */
extern IMGUI_IMPL_API LRESULT ImGui_ImplWin32_WndProcHandler(
    HWND hWnd, UINT msg, WPARAM wParam, LPARAM lParam);

/* ── DirectX 11 globals ───────────────────────────────────── */
static ID3D11Device           *g_pd3dDevice           = nullptr;
static ID3D11DeviceContext    *g_pd3dDeviceContext     = nullptr;
static IDXGISwapChain         *g_pSwapChain            = nullptr;
static ID3D11RenderTargetView *g_mainRenderTargetView  = nullptr;

static bool CreateDeviceD3D(HWND hWnd);
static void CleanupDeviceD3D();
static void CreateRenderTarget();
static void CleanupRenderTarget();
static LRESULT WINAPI WndProc(HWND hWnd, UINT msg, WPARAM wParam, LPARAM lParam);

/* ── App state ────────────────────────────────────────────── */
static DiskInfo  g_disks[MAX_DISKS];
static int       g_disk_count  = 0;
static int       g_selected    = 0;    /* currently selected disk index */
static char      g_status[256] = "Ready";
static bool      g_scanning    = false;

/* ── Colour palette ───────────────────────────────────────── */
#define COL32(r,g,b,a) IM_COL32(r,g,b,a)

static const ImVec4 C_BG        = {0.04f, 0.06f, 0.10f, 1.0f}; /* #0a0e1a */
static const ImVec4 C_PANEL     = {0.07f, 0.10f, 0.15f, 1.0f}; /* #111827 */
static const ImVec4 C_BORDER    = {0.12f, 0.18f, 0.27f, 1.0f}; /* #1e2d45 */
static const ImVec4 C_ACCENT    = {0.00f, 0.83f, 1.00f, 1.0f}; /* #00d4ff */
static const ImVec4 C_ACCENT2   = {0.49f, 0.23f, 0.93f, 1.0f}; /* #7c3aed */
static const ImVec4 C_TEXT      = {0.89f, 0.91f, 0.94f, 1.0f}; /* #e2e8f0 */
static const ImVec4 C_MUTED     = {0.39f, 0.45f, 0.55f, 1.0f}; /* #64748b */
static const ImVec4 C_GREEN     = {0.09f, 0.80f, 0.34f, 1.0f}; /* #17cc57 */
static const ImVec4 C_YELLOW    = {0.96f, 0.62f, 0.04f, 1.0f}; /* #f59e0b */
static const ImVec4 C_RED       = {0.96f, 0.26f, 0.21f, 1.0f}; /* #f5433a */
static const ImVec4 C_CARD_SEL  = {0.10f, 0.15f, 0.23f, 1.0f};

/* ── Helpers ──────────────────────────────────────────────── */
static ImVec4 score_color(int score)
{
    if (score >= 80) return C_GREEN;
    if (score >= 50) return C_YELLOW;
    return C_RED;
}

static const char *score_verdict_key(int score)
{
    if (score >= 85) return "v_good";
    if (score >= 60) return "v_monitor";
    if (score >= 30) return "v_risk";
    return "v_crit";
}

static const char *score_verdict_detail_key(int score)
{
    if (score >= 85) return "vd_good";
    if (score >= 60) return "vd_monitor";
    if (score >= 30) return "vd_risk";
    return "vd_crit";
}

static void size_str(uint64_t bytes, char *buf, int bufsz)
{
    double gb = (double)bytes / (1024.0 * 1024.0 * 1024.0);
    if (gb >= 1000.0)
        snprintf(buf, bufsz, "%.1f TB", gb / 1024.0);
    else
        snprintf(buf, bufsz, "%.0f GB", gb);
}

/* ── Left panel: disk card list ───────────────────────────── */
static void draw_disk_list(float panel_w, float panel_h)
{
    ImGui::SetNextWindowPos({0, 0});
    ImGui::SetNextWindowSize({panel_w, panel_h});
    ImGui::PushStyleColor(ImGuiCol_WindowBg, C_PANEL);
    ImGui::PushStyleColor(ImGuiCol_Border,   C_BORDER);
    ImGui::Begin("##disklist", nullptr,
        ImGuiWindowFlags_NoTitleBar | ImGuiWindowFlags_NoResize |
        ImGuiWindowFlags_NoMove     | ImGuiWindowFlags_NoScrollbar |
        ImGuiWindowFlags_NoBringToFrontOnFocus);

    /* Title */
    ImGui::PushStyleColor(ImGuiCol_Text, C_ACCENT);
    ImGui::SetWindowFontScale(1.1f);
    ImGui::Text("  %s", L("app_name"));
    ImGui::SetWindowFontScale(1.0f);
    ImGui::PopStyleColor();

    ImGui::PushStyleColor(ImGuiCol_Text, C_MUTED);
    ImGui::Text("  %s", L("app_sub"));
    ImGui::PopStyleColor();
    ImGui::Separator();
    ImGui::Spacing();

    /* Scan button */
    ImGui::PushStyleColor(ImGuiCol_Button,        C_ACCENT2);
    ImGui::PushStyleColor(ImGuiCol_ButtonHovered,
        ImVec4{C_ACCENT2.x+0.1f, C_ACCENT2.y+0.1f, C_ACCENT2.z+0.1f, 1.0f});
    ImGui::PushStyleColor(ImGuiCol_ButtonActive,  C_ACCENT);
    if (ImGui::Button(g_scanning ? L("btn_scanning") : L("btn_scan"),
                      {panel_w - 20.0f, 32.0f})) {
        if (!g_scanning) {
            g_scanning   = true;
            snprintf(g_status, sizeof(g_status), "Scanning hardware...");
            g_disk_count = disk_enumerate(g_disks);
            g_selected   = 0;
            g_scanning   = false;
            /* status_found has %d placeholder — format manually */
            snprintf(g_status, sizeof(g_status), L("status_found"), g_disk_count);
        }
    }
    ImGui::PopStyleColor(3);
    ImGui::Spacing();

    /* Disk cards */
    ImGui::BeginChild("##cards", {panel_w - 8.0f, 0}, false);
    for (int i = 0; i < g_disk_count; i++) {
        const DiskInfo *d = &g_disks[i];
        int   score = disk_health_score(d);
        bool  sel   = (i == g_selected);

        ImGui::PushID(i);
        ImGui::PushStyleColor(ImGuiCol_ChildBg,
            sel ? C_CARD_SEL : C_PANEL);
        ImGui::PushStyleColor(ImGuiCol_Border,
            sel ? C_ACCENT : C_BORDER);

        /* Card height: 72 normally, +14 if drive letters present */
        float card_h = (d->drive_letters[0]) ? 86.0f : 72.0f;
        ImGui::BeginChild("##card", {panel_w - 16.0f, card_h}, true,
            ImGuiWindowFlags_NoScrollbar);

        /* Clickable area */
        ImVec2 card_min = ImGui::GetWindowPos();
        ImVec2 card_max = {card_min.x + panel_w - 16.0f, card_min.y + card_h};
        if (ImGui::IsMouseHoveringRect(card_min, card_max) &&
            ImGui::IsMouseClicked(0))
            g_selected = i;

        /* Disk type badge */
        ImGui::PushStyleColor(ImGuiCol_Text,
            d->type == DISK_TYPE_NVME ? C_ACCENT :
            d->type == DISK_TYPE_SSD  ? C_GREEN  : C_TEXT);
        ImGui::Text("%s", disk_type_str(d->type));
        ImGui::PopStyleColor();

        ImGui::SameLine();
        /* Health score badge */
        ImGui::PushStyleColor(ImGuiCol_Text, score_color(score));
        ImGui::Text("[%d]", score);
        ImGui::PopStyleColor();

        /* Model name */
        ImGui::PushStyleColor(ImGuiCol_Text, C_TEXT);
        char short_model[32] = "Unknown";
        if (d->model[0])
            snprintf(short_model, sizeof(short_model), "%.30s", d->model);
        ImGui::TextUnformatted(short_model);
        ImGui::PopStyleColor();

        /* Size + PhysicalDrive index */
        char sz[16];
        size_str(d->size_bytes, sz, sizeof(sz));
        ImGui::PushStyleColor(ImGuiCol_Text, C_MUTED);
        ImGui::Text("PhysicalDrive%d  %s", d->index, sz);
        ImGui::PopStyleColor();

        /* Drive letters (if any) */
        if (d->drive_letters[0]) {
            ImGui::PushStyleColor(ImGuiCol_Text, C_YELLOW);
            ImGui::Text("  %s: %s", L("drives"), d->drive_letters);
            ImGui::PopStyleColor();
        }

        ImGui::EndChild();
        ImGui::PopStyleColor(2);
        ImGui::PopID();
        ImGui::Spacing();
    }
    ImGui::EndChild();
    ImGui::End();
    ImGui::PopStyleColor(2);
}

/* ── Right panel: disk detail ─────────────────────────────── */
static void draw_disk_detail(float x, float panel_w, float panel_h)
{
    ImGui::SetNextWindowPos({x, 0});
    ImGui::SetNextWindowSize({panel_w, panel_h});
    ImGui::PushStyleColor(ImGuiCol_WindowBg, C_BG);
    ImGui::PushStyleColor(ImGuiCol_Border,   C_BORDER);
    ImGui::Begin("##detail", nullptr,
        ImGuiWindowFlags_NoTitleBar | ImGuiWindowFlags_NoResize |
        ImGuiWindowFlags_NoMove     | ImGuiWindowFlags_NoBringToFrontOnFocus);

    if (g_disk_count == 0) {
        ImGui::SetCursorPosY(panel_h * 0.45f);
        ImGui::PushStyleColor(ImGuiCol_Text, C_MUTED);
        const char *hint = L("no_disks");
        float tw = ImGui::CalcTextSize(hint).x;
        ImGui::SetCursorPosX((panel_w - tw) * 0.5f);
        ImGui::TextUnformatted(hint);
        ImGui::PopStyleColor();
        ImGui::End();
        ImGui::PopStyleColor(2);
        return;
    }

    const DiskInfo *d = &g_disks[g_selected];
    int score = disk_health_score(d);

    /* ── Header ── */
    ImGui::PushStyleColor(ImGuiCol_Text, C_ACCENT);
    ImGui::SetWindowFontScale(1.2f);
    ImGui::Text(" %s", d->model[0] ? d->model : "Unknown Disk");
    ImGui::SetWindowFontScale(1.0f);
    ImGui::PopStyleColor();

    ImGui::SameLine(panel_w - 160.0f);
    ImGui::PushStyleColor(ImGuiCol_Text, score_color(score));
    ImGui::SetWindowFontScale(1.3f);
    ImGui::Text("%s: %d/100", L("lbl_health"), score);
    ImGui::SetWindowFontScale(1.0f);
    ImGui::PopStyleColor();

    ImGui::Separator();
    ImGui::Spacing();

    /* ── Identity rows ── */
    auto label_val = [&](const char *lbl, const char *val, ImVec4 vcol = C_TEXT) {
        ImGui::PushStyleColor(ImGuiCol_Text, C_MUTED);
        ImGui::Text("  %-18s", lbl);
        ImGui::PopStyleColor();
        ImGui::SameLine();
        ImGui::PushStyleColor(ImGuiCol_Text, vcol);
        ImGui::TextUnformatted(val);
        ImGui::PopStyleColor();
    };

    char sz[16]; size_str(d->size_bytes, sz, sizeof(sz));
    char sn[48];  snprintf(sn, sizeof(sn), "%s", d->serial[0]   ? d->serial   : "N/A");
    char fw[24];  snprintf(fw, sizeof(fw), "%s", d->firmware[0] ? d->firmware : "N/A");
    char sec[48]; snprintf(sec, sizeof(sec), "%u B logical / %u B physical",
                           d->sector_size, d->sector_size_physical);
    char poh[64];
    if (d->power_on_hours > 0)
        snprintf(poh, sizeof(poh), L("hours_days"), d->power_on_hours, d->power_on_hours / 24);
    else
        snprintf(poh, sizeof(poh), "N/A");

    label_val(L("lbl_type"),     disk_type_str(d->type),
              d->type == DISK_TYPE_NVME ? C_ACCENT :
              d->type == DISK_TYPE_SSD  ? C_GREEN  : C_TEXT);
    label_val(L("lbl_model"),    d->model[0]    ? d->model    : "N/A");
    label_val(L("lbl_serial"),   sn);
    label_val(L("lbl_firmware"), fw);
    label_val(L("lbl_capacity"), sz);
    label_val(L("lbl_sector"),   sec);
    label_val(L("lbl_poweron"),  poh);

    /* Drive letters */
    if (d->drive_letters[0]) {
        label_val(L("lbl_drives"), d->drive_letters, C_YELLOW);
    } else {
        label_val(L("lbl_drives"), L("no_drives"), C_MUTED);
    }

    /* SMART status */
    const char *smart_str = d->smart_passed == 1 ? L("smart_pass")
                          : d->smart_passed == 0 ? L("smart_fail")
                          :                        L("smart_unk");
    ImVec4 smart_col = d->smart_passed == 1 ? C_GREEN
                     : d->smart_passed == 0 ? C_RED
                     :                        C_MUTED;
    label_val(L("lbl_smart"),    smart_str, smart_col);

    /* Verdict */
    int sc = score;
    label_val(L("lbl_verdict"),  L(score_verdict_key(sc)), score_color(sc));

    /* Verdict detail */
    ImGui::Spacing();
    ImGui::PushStyleColor(ImGuiCol_Text, score_color(sc));
    ImGui::Text("  %s", L(score_verdict_detail_key(sc)));
    ImGui::PopStyleColor();

    ImGui::Spacing();
    ImGui::Separator();
    ImGui::Spacing();

    /* ── NVMe detail / error ── */
    if (d->type == DISK_TYPE_NVME && !d->has_nvme && d->error[0]) {
        ImGui::Spacing();
        ImGui::PushStyleColor(ImGuiCol_Text, C_YELLOW);
        ImGui::Text("  %s : %s", L("nvme_err"), d->error);
        ImGui::PopStyleColor();
        ImGui::Spacing();
        ImGui::Separator();
        ImGui::Spacing();
    }

    if (d->has_nvme) {
        const NvmeHealth *n = &d->nvme;
        ImGui::PushStyleColor(ImGuiCol_Text, C_ACCENT);
        ImGui::Text("  %s", L("nvme_title"));
        ImGui::PopStyleColor();
        ImGui::Spacing();

        int health_pct = 100 - n->percentage_used;
        ImVec4 hlth_col = health_pct <= 10 ? C_RED : health_pct <= 20 ? C_YELLOW : C_GREEN;
        ImVec4 temp_col = n->temperature_c >= 70 ? C_RED
                        : n->temperature_c >= 55 ? C_YELLOW : C_GREEN;

        char buf[64];
        snprintf(buf, sizeof(buf), "%d %%", health_pct);
        label_val(L("nvme_life"),    buf, hlth_col);
        snprintf(buf, sizeof(buf), "%d C", n->temperature_c);
        label_val(L("nvme_temp"),    buf, temp_col);
        double wtb = (double)n->data_units_written * 512.0 * 1000.0
                   / (1024.0 * 1024.0 * 1024.0 * 1024.0);
        snprintf(buf, sizeof(buf), "%.2f TB", wtb);
        label_val(L("nvme_written"), buf);
        snprintf(buf, sizeof(buf), "%u", n->power_cycles);
        label_val(L("nvme_cycles"),  buf);
        snprintf(buf, sizeof(buf), "%u", n->unsafe_shutdowns);
        label_val(L("nvme_unsafe"),  buf,
            n->unsafe_shutdowns > 50 ? C_YELLOW : C_TEXT);
        snprintf(buf, sizeof(buf), "%u", n->media_errors);
        label_val(L("nvme_merr"),    buf, n->media_errors > 0 ? C_RED : C_GREEN);
        snprintf(buf, sizeof(buf), "%u", n->num_err_log_entries);
        label_val(L("nvme_elog"),    buf, n->num_err_log_entries > 0 ? C_YELLOW : C_GREEN);
        snprintf(buf, sizeof(buf), "%d %% (thr %d %%)",
                 n->available_spare, n->available_spare_threshold);
        label_val(L("nvme_spare"),   buf,
            n->available_spare <= n->available_spare_threshold ? C_RED : C_GREEN);

        ImGui::Spacing();
        ImGui::Separator();
        ImGui::Spacing();
    }

    /* ── ATA SMART attributes table ── */
    if (!d->has_nvme && d->attr_count > 0) {
        ImGui::PushStyleColor(ImGuiCol_Text, C_ACCENT);
        ImGui::Text("  %s", L("tbl_attrs"));
        ImGui::PopStyleColor();
        ImGui::Spacing();

        ImGui::PushStyleColor(ImGuiCol_TableBorderLight, C_BORDER);
        ImGui::PushStyleColor(ImGuiCol_TableBorderStrong, C_BORDER);
        ImGui::PushStyleColor(ImGuiCol_TableHeaderBg,
            ImVec4{0.07f, 0.12f, 0.20f, 1.0f});

        if (ImGui::BeginTable("##attrs", 5,
            ImGuiTableFlags_BordersInnerV |
            ImGuiTableFlags_BordersOuter  |
            ImGuiTableFlags_RowBg         |
            ImGuiTableFlags_ScrollY       |
            ImGuiTableFlags_SizingFixedFit,
            {0, 0}))
        {
            ImGui::TableSetupScrollFreeze(0, 1);
            ImGui::TableSetupColumn(L("tbl_id"),   ImGuiTableColumnFlags_WidthFixed,  36);
            ImGui::TableSetupColumn(L("tbl_attr"), ImGuiTableColumnFlags_WidthStretch);
            ImGui::TableSetupColumn(L("tbl_cur"),  ImGuiTableColumnFlags_WidthFixed,  40);
            ImGui::TableSetupColumn(L("tbl_wst"),  ImGuiTableColumnFlags_WidthFixed,  44);
            ImGui::TableSetupColumn(L("tbl_raw"),  ImGuiTableColumnFlags_WidthFixed,  90);
            ImGui::PushStyleColor(ImGuiCol_Text, C_ACCENT);
            ImGui::TableHeadersRow();
            ImGui::PopStyleColor();

            for (int i = 0; i < d->attr_count; i++) {
                const SmartAttr *a = &d->attrs[i];
                ImGui::TableNextRow();

                /* Row color: red if failing, yellow if notable */
                bool notable = (a->id == 5  || a->id == 196 || a->id == 197 ||
                                a->id == 198|| a->id == 187) && a->raw > 0;
                ImVec4 row_col = a->failing ? C_RED : notable ? C_YELLOW : C_TEXT;

                ImGui::TableSetColumnIndex(0);
                ImGui::PushStyleColor(ImGuiCol_Text, C_MUTED);
                ImGui::Text("%3d", a->id);
                ImGui::PopStyleColor();

                ImGui::TableSetColumnIndex(1);
                ImGui::PushStyleColor(ImGuiCol_Text, row_col);
                ImGui::TextUnformatted(a->name);
                ImGui::PopStyleColor();

                ImGui::TableSetColumnIndex(2);
                ImGui::PushStyleColor(ImGuiCol_Text, row_col);
                ImGui::Text("%d", a->current);
                ImGui::PopStyleColor();

                ImGui::TableSetColumnIndex(3);
                ImGui::PushStyleColor(ImGuiCol_Text, C_MUTED);
                ImGui::Text("%d", a->worst);
                ImGui::PopStyleColor();

                ImGui::TableSetColumnIndex(4);
                ImGui::PushStyleColor(ImGuiCol_Text, row_col);
                ImGui::Text("%llu", (unsigned long long)a->raw);
                ImGui::PopStyleColor();
            }
            ImGui::EndTable();
        }
        ImGui::PopStyleColor(3);
    }

    ImGui::End();
    ImGui::PopStyleColor(2);
}

/* ── Status bar ───────────────────────────────────────────── */
static void draw_statusbar(float panel_h, float win_w)
{
    ImGui::SetNextWindowPos({0, panel_h});
    ImGui::SetNextWindowSize({win_w, 28.0f});
    ImGui::PushStyleColor(ImGuiCol_WindowBg,
        ImVec4{0.05f, 0.08f, 0.12f, 1.0f});
    ImGui::PushStyleColor(ImGuiCol_Border, C_BORDER);
    ImGui::Begin("##status", nullptr,
        ImGuiWindowFlags_NoTitleBar | ImGuiWindowFlags_NoResize |
        ImGuiWindowFlags_NoMove     | ImGuiWindowFlags_NoScrollbar |
        ImGuiWindowFlags_NoBringToFrontOnFocus);

    ImGui::PushStyleColor(ImGuiCol_Text, C_MUTED);
    ImGui::Text("  BlackCat SMART  |  %s", g_status);
    ImGui::PopStyleColor();

    /* Language toggle button — always visible, right side */
    float lang_btn_w = 48.0f;
    float export_btn_w = 120.0f;
    float right_edge = win_w - 8.0f;

    /* Export PDF button — only when a disk is selected */
    if (g_disk_count > 0) {
        ImGui::SameLine(right_edge - export_btn_w - lang_btn_w - 8.0f);
        ImGui::PushStyleColor(ImGuiCol_Button,        ImVec4{0.00f,0.55f,0.80f,1.0f});
        ImGui::PushStyleColor(ImGuiCol_ButtonHovered, ImVec4{0.00f,0.70f,1.00f,1.0f});
        ImGui::PushStyleColor(ImGuiCol_ButtonActive,  C_ACCENT);
        if (ImGui::Button(L("btn_export"), {export_btn_w, 20.0f})) {
            /* Default filename: BlackCat_DriveN_YYYYMMDD.pdf */
            char def_name[64];
            time_t now = time(NULL);
            struct tm *t = localtime(&now);
            snprintf(def_name, sizeof(def_name),
                     "BlackCat_Drive%d_%04d%02d%02d.pdf",
                     g_disks[g_selected].index,
                     t->tm_year + 1900, t->tm_mon + 1, t->tm_mday);

            /* Win32 Save File Dialog */
            char out[MAX_PATH] = {0};
            OPENFILENAMEA ofn   = {0};
            ofn.lStructSize     = sizeof(ofn);
            ofn.lpstrFilter     = "PDF Files\0*.pdf\0All Files\0*.*\0";
            ofn.lpstrFile       = out;
            ofn.nMaxFile        = MAX_PATH;
            ofn.lpstrDefExt     = "pdf";
            ofn.lpstrTitle      = "Save SMART Report";
            ofn.lpstrFileTitle  = def_name;
            ofn.Flags           = OFN_OVERWRITEPROMPT | OFN_PATHMUSTEXIST;
            strncpy(out, def_name, MAX_PATH - 1);

            if (GetSaveFileNameA(&ofn)) {
                snprintf(g_status, sizeof(g_status), "%s", L("status_saving"));
                if (report_generate(&g_disks[g_selected], out)) {
                    snprintf(g_status, sizeof(g_status), L("status_saved"), out);
                    ShellExecuteA(NULL, "open", out, NULL, NULL, SW_SHOWNORMAL);
                } else {
                    snprintf(g_status, sizeof(g_status), "%s", L("status_fail"));
                }
            }
            /* user cancelled — do nothing */
        }
        ImGui::PopStyleColor(3);
        ImGui::SameLine();
    } else {
        ImGui::SameLine(right_edge - lang_btn_w - 8.0f);
    }

    /* Language toggle */
    ImGui::PushStyleColor(ImGuiCol_Button,        ImVec4{0.15f,0.20f,0.30f,1.0f});
    ImGui::PushStyleColor(ImGuiCol_ButtonHovered, ImVec4{0.20f,0.28f,0.40f,1.0f});
    ImGui::PushStyleColor(ImGuiCol_ButtonActive,  C_ACCENT2);
    ImGui::PushStyleColor(ImGuiCol_Text,          C_ACCENT);
    if (ImGui::Button(lang_name(), {lang_btn_w, 20.0f})) {
        lang_toggle();
        /* Update status text for new language */
        if (g_disk_count > 0)
            snprintf(g_status, sizeof(g_status), L("status_found"), g_disk_count);
        else
            snprintf(g_status, sizeof(g_status), "%s", L("status_ready"));
    }
    ImGui::PopStyleColor(4);

    ImGui::End();
    ImGui::PopStyleColor(2);
}

/* ── Win32 window proc ────────────────────────────────────── */
static LRESULT WINAPI WndProc(HWND hWnd, UINT msg, WPARAM wParam, LPARAM lParam)
{
    if (ImGui_ImplWin32_WndProcHandler(hWnd, msg, wParam, lParam))
        return true;
    switch (msg) {
        case WM_SIZE:
            if (g_pd3dDevice && wParam != SIZE_MINIMIZED) {
                CleanupRenderTarget();
                g_pSwapChain->ResizeBuffers(0,
                    LOWORD(lParam), HIWORD(lParam),
                    DXGI_FORMAT_UNKNOWN, 0);
                CreateRenderTarget();
            }
            return 0;
        case WM_SYSCOMMAND:
            if ((wParam & 0xfff0) == SC_KEYMENU) return 0;
            break;
        case WM_DESTROY:
            PostQuitMessage(0);
            return 0;
    }
    return DefWindowProcW(hWnd, msg, wParam, lParam);
}

/* ── D3D setup ────────────────────────────────────────────── */
static bool CreateDeviceD3D(HWND hWnd)
{
    DXGI_SWAP_CHAIN_DESC sd = {};
    sd.BufferCount                        = 2;
    sd.BufferDesc.Width                   = 0;
    sd.BufferDesc.Height                  = 0;
    sd.BufferDesc.Format                  = DXGI_FORMAT_R8G8B8A8_UNORM;
    sd.BufferDesc.RefreshRate.Numerator   = 60;
    sd.BufferDesc.RefreshRate.Denominator = 1;
    sd.Flags                              = DXGI_SWAP_CHAIN_FLAG_ALLOW_MODE_SWITCH;
    sd.BufferUsage                        = DXGI_USAGE_RENDER_TARGET_OUTPUT;
    sd.OutputWindow                       = hWnd;
    sd.SampleDesc.Count                   = 1;
    sd.SampleDesc.Quality                 = 0;
    sd.Windowed                           = TRUE;
    sd.SwapEffect                         = DXGI_SWAP_EFFECT_DISCARD;

    UINT flags = 0;
    D3D_FEATURE_LEVEL fl;
    D3D_FEATURE_LEVEL fls[] = {D3D_FEATURE_LEVEL_11_0, D3D_FEATURE_LEVEL_10_0};

    if (D3D11CreateDeviceAndSwapChain(nullptr, D3D_DRIVER_TYPE_HARDWARE,
            nullptr, flags, fls, 2, D3D11_SDK_VERSION,
            &sd, &g_pSwapChain, &g_pd3dDevice, &fl, &g_pd3dDeviceContext) != S_OK)
        return false;

    CreateRenderTarget();
    return true;
}

static void CleanupDeviceD3D()
{
    CleanupRenderTarget();
    if (g_pSwapChain)        { g_pSwapChain->Release();        g_pSwapChain = nullptr; }
    if (g_pd3dDeviceContext) { g_pd3dDeviceContext->Release(); g_pd3dDeviceContext = nullptr; }
    if (g_pd3dDevice)        { g_pd3dDevice->Release();        g_pd3dDevice = nullptr; }
}

static void CreateRenderTarget()
{
    ID3D11Texture2D *pBackBuffer = nullptr;
    g_pSwapChain->GetBuffer(0, IID_PPV_ARGS(&pBackBuffer));
    if (pBackBuffer) {
        g_pd3dDevice->CreateRenderTargetView(pBackBuffer, nullptr, &g_mainRenderTargetView);
        pBackBuffer->Release();
    }
}

static void CleanupRenderTarget()
{
    if (g_mainRenderTargetView) {
        g_mainRenderTargetView->Release();
        g_mainRenderTargetView = nullptr;
    }
}

/* ── Entry point (exported as C symbol for main.c) ───────── */
extern "C" int gui_main(void)
{
    /* Win32 window */
    WNDCLASSEXW wc = {sizeof(wc), CS_CLASSDC, WndProc, 0, 0,
                      GetModuleHandle(nullptr), nullptr, nullptr, nullptr, nullptr,
                      L"BlackCatSMART", nullptr};
    RegisterClassExW(&wc);

    HWND hwnd = CreateWindowW(L"BlackCatSMART", L"BlackCat SMART",
        WS_OVERLAPPEDWINDOW, 100, 100, 1100, 720,
        nullptr, nullptr, wc.hInstance, nullptr);

    if (!CreateDeviceD3D(hwnd)) {
        CleanupDeviceD3D();
        UnregisterClassW(wc.lpszClassName, wc.hInstance);
        return 1;
    }

    ShowWindow(hwnd, SW_SHOWDEFAULT);
    UpdateWindow(hwnd);

    /* ImGui setup */
    IMGUI_CHECKVERSION();
    ImGui::CreateContext();
    ImGuiIO &io = ImGui::GetIO(); (void)io;
    io.IniFilename = nullptr; /* no imgui.ini */

    /* Load Thai font from Windows Fonts for UTF-8 Thai text.
       Falls back to default font if not found. */
    ImFontConfig cfg;
    cfg.OversampleH = 2;
    cfg.OversampleV = 1;
    /* Thai glyph range: basic Latin + Thai block */
    static const ImWchar thai_ranges[] = {
        0x0020, 0x00FF,   /* Basic Latin + Latin Supplement */
        0x0E00, 0x0E7F,   /* Thai */
        0,
    };
    const char *font_candidates[] = {
        "C:\\Windows\\Fonts\\Tahoma.ttf",
        "C:\\Windows\\Fonts\\tahoma.ttf",
        "C:\\Windows\\Fonts\\NotoSansThai-Regular.ttf",
        nullptr
    };
    bool font_loaded = false;
    for (int fi = 0; font_candidates[fi]; fi++) {
        if (GetFileAttributesA(font_candidates[fi]) != INVALID_FILE_ATTRIBUTES) {
            io.Fonts->AddFontFromFileTTF(font_candidates[fi], 15.0f, &cfg, thai_ranges);
            font_loaded = true;
            break;
        }
    }
    if (!font_loaded)
        io.Fonts->AddFontDefault();

    /* Dark style */
    ImGui::StyleColorsDark();
    ImGuiStyle &style = ImGui::GetStyle();
    style.WindowBorderSize = 1.0f;
    style.FrameRounding    = 4.0f;
    style.ScrollbarRounding= 4.0f;
    style.WindowRounding   = 0.0f;
    style.Colors[ImGuiCol_WindowBg]     = C_BG;
    style.Colors[ImGuiCol_FrameBg]      = C_PANEL;
    style.Colors[ImGuiCol_TitleBgActive]= C_PANEL;
    style.Colors[ImGuiCol_TableRowBg]   = C_BG;
    style.Colors[ImGuiCol_TableRowBgAlt]= C_PANEL;
    style.Colors[ImGuiCol_ScrollbarBg]  = C_PANEL;

    ImGui_ImplWin32_Init(hwnd);
    ImGui_ImplDX11_Init(g_pd3dDevice, g_pd3dDeviceContext);

    /* Main loop */
    bool done = false;
    while (!done) {
        MSG msg;
        while (PeekMessage(&msg, nullptr, 0U, 0U, PM_REMOVE)) {
            TranslateMessage(&msg);
            DispatchMessage(&msg);
            if (msg.message == WM_QUIT) done = true;
        }
        if (done) break;

        ImGui_ImplDX11_NewFrame();
        ImGui_ImplWin32_NewFrame();
        ImGui::NewFrame();

        /* Layout dimensions */
        RECT rc; GetClientRect(hwnd, &rc);
        float win_w    = (float)(rc.right  - rc.left);
        float win_h    = (float)(rc.bottom - rc.top);
        float status_h = 28.0f;
        float panel_h  = win_h - status_h;
        float left_w   = 240.0f;
        float right_w  = win_w - left_w;

        draw_disk_list(left_w, panel_h);
        draw_disk_detail(left_w, right_w, panel_h);
        draw_statusbar(panel_h, win_w);

        /* Render */
        ImGui::Render();
        const float clear[4] = {(float)C_BG.x, (float)C_BG.y, (float)C_BG.z, 1.0f};
        g_pd3dDeviceContext->OMSetRenderTargets(1, &g_mainRenderTargetView, nullptr);
        g_pd3dDeviceContext->ClearRenderTargetView(g_mainRenderTargetView, clear);
        ImGui_ImplDX11_RenderDrawData(ImGui::GetDrawData());
        g_pSwapChain->Present(1, 0); /* vsync */
    }

    ImGui_ImplDX11_Shutdown();
    ImGui_ImplWin32_Shutdown();
    ImGui::DestroyContext();
    CleanupDeviceD3D();
    DestroyWindow(hwnd);
    UnregisterClassW(wc.lpszClassName, wc.hInstance);
    return 0;
}
