"""
BlackCat Disk Scanner v4.0.0
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Tool 22  — HDD / SSD sector-level read scan
Platform — Windows (Administrator required for raw access)
UI       — Flet >= 0.80
Languages — EN / TH  (live switch, no restart)
Install  — pip install flet reportlab
Run      — python disk_scan.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

# ── stdlib ─────────────────────────────────────────────────────────────────────
import asyncio
import ctypes
import ctypes.wintypes
import platform
import random
import subprocess
import threading
import time

# ── third-party ────────────────────────────────────────────────────────────────
import flet as ft


# ══════════════════════════════════════════════════════════════════════════════
#  ADMIN CHECK
# ══════════════════════════════════════════════════════════════════════════════

def is_admin() -> bool:
    """Return True if the current process has Administrator privileges."""
    if platform.system() != "Windows":
        return True
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def relaunch_as_admin() -> None:
    """Re-launch this script elevated via ShellExecute runas verb."""
    import sys
    ctypes.windll.shell32.ShellExecuteW(
        None, "runas", sys.executable, f'"{sys.argv[0]}"', None, 1
    )


# ══════════════════════════════════════════════════════════════════════════════
#  CONSTANTS — theme & grid
# ══════════════════════════════════════════════════════════════════════════════

ACCENT  = "#FF3B30"
ACCENT2 = "#FF9F0A"
GREEN   = "#30D158"
RED     = "#FF3B30"

THEMES: dict[str, dict[str, str]] = {
    "dark": {
        "bg":       "#0D0D0D",
        "panel":    "#141414",
        "card":     "#1C1C1C",
        "border":   "#2C2C2C",
        "text_pri": "#F0F0F0",
        "text_sec": "#888888",
        "grey_blk": "#2A2A2A",
    },
    "light": {
        "bg":       "#F2F2F7",
        "panel":    "#FFFFFF",
        "card":     "#F0F0F5",
        "border":   "#C6C6C8",
        "text_pri": "#1C1C1E",
        "text_sec": "#6C6C70",
        "grey_blk": "#C7C7CC",
    },
}

# Dark-theme aliases used at widget-creation time
BG_DARK  = THEMES["dark"]["bg"]
BG_PANEL = THEMES["dark"]["panel"]
BG_CARD  = THEMES["dark"]["card"]
BORDER   = THEMES["dark"]["border"]
TEXT_PRI = THEMES["dark"]["text_pri"]
TEXT_SEC = THEMES["dark"]["text_sec"]
GREY_BLK = THEMES["dark"]["grey_blk"]

GRID_COLS  = 30
BLOCK_PX   = 22
MAX_BLOCKS = 600


# ══════════════════════════════════════════════════════════════════════════════
#  LANGUAGES
# ══════════════════════════════════════════════════════════════════════════════

LANGS: dict[str, dict[str, str]] = {
    "EN": {
        "admin_warn":    "Run as Administrator for real disk access",
        "cfg_title":     "CONFIGURATION",
        "select_drive":  "Select Drive",
        "scan_mode":     "Scan Mode",
        "mode_quick":    "Quick  (128 MB blocks)",
        "mode_full":     "Full  (512 KB blocks)",
        "on_bad":        "On Bad Sector",
        "stop_first":    "Stop on first bad",
        "scan_finish":   "Scan until finish",
        "btn_start":     "START SCAN",
        "btn_stop":      "STOP",
        "status_title":  "STATUS",
        "ready":         "Ready",
        "map_title":     "DISK MAP",
        "leg_unscan":    "Not scanned",
        "leg_ok":        "OK",
        "leg_bad":       "Bad",
        "log_title":     "EVENT LOG",
        "log_ready":     "Ready — select a drive and press START SCAN.",
        "scanning":      "Scanning Disk {idx}  [{mode} mode]",
        "log_start":     "Disk {idx} | mode={mode} | stop_on_bad={sob}",
        "speed_init":    "Speed: —",
        "bad_zero":      "Bad: 0",
        "bad_n":         "Bad: {n}",
        "speed_val":     "Speed: {v:.1f} MB/s",
        "stopping":      "Stopping...",
        "stop_user":     "Stop requested by user",
        "dlg_title":     "Confirm Stop",
        "dlg_body":      "Do you really want to stop the scan?\nProgress so far will not be lost.",
        "dlg_cancel":    "Cancel",
        "dlg_confirm":   "Stop Scan",
        "res_ok":        "Scan complete — No bad sectors found",
        "res_errors":    "Scan complete — {n} bad sector(s) found",
        "res_failed":    "Stopped — Bad sector detected ({n} total)",
        "res_stopped":   "Scan stopped by user",
        "res_admin":     "Permission denied — Run as Administrator",
        "res_size":      "Cannot read disk size — check disk index",
        "demo_mode":     "Demo Mode  (random, no HDD read)",
        "demo_badge":    "[DEMO]",
        "demo_banner":   "DEMO\nMODE",
        "demo_log":      "[DEMO] Results are randomised — NOT reading real disk",
        "admin_ok":      "Running as Administrator",
        "admin_no":      "NOT Administrator — scan will fail",
        "btn_relaunch":  "Relaunch as Admin",
        "btn_pdf":       "Export PDF Report",
        "pdf_saving":    "Saving PDF...",
        "pdf_saved":     "PDF saved: {path}",
        "pdf_error":     "PDF export failed: {err}",
        "pdf_no_report": "No scan data to export",
        "pdf_sec_info":  "SCAN INFORMATION",
        "pdf_sec_stats": "STATISTICS",
        "pdf_sec_map":   "DISK MAP",
        "pdf_sec_log":   "EVENT LOG",
        "pdf_disk":      "Disk",
        "pdf_serial":    "Serial Number",
        "pdf_mode":      "Scan Mode",
        "pdf_sob":       "Stop on Bad Sector",
        "pdf_start":     "Start Time",
        "pdf_end":       "End Time",
        "pdf_duration":  "Duration",
        "pdf_result":    "Result",
        "pdf_total":     "Total Size",
        "pdf_scanned":   "Scanned",
        "pdf_bad":       "Bad Sectors",
        "pdf_speed":     "Average Speed",
    },
    "TH": {
        "admin_warn":    "กรุณารันในฐานะ Administrator",
        "cfg_title":     "ตั้งค่า",
        "select_drive":  "เลือกไดรฟ์",
        "scan_mode":     "โหมดสแกน",
        "mode_quick":    "Quick  (128 MB ต่อบล็อก)",
        "mode_full":     "Full  (512 KB ต่อบล็อก)",
        "on_bad":        "เมื่อพบ Bad Sector",
        "stop_first":    "หยุดทันทีที่พบครั้งแรก",
        "scan_finish":   "สแกนต่อจนจบ",
        "btn_start":     "เริ่มสแกน",
        "btn_stop":      "หยุด",
        "status_title":  "สถานะ",
        "ready":         "พร้อมใช้งาน",
        "map_title":     "แผนที่ดิสก์",
        "leg_unscan":    "ยังไม่สแกน",
        "leg_ok":        "ปกติ",
        "leg_bad":       "เสีย",
        "log_title":     "บันทึกเหตุการณ์",
        "log_ready":     "พร้อม — เลือกไดรฟ์และกดเริ่มสแกน",
        "scanning":      "กำลังสแกน Disk {idx}  [{mode}]",
        "log_start":     "Disk {idx} | mode={mode} | stop_on_bad={sob}",
        "speed_init":    "ความเร็ว: —",
        "bad_zero":      "เสีย: 0",
        "bad_n":         "เสีย: {n}",
        "speed_val":     "ความเร็ว: {v:.1f} MB/s",
        "stopping":      "กำลังหยุด...",
        "stop_user":     "ผู้ใช้สั่งหยุดการสแกน",
        "dlg_title":     "ยืนยันการหยุดสแกน",
        "dlg_body":      "ต้องการหยุดการสแกนจริงหรือไม่?\nข้อมูลที่สแกนไปแล้วจะไม่หาย",
        "dlg_cancel":    "ยกเลิก",
        "dlg_confirm":   "หยุดสแกน",
        "res_ok":        "สแกนเสร็จ — ไม่พบ Bad Sector",
        "res_errors":    "สแกนเสร็จ — พบ {n} Bad Sector",
        "res_failed":    "หยุดแล้ว — พบ Bad Sector ({n} จุด)",
        "res_stopped":   "ผู้ใช้หยุดการสแกน",
        "res_admin":     "ไม่มีสิทธิ์ — รันในฐานะ Administrator",
        "res_size":      "อ่านขนาดดิสก์ไม่ได้ — ตรวจสอบหมายเลขดิสก์",
        "demo_mode":     "โหมด Demo  (สุ่มผล ไม่อ่าน HDD)",
        "demo_badge":    "[DEMO]",
        "demo_banner":   "DEMO\nMODE",
        "demo_log":      "[DEMO] ผลลัพธ์เป็นการสุ่ม — ไม่ได้อ่าน HDD จริงๆ",
        "admin_ok":      "รันในฐานะ Administrator แล้ว",
        "admin_no":      "ไม่ใช่ Administrator — การสแกนจะล้มเหลว",
        "btn_relaunch":  "รีสตาร์ทในฐานะ Admin",
        "btn_pdf":       "ส่งออก PDF Report",
        "pdf_saving":    "กำลังบันทึก PDF...",
        "pdf_saved":     "บันทึก PDF แล้ว: {path}",
        "pdf_error":     "ส่งออก PDF ล้มเหลว: {err}",
        "pdf_no_report": "ไม่มีข้อมูล scan สำหรับส่งออก",
        "pdf_sec_info":  "ข้อมูลการสแกน",
        "pdf_sec_stats": "สถิติ",
        "pdf_sec_map":   "แผนที่ดิสก์",
        "pdf_sec_log":   "บันทึกเหตุการณ์",
        "pdf_disk":      "ดิสก์",
        "pdf_serial":    "Serial Number",
        "pdf_mode":      "โหมดสแกน",
        "pdf_sob":       "หยุดเมื่อพบ Bad Sector",
        "pdf_start":     "เวลาเริ่ม",
        "pdf_end":       "เวลาสิ้นสุด",
        "pdf_duration":  "ระยะเวลา",
        "pdf_result":    "ผลลัพธ์",
        "pdf_total":     "ขนาดทั้งหมด",
        "pdf_scanned":   "สแกนแล้ว",
        "pdf_bad":       "Bad Sector",
        "pdf_speed":     "ความเร็วเฉลี่ย",
    },
}


# ══════════════════════════════════════════════════════════════════════════════
#  DISK HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def get_disk_size(disk_index: int) -> int:
    if platform.system() != "Windows":
        return 0
    IOCTL = 0x000700A0
    path  = f"\\\\.\\PhysicalDrive{disk_index}"

    class _Geo(ctypes.Structure):
        _fields_ = [
            ("Cylinders",         ctypes.c_longlong),
            ("MediaType",         ctypes.c_uint),
            ("TracksPerCylinder", ctypes.c_ulong),
            ("SectorsPerTrack",   ctypes.c_ulong),
            ("BytesPerSector",    ctypes.c_ulong),
        ]

    class _GeoEx(ctypes.Structure):
        _fields_ = [
            ("Geometry", _Geo),
            ("DiskSize", ctypes.c_longlong),
            ("Data",     ctypes.c_byte * 1),
        ]

    try:
        hnd = ctypes.windll.kernel32.CreateFileW(
            path, 0x80000000, 0x3, None, 3, 0, None)
        if hnd == ctypes.wintypes.HANDLE(-1).value:
            return 0
        geo = _GeoEx()
        br  = ctypes.c_ulong(0)
        ok  = ctypes.windll.kernel32.DeviceIoControl(
            hnd, IOCTL, None, 0,
            ctypes.byref(geo), ctypes.sizeof(geo),
            ctypes.byref(br), None)
        ctypes.windll.kernel32.CloseHandle(hnd)
        return geo.DiskSize if ok else 0
    except Exception:
        return 0


def _parse_pipe_lines(stdout: str) -> list[dict]:
    drives = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line or "|" not in line:
            continue
        parts = line.split("|", 3)
        if len(parts) < 3:
            continue
        id_s   = parts[0].strip()
        model  = parts[1].strip()
        size_s = parts[2].strip()
        serial = parts[3].strip() if len(parts) > 3 else ""
        if not id_s.isdigit():
            continue
        idx = int(id_s)
        sb  = int(size_s) if size_s.isdigit() else 0
        gb  = f"{round(sb / 1024**3, 1)} GB" if sb else "size unknown"
        drives.append({
            "index":      idx,
            "label":      f"Disk {idx}  —  {model or f'Disk {idx}'}  ({gb})",
            "size_bytes": sb,
            "serial":     serial,
        })
    return drives


_NO_WINDOW = subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0


def _run_ps(command: str, timeout: int = 12) -> str:
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
            capture_output=True, text=True,
            timeout=timeout, encoding="utf-8", errors="replace",
            creationflags=_NO_WINDOW)
        return r.stdout
    except Exception:
        return ""


def list_drives() -> list[dict]:
    if platform.system() != "Windows":
        demo = [
            ("Samsung SSD 870 EVO 500GB", 500),
            ("WD Blue 1TB SATA HDD",      1000),
            ("Seagate Barracuda 2TB",      2000),
        ]
        return [{"index": i, "label": f"Disk {i}  —  {m}  ({s} GB)",
                 "size_bytes": s * 1024**3, "serial": "DEMO-SN-00000"}
                for i, (m, s) in enumerate(demo)]

    drives: list[dict] = []

    ps1 = (
        "Get-PhysicalDisk | Sort-Object DeviceId | "
        "Select-Object DeviceId,FriendlyName,Size,SerialNumber | "
        "ForEach-Object { $_.DeviceId + '|' + $_.FriendlyName + '|' + $_.Size + '|' + $_.SerialNumber }"
    )
    drives = _parse_pipe_lines(_run_ps(ps1))

    if not drives:
        ps2 = (
            "Get-Disk | Sort-Object Number | "
            "Select-Object Number,FriendlyName,Size,SerialNumber | "
            "ForEach-Object { $_.Number.ToString() + '|' + $_.FriendlyName + '|' + $_.Size.ToString() + '|' + $_.SerialNumber }"
        )
        drives = _parse_pipe_lines(_run_ps(ps2))

    if not drives:
        try:
            r = subprocess.run(
                ["wmic", "diskdrive", "get", "Index,Model,SerialNumber,Size", "/format:list"],
                capture_output=True, timeout=10,
                encoding="utf-8", errors="replace",
                creationflags=_NO_WINDOW)
            current: dict[str, str] = {}
            for line in r.stdout.splitlines():
                line = line.strip()
                if "=" in line:
                    k, v = line.split("=", 1)
                    current[k.strip()] = v.strip()
                elif current:
                    if current.get("Index", "").isdigit():
                        idx    = int(current["Index"])
                        model  = current.get("Model", "").strip() or f"Disk {idx}"
                        sb     = int(current["Size"]) if current.get("Size", "").isdigit() else 0
                        gb     = f"{round(sb / 1024**3, 1)} GB" if sb else "size unknown"
                        serial = current.get("SerialNumber", "").strip()
                        drives.append({"index": idx,
                                       "label": f"Disk {idx}  —  {model}  ({gb})",
                                       "size_bytes": sb,
                                       "serial": serial})
                    current = {}
        except Exception:
            pass

    if not drives:
        for i in range(10):
            sz = get_disk_size(i)
            if sz > 0:
                drives.append({
                    "index":      i,
                    "label":      f"Disk {i}  —  PhysicalDrive{i}  ({round(sz/1024**3,1)} GB)",
                    "size_bytes": sz,
                    "serial":     "",
                })

    drives.sort(key=lambda d: d["index"])
    return drives


# ══════════════════════════════════════════════════════════════════════════════
#  SCAN ENGINE
# ══════════════════════════════════════════════════════════════════════════════

def scan_disk(
    disk_index:  int,
    mode:        str,
    stop_on_bad: bool,
    on_block:    callable,
    on_progress: callable,
    on_finish:   callable,
    stop_event:  threading.Event,
    force_demo:  bool = False,
) -> None:
    MB         = 1024 * 1024
    block_size = 128 * MB if mode == "quick" else 512 * 1024

    # ── demo simulation ───────────────────────────────────────────────────────
    if force_demo or platform.system() != "Windows":
        DEMO_BLOCKS  = 200
        DEMO_SIZE_MB = 500 * 1024
        mb_per_block = DEMO_SIZE_MB // DEMO_BLOCKS
        bad_count    = 0

        num_clusters = random.randint(0, 3)
        bad_centres  = [random.randint(0, DEMO_BLOCKS - 1)
                        for _ in range(num_clusters)]

        def _is_bad(idx: int) -> bool:
            for c in bad_centres:
                if abs(idx - c) <= 4 and random.random() < 0.55:
                    return True
            return random.random() < 0.008

        for i in range(DEMO_BLOCKS):
            if stop_event.is_set():
                on_finish("STOPPED", bad_count)
                return
            speed = 60.0 + random.uniform(0, 70)
            time.sleep(block_size / (speed * MB))
            if _is_bad(i):
                bad_count += 1
                on_block(i, "red")
                if stop_on_bad:
                    on_progress(i * mb_per_block, DEMO_SIZE_MB, bad_count, speed)
                    on_finish("FAILED", bad_count)
                    return
            else:
                on_block(i, "green")
            on_progress((i + 1) * mb_per_block, DEMO_SIZE_MB, bad_count, speed)

        on_finish("SUCCESS" if not bad_count else "DONE_WITH_ERRORS", bad_count)
        return

    # ── real scan ─────────────────────────────────────────────────────────────
    disk_path  = f"\\\\.\\PhysicalDrive{disk_index}"
    disk_total = get_disk_size(disk_index)
    if not disk_total:
        on_finish("ERROR_SIZE", 0)
        return

    pos            = 0
    blk_idx        = 0
    bad_count      = 0
    t0             = time.time()
    last_ui_t      = 0.0
    UI_INTERVAL    = 0.25   # push UI every 250 ms regardless of block size

    try:
        with open(disk_path, "rb") as disk:
            while pos < disk_total:
                if stop_event.is_set():
                    on_finish("STOPPED", bad_count)
                    return
                try:
                    disk.seek(pos)
                    data = disk.read(block_size)
                    if not data:
                        break
                    on_block(blk_idx, "green")
                except OSError:
                    bad_count += 1
                    on_block(blk_idx, "red")
                    if stop_on_bad:
                        elapsed = max(0.001, time.time() - t0)
                        on_progress(pos // MB, disk_total // MB,
                                    bad_count, (pos // MB) / elapsed)
                        on_finish("FAILED", bad_count)
                        return

                now = time.time()
                if now - last_ui_t >= UI_INTERVAL:
                    elapsed   = max(0.001, now - t0)
                    on_progress(pos // MB, disk_total // MB,
                                bad_count, (pos // MB) / elapsed)
                    last_ui_t = now

                pos     += block_size
                blk_idx += 1

        # final 100% update
        elapsed = max(0.001, time.time() - t0)
        on_progress(disk_total // MB, disk_total // MB,
                    bad_count, (disk_total // MB) / elapsed)
        on_finish("SUCCESS" if not bad_count else "DONE_WITH_ERRORS", bad_count)

    except PermissionError:
        on_finish("ERROR_ADMIN", bad_count)
    except Exception as exc:
        on_finish(f"ERROR: {exc}", bad_count)


# ══════════════════════════════════════════════════════════════════════════════
#  PDF REPORT
# ══════════════════════════════════════════════════════════════════════════════

def generate_pdf_report(report: dict, lang: str = "EN", save_path: str | None = None) -> str:
    """Build a PDF scan report. Returns file path."""
    import os
    import datetime
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units    import mm
    from reportlab.pdfgen       import canvas as _cv
    from reportlab.lib.colors   import HexColor

    L = LANGS.get(lang, LANGS["EN"])

    C_RED    = HexColor("#FF3B30")
    C_GREEN  = HexColor("#30D158")
    C_BG     = HexColor("#FFFFFF")
    C_PANEL  = HexColor("#F2F2F7")
    C_CARD   = HexColor("#EBEBF0")
    C_BORDER = HexColor("#C6C6C8")
    C_TXT    = HexColor("#1C1C1E")
    C_SEC    = HexColor("#6C6C70")
    C_GREY   = HexColor("#AEAEB2")

    if save_path:
        path = save_path
    else:
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        ts_file = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        path    = os.path.join(desktop, f"BlackCat_DiskScan_{ts_file}.pdf")

    W, H = A4
    c    = _cv.Canvas(path, pagesize=A4)

    # ── white background on all pages ────────────────────────────────────────
    def _bg():
        c.setFillColor(C_BG)
        c.rect(0, 0, W, H, fill=1, stroke=0)

    # ── header bar ───────────────────────────────────────────────────────────
    def _draw_header():
        _bg()
        c.setFillColor(C_PANEL)
        c.rect(0, H - 52*mm, W, 52*mm, fill=1, stroke=0)
        c.setFillColor(C_RED)
        c.rect(0, H - 54*mm, W, 2*mm, fill=1, stroke=0)
        c.setFillColor(C_RED)
        c.setFont("Helvetica-Bold", 30)
        c.drawString(20*mm, H - 28*mm, "BlackCat")
        c.setFillColor(C_TXT)
        c.setFont("Helvetica", 13)
        c.drawString(20*mm, H - 40*mm, "Disk Scanner  v4.0.0   —   Scan Report")
        c.setFillColor(C_SEC)
        c.setFont("Helvetica", 9)
        now_str = datetime.datetime.now().strftime("%Y-%m-%d  %H:%M:%S")
        c.drawRightString(W - 20*mm, H - 28*mm, now_str)

    # ── footer ────────────────────────────────────────────────────────────────
    def _draw_footer():
        c.setFillColor(C_PANEL)
        c.rect(0, 0, W, 12*mm, fill=1, stroke=0)
        c.setFillColor(C_RED)
        c.rect(0, 12*mm, W, 0.5*mm, fill=1, stroke=0)
        c.setFillColor(C_SEC)
        c.setFont("Helvetica", 7)
        c.drawString(20*mm, 4*mm, "BlackCat Disk Scanner v4.0.0  —  Generated automatically")
        c.drawRightString(W - 20*mm, 4*mm, os.path.basename(path))

    # ── section title ────────────────────────────────────────────────────────
    def _section(title: str, y: float) -> float:
        y -= 8*mm
        c.setFillColor(C_PANEL)
        c.rect(15*mm, y - 8*mm, W - 30*mm, 9*mm, fill=1, stroke=0)
        c.setFillColor(C_RED)
        c.rect(15*mm, y - 8*mm, 3*mm, 9*mm, fill=1, stroke=0)
        c.setFillColor(C_TXT)
        c.setFont("Helvetica-Bold", 10)
        c.drawString(22*mm, y - 4*mm, title)
        return y - 13*mm

    # ── key-value rows ────────────────────────────────────────────────────────
    def _kv_rows(rows: list[tuple[str, str]], y: float) -> float:
        rh = 7*mm
        for key, val in rows:
            c.setFillColor(C_CARD)
            c.rect(15*mm, y - rh, W - 30*mm, rh, fill=1, stroke=0)
            c.setStrokeColor(C_BORDER)
            c.setLineWidth(0.3)
            c.rect(15*mm, y - rh, W - 30*mm, rh, fill=0, stroke=1)
            c.setFillColor(C_SEC)
            c.setFont("Helvetica", 9)
            c.drawString(20*mm, y - 5*mm, key)
            c.setFillColor(C_TXT)
            c.setFont("Helvetica-Bold", 9)
            c.drawString(80*mm, y - 5*mm, str(val))
            y -= rh
        return y

    # ── disk map ─────────────────────────────────────────────────────────────
    def _disk_map(block_states: list[str], y: float) -> float:
        bs   = 4.5*mm
        gap  = 0.8
        cols = int((W - 30*mm) / (bs + gap))
        for i, state in enumerate(block_states):
            col = i % cols
            row = i // cols
            bx  = 15*mm + col * (bs + gap)
            by  = y - row * (bs + gap) - bs
            c.setFillColor(C_GREEN if state == "green" else
                           C_RED   if state == "red"   else C_GREY)
            c.rect(bx, by, bs, bs, fill=1, stroke=0)
        rows_used = (len(block_states) - 1) // cols + 1 if block_states else 0
        # legend
        ly = y - rows_used * (bs + gap) - 6*mm
        for col, label in [(C_GREY, "Not scanned"), (C_GREEN, "OK"), (C_RED, "Bad")]:
            c.setFillColor(col)
            c.rect(15*mm, ly - 3*mm, 4*mm, 4*mm, fill=1, stroke=0)
            c.setFillColor(C_SEC)
            c.setFont("Helvetica", 8)
            c.drawString(21*mm, ly - 2*mm, label)
            ly -= 6*mm
        return ly - 4*mm

    # ── event log rows ────────────────────────────────────────────────────────
    def _log_rows(events: list[tuple], y: float) -> float:
        rh = 5.5*mm
        for ts_s, msg, _ in events:
            if y < 25*mm:
                _draw_footer()
                c.showPage()
                _bg()
                _draw_footer()
                y = H - 15*mm
            c.setFillColor(C_CARD)
            c.rect(15*mm, y - rh, W - 30*mm, rh, fill=1, stroke=0)
            c.setFillColor(C_SEC)
            c.setFont("Helvetica", 7.5)
            c.drawString(20*mm, y - 3.5*mm, ts_s)
            c.setFillColor(C_TXT)
            c.setFont("Helvetica", 7.5)
            c.drawString(42*mm, y - 3.5*mm, msg[:90])
            y -= rh
        return y

    # ── build pages ───────────────────────────────────────────────────────────
    _draw_header()
    _draw_footer()
    y = H - 60*mm

    # scan info
    y = _section(L.get("pdf_sec_info", "SCAN INFORMATION"), y)
    dur_s   = report.get("duration_s", 0)
    dur_str = f"{int(dur_s // 60)}m {int(dur_s % 60)}s"
    y = _kv_rows([
        (L.get("pdf_disk",     "Disk"),             report.get("disk_label",  "—")),
        (L.get("pdf_serial",   "Serial Number"),     report.get("disk_serial", "—")),
        (L.get("pdf_mode",     "Scan Mode"),         report.get("scan_mode",   "—").upper()),
        (L.get("pdf_sob",      "Stop on Bad"),       "Yes" if report.get("stop_on_bad") else "No"),
        (L.get("pdf_start",    "Start Time"),        report.get("start_time",  "—")),
        (L.get("pdf_end",      "End Time"),          report.get("end_time",    "—")),
        (L.get("pdf_duration", "Duration"),          dur_str),
        (L.get("pdf_result",   "Result"),            report.get("result_msg",  "—")),
    ], y)

    # statistics
    y = _section(L.get("pdf_sec_stats", "STATISTICS"), y)
    total_mb   = report.get("total_mb",   0)
    scanned_mb = report.get("scanned_mb", 0)
    pct = f"{scanned_mb / total_mb * 100:.1f}%" if total_mb else "—"
    y = _kv_rows([
        (L.get("pdf_total",   "Total Size"),     f"{total_mb:,} MB"),
        (L.get("pdf_scanned", "Scanned"),        f"{scanned_mb:,} MB  ({pct})"),
        (L.get("pdf_bad",     "Bad Sectors"),    str(report.get("bad_count", 0))),
        (L.get("pdf_speed",   "Average Speed"),  f"{report.get('avg_speed', 0):.1f} MB/s"),
    ], y)

    # disk map
    y = _section(L.get("pdf_sec_map", "DISK MAP"), y)
    y = _disk_map(report.get("block_states", []), y)

    # check page break before log
    if y < 60*mm:
        _draw_footer()
        c.showPage()
        _bg()
        _draw_footer()
        y = H - 15*mm

    # event log
    y = _section(L.get("pdf_sec_log", "EVENT LOG"), y)
    _log_rows(report.get("log_events", []), y)

    c.save()
    return path


# ══════════════════════════════════════════════════════════════════════════════
#  FLET UI
# ══════════════════════════════════════════════════════════════════════════════

def main(page: ft.Page) -> None:
    page.title         = "BlackCat Disk Scanner"
    page.bgcolor       = BG_DARK
    page.theme_mode    = ft.ThemeMode.DARK
    page.window.width  = 960
    page.window.height = 760
    page.padding       = 0

    drives     = list_drives()
    admin_mode = is_admin()

    # ── state ─────────────────────────────────────────────────────────────────
    scan_thread: threading.Thread | None = None
    stop_event      = threading.Event()
    cur_lang        = ["EN"]
    demo_mode       = [False]
    cur_theme       = ["dark"]
    scan_report     = [None]          # holds completed report dict
    _scan_start_t   = [0.0]           # epoch when scan started
    _last_progress  = [0, 0, 0.0]     # [scanned_mb, total_mb, avg_speed]
    _block_states:  list[str] = []    # per-block result ("green"/"red"/"grey")
    _scan_log:      list[tuple] = []  # (ts_str, msg, color)

    def T(key: str) -> str:
        return LANGS[cur_lang[0]].get(key, key)

    def _th() -> dict[str, str]:
        return THEMES[cur_theme[0]]

    _panels:   list[ft.Container] = []
    _dividers: list[ft.Divider]   = []

    try:
        _loop = asyncio.get_running_loop()
    except RuntimeError:
        _loop = asyncio.get_event_loop()

    def _safe_update() -> None:
        """Schedule page.update() on the Flet event loop — thread-safe."""
        try:
            if _loop.is_running():
                _loop.call_soon_threadsafe(page.update)
            else:
                page.update()
        except Exception:
            pass

    def add_log(msg: str, color: str | None = None) -> None:
        color = color or _th()["text_sec"]
        ts = time.strftime("%H:%M:%S")
        log_list.controls.append(
            ft.Text(f"[{ts}]  {msg}", size=13, color=color,
                    font_family="Monospace"))
        if len(log_list.controls) > 300:
            log_list.controls.pop(0)
        _scan_log.append((ts, msg, color))
        _safe_update()

    # ── language switcher ─────────────────────────────────────────────────────
    lang_order = ["EN", "TH"]
    lang_btns: dict[str, ft.TextButton] = {}

    def _make_lang_btn(code: str) -> ft.TextButton:
        def _on_click(_):
            cur_lang[0] = code
            apply_lang()
        btn = ft.TextButton(
            code, on_click=_on_click,
            style=ft.ButtonStyle(
                color={"": ACCENT if code == cur_lang[0] else TEXT_SEC},
                padding=ft.Padding(10, 6, 10, 6),
                text_style=ft.TextStyle(size=14, weight=ft.FontWeight.W_500),
            ))
        lang_btns[code] = btn
        return btn

    lang_row = ft.Row([_make_lang_btn(c) for c in lang_order], spacing=2)

    # ── demo toggle ───────────────────────────────────────────────────────────
    txt_demo_badge = ft.Text("", size=12, color=ACCENT2,
                              weight=ft.FontWeight.W_500, visible=False)
    demo_watermark = ft.Text(
        "", size=36, weight=ft.FontWeight.W_500,
        color=ACCENT2, opacity=0.18, visible=False,
        rotate=ft.Rotate(angle=-0.4),
        text_align=ft.TextAlign.CENTER,
    )

    def _toggle_demo(e):
        demo_mode[0] = e.control.value
        txt_demo_badge.visible = demo_mode[0]
        txt_demo_badge.value   = T("demo_badge")
        demo_watermark.visible = demo_mode[0]
        demo_watermark.value   = T("demo_banner")
        if platform.system() == "Windows":
            btn_start.disabled = not (admin_mode or demo_mode[0])
        if demo_mode[0]:
            add_log(T("demo_log"), ACCENT2)
        _safe_update()

    chk_demo = ft.Checkbox(
        label="", value=False, on_change=_toggle_demo,
        active_color=ACCENT2, check_color="#000000",
        label_style=ft.TextStyle(color=ACCENT2, size=13),
    )

    # ── serial number lookup ──────────────────────────────────────────────────
    _serial_map: dict[int, str] = {d["index"]: d.get("serial", "") for d in drives}

    def _get_serial(idx: int) -> str:
        sn = _serial_map.get(idx, "")
        return sn if sn else "—"

    # ── form controls ─────────────────────────────────────────────────────────
    txt_serial = ft.Text(
        f"S/N: {_get_serial(drives[0]['index']) if drives else '—'}",
        size=12, color=TEXT_SEC, font_family="Monospace",
    )

    def _on_drive_change(e):
        try:
            idx = int(e.control.value)
            txt_serial.value = f"S/N: {_get_serial(idx)}"
        except Exception:
            txt_serial.value = "S/N: —"
        _safe_update()

    dd_drive = ft.Dropdown(
        label="Select Drive",
        options=[ft.dropdown.Option(str(d["index"]), d["label"]) for d in drives],
        value=str(drives[0]["index"]) if drives else "0",
        width=370, bgcolor=BG_CARD, border_color=BORDER, color=TEXT_PRI,
        label_style=ft.TextStyle(color=TEXT_SEC, size=13),
        text_style=ft.TextStyle(color=TEXT_PRI, size=14),
    )
    dd_drive.on_change = _on_drive_change

    rb_quick      = ft.Radio(value="quick",    label_style=ft.TextStyle(color=TEXT_PRI, size=14))
    rb_full       = ft.Radio(value="full",     label_style=ft.TextStyle(color=TEXT_PRI, size=14))
    rb_stop_first = ft.Radio(value="stop",     label_style=ft.TextStyle(color=TEXT_PRI, size=14))
    rb_continue   = ft.Radio(value="continue", label_style=ft.TextStyle(color=TEXT_PRI, size=14))
    rg_mode = ft.RadioGroup(value="quick",
                             content=ft.Row([rb_quick, rb_full], spacing=20))
    rg_stop = ft.RadioGroup(value="stop",
                             content=ft.Row([rb_stop_first, rb_continue], spacing=20))

    # ── status widgets ────────────────────────────────────────────────────────
    txt_status   = ft.Text("", color=TEXT_SEC, size=15)
    txt_progress = ft.Text("—", color=TEXT_PRI, size=14)
    txt_bad      = ft.Text("", color=RED, size=14, weight=ft.FontWeight.W_500)
    txt_speed    = ft.Text("", color=ACCENT2, size=14)
    prog_bar     = ft.ProgressBar(value=0, bgcolor=BG_CARD, color=ACCENT, height=5)

    # ── labels ────────────────────────────────────────────────────────────────
    lbl_cfg       = ft.Text("", size=13, color=TEXT_SEC, weight=ft.FontWeight.W_500)
    lbl_status    = ft.Text("", size=13, color=TEXT_SEC, weight=ft.FontWeight.W_500)
    lbl_map       = ft.Text("", size=13, color=TEXT_SEC, weight=ft.FontWeight.W_500)
    lbl_log       = ft.Text("", size=13, color=TEXT_SEC, weight=ft.FontWeight.W_500)
    lbl_scan_mode = ft.Text("", size=13, color=TEXT_SEC)
    lbl_on_bad    = ft.Text("", size=13, color=TEXT_SEC)
    dot_unscan    = ft.Text("", size=13, color=TEXT_SEC)
    dot_ok        = ft.Text("", size=13, color=TEXT_SEC)
    dot_bad_lbl   = ft.Text("", size=13, color=TEXT_SEC)

    # ── admin badge ───────────────────────────────────────────────────────────
    _admin_icon = ft.Text(
        "✓" if admin_mode else "✗", size=14,
        weight=ft.FontWeight.W_500,
        color=GREEN if admin_mode else RED)
    txt_admin = ft.Text(
        "", size=13,
        color=GREEN if admin_mode else RED,
        italic=not admin_mode,
        weight=ft.FontWeight.W_500 if admin_mode else ft.FontWeight.W_400)
    _btn_relaunch = ft.TextButton(
        "", visible=not admin_mode,
        on_click=lambda _: relaunch_as_admin(),
        style=ft.ButtonStyle(
            color={"": ACCENT},
            padding=ft.Padding(8, 4, 8, 4),
            text_style=ft.TextStyle(size=13, weight=ft.FontWeight.W_500),
        ))
    admin_row = ft.Row(
        [_admin_icon, txt_admin, _btn_relaunch],
        spacing=6, vertical_alignment=ft.CrossAxisAlignment.CENTER)

    # ── buttons ───────────────────────────────────────────────────────────────
    btn_start_lbl = ft.Text("", color="#FFFFFF", size=15, weight=ft.FontWeight.W_500)
    btn_stop_lbl  = ft.Text("", color=ACCENT,   size=15, weight=ft.FontWeight.W_500)

    btn_start = ft.FilledButton(
        content=ft.Row([btn_start_lbl], tight=True),
        on_click=lambda _: _start_scan(),
        style=ft.ButtonStyle(
            bgcolor={"": ACCENT, "disabled": "#3A1010"},
            overlay_color={"": "#CC2A22"},
            shape=ft.RoundedRectangleBorder(radius=8),
            padding=ft.Padding(24, 14, 24, 14),
        ))
    btn_stop = ft.OutlinedButton(
        content=ft.Row([btn_stop_lbl], tight=True),
        on_click=lambda _: _confirm_stop(),
        disabled=True,
        style=ft.ButtonStyle(
            bgcolor={"": BG_CARD, "disabled": BG_CARD},
            overlay_color={"": "#2A0A0A"},
            side={"": ft.BorderSide(1, ACCENT),
                  "disabled": ft.BorderSide(1, "#5A2020")},
            shape=ft.RoundedRectangleBorder(radius=8),
            padding=ft.Padding(20, 14, 20, 14),
        ))

    btn_refresh = ft.IconButton(
        icon=ft.Icons.REFRESH,
        icon_color=ACCENT2,
        icon_size=20,
        tooltip="Refresh",
        on_click=lambda _: _safe_update(),
        style=ft.ButtonStyle(
            overlay_color={"": "#332200"},
            shape=ft.RoundedRectangleBorder(radius=8),
        ),
    )

    # ── PDF export ────────────────────────────────────────────────────────────
    def _export_pdf(_) -> None:
        if not scan_report[0]:
            add_log(T("pdf_no_report"), ACCENT2)
            return

        def _ask_and_export():
            import os, datetime
            import tkinter as tk
            from tkinter import filedialog
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            default_name = f"BlackCat_DiskScan_{ts}.pdf"
            desktop = os.path.join(os.path.expanduser("~"), "Desktop")

            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            save_path = filedialog.asksaveasfilename(
                parent=root,
                title="Save PDF Report",
                defaultextension=".pdf",
                filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")],
                initialfile=default_name,
                initialdir=desktop,
            )
            root.destroy()

            if not save_path:
                return  # user cancelled

            add_log(T("pdf_saving"), ACCENT2)
            btn_pdf.disabled = True
            _safe_update()
            try:
                path = generate_pdf_report(scan_report[0], cur_lang[0], save_path=save_path)
                add_log(T("pdf_saved").format(path=path), GREEN)
            except Exception as e:
                add_log(T("pdf_error").format(err=e), RED)
            finally:
                btn_pdf.disabled = False
                _safe_update()

        threading.Thread(target=_ask_and_export, daemon=True, name="pdf-export").start()

    btn_pdf_lbl = ft.Text("", color="#FFFFFF", size=13, weight=ft.FontWeight.W_500)
    btn_pdf = ft.FilledButton(
        content=ft.Row([ft.Icon(ft.Icons.PICTURE_AS_PDF, size=16, color="#FFFFFF"),
                        btn_pdf_lbl], spacing=6, tight=True),
        on_click=_export_pdf,
        visible=False,
        style=ft.ButtonStyle(
            bgcolor={"": "#C0392B", "disabled": "#3A1010"},
            overlay_color={"": "#96281B"},
            shape=ft.RoundedRectangleBorder(radius=8),
            padding=ft.Padding(16, 10, 16, 10),
        ))

    # ── theme toggle ──────────────────────────────────────────────────────────
    def _toggle_theme(_) -> None:
        cur_theme[0] = "light" if cur_theme[0] == "dark" else "dark"
        apply_theme()

    theme_btn = ft.IconButton(
        icon=ft.Icons.LIGHT_MODE,
        icon_color=ACCENT2,
        icon_size=20,
        tooltip="Toggle theme",
        on_click=_toggle_theme,
        style=ft.ButtonStyle(
            overlay_color={"": "#332200"},
            shape=ft.RoundedRectangleBorder(radius=8),
        ),
    )

    # ── grid ──────────────────────────────────────────────────────────────────
    grid_cells: list[ft.Container] = [
        ft.Container(width=BLOCK_PX, height=BLOCK_PX,
                     bgcolor=GREY_BLK, border_radius=3)
        for _ in range(MAX_BLOCKS)
    ]
    grid_view = ft.GridView(
        controls=grid_cells, runs_count=GRID_COLS,
        max_extent=BLOCK_PX, child_aspect_ratio=1.0,
        spacing=3, run_spacing=3, height=280,
    )

    # ── log ───────────────────────────────────────────────────────────────────
    log_list = ft.ListView(expand=True, spacing=1, auto_scroll=True)

    # ── scan callbacks ────────────────────────────────────────────────────────
    def _on_block(index: int, status: str) -> None:
        vi = min(index, MAX_BLOCKS - 1)
        grid_cells[vi].bgcolor = GREEN if status == "green" else RED
        if index < len(_block_states):
            _block_states[index] = status
        _safe_update()

    def _on_progress(scanned_mb: int, total_mb: int,
                     bad_count: int, speed: float) -> None:
        pct = scanned_mb / total_mb if total_mb else 0
        prog_bar.value     = min(pct, 1.0)
        txt_progress.value = f"{scanned_mb:,} / {total_mb:,} MB  ({pct*100:.1f}%)"
        txt_bad.value      = T("bad_n").format(n=bad_count)
        txt_speed.value    = T("speed_val").format(v=speed)
        _last_progress[0]  = scanned_mb
        _last_progress[1]  = total_mb
        _last_progress[2]  = speed
        _safe_update()

    def _on_finish(result: str, bad_count: int) -> None:
        nonlocal scan_thread
        scan_thread = None
        btn_start.disabled = False
        btn_stop.disabled  = True
        dd_drive.disabled  = False
        rg_mode.disabled   = False
        rg_stop.disabled   = False
        result_map = {
            "SUCCESS":          (T("res_ok"),                             GREEN),
            "DONE_WITH_ERRORS": (T("res_errors").format(n=bad_count),     ACCENT2),
            "FAILED":           (T("res_failed").format(n=bad_count),     RED),
            "STOPPED":          (T("res_stopped"),                        ACCENT2),
            "ERROR_ADMIN":      (T("res_admin"),                          RED),
            "ERROR_SIZE":       (T("res_size"),                           RED),
        }
        msg, color = result_map.get(result, (result, TEXT_SEC))
        txt_status.value = msg
        txt_status.color = color
        add_log(msg, color)

        # build report for PDF export
        idx = int(dd_drive.value or 0)
        disk_label  = next((d["label"]  for d in drives if d["index"] == idx), f"Disk {idx}")
        disk_serial = _serial_map.get(idx, "—")
        duration    = time.time() - _scan_start_t[0]
        scan_report[0] = {
            "disk_label":   disk_label,
            "disk_serial":  disk_serial if disk_serial else "—",
            "scan_mode":    rg_mode.value,
            "stop_on_bad":  rg_stop.value == "stop",
            "start_time":   time.strftime("%Y-%m-%d %H:%M:%S",
                                          time.localtime(_scan_start_t[0])),
            "end_time":     time.strftime("%Y-%m-%d %H:%M:%S"),
            "duration_s":   duration,
            "total_mb":     _last_progress[1],
            "scanned_mb":   _last_progress[0],
            "bad_count":    bad_count,
            "result":       result,
            "result_msg":   msg,
            "avg_speed":    _last_progress[2],
            "block_states": list(_block_states),
            "log_events":   list(_scan_log),
        }
        btn_pdf.visible = True
        _safe_update()

    # ── start scan ────────────────────────────────────────────────────────────
    def _start_scan() -> None:
        nonlocal scan_thread, stop_event
        if scan_thread and scan_thread.is_alive():
            return

        idx         = int(dd_drive.value or 0)
        mode        = rg_mode.value
        stop_on_bad = rg_stop.value == "stop"

        stop_event = threading.Event()

        # reset tracking state
        _scan_start_t[0] = time.time()
        _last_progress[:] = [0, 0, 0.0]
        _block_states.clear()
        _block_states.extend(["grey"] * MAX_BLOCKS)
        _scan_log.clear()
        scan_report[0] = None
        btn_pdf.visible = False

        for cell in grid_cells:
            cell.bgcolor = _th()["grey_blk"]
        log_list.controls.clear()
        prog_bar.value     = 0
        txt_progress.value = "—"
        txt_bad.value      = T("bad_zero")
        txt_speed.value    = T("speed_init")
        txt_status.value   = T("scanning").format(idx=idx, mode=mode)
        txt_status.color   = ACCENT2
        btn_start.disabled = True
        btn_stop.disabled  = False
        dd_drive.disabled  = True
        rg_mode.disabled   = True
        rg_stop.disabled   = True

        add_log(T("log_start").format(idx=idx, mode=mode, sob=stop_on_bad), ACCENT2)
        _safe_update()

        scan_thread = threading.Thread(
            target=scan_disk,
            args=(idx, mode, stop_on_bad,
                  _on_block, _on_progress, _on_finish,
                  stop_event, demo_mode[0]),
            daemon=True, name=f"scan-disk{idx}")
        scan_thread.start()

    # ── confirm stop ──────────────────────────────────────────────────────────
    def _confirm_stop() -> None:
        def _do_stop(_) -> None:
            confirm_dlg.open = False
            _safe_update()
            stop_event.set()
            txt_status.value  = T("stopping")
            txt_status.color  = ACCENT2
            btn_stop.disabled = True
            add_log(T("stop_user"), ACCENT2)
            _safe_update()

        def _cancel(_) -> None:
            confirm_dlg.open = False
            _safe_update()

        confirm_dlg = ft.AlertDialog(
            modal=True, open=True,
            title=ft.Text(T("dlg_title"), color=_th()["text_pri"],
                          weight=ft.FontWeight.W_500, size=16),
            content=ft.Text(T("dlg_body"), color=_th()["text_sec"], size=14),
            bgcolor=_th()["card"],
            actions=[
                ft.TextButton(T("dlg_cancel"), on_click=_cancel,
                              style=ft.ButtonStyle(
                                  color={"": TEXT_SEC},
                                  text_style=ft.TextStyle(size=14))),
                ft.FilledButton(
                    T("dlg_confirm"), on_click=_do_stop,
                    style=ft.ButtonStyle(
                        bgcolor={"": ACCENT}, color={"": "#FFFFFF"},
                        shape=ft.RoundedRectangleBorder(radius=6),
                        text_style=ft.TextStyle(size=14))),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        page.overlay.append(confirm_dlg)
        _safe_update()

    # ── apply theme ───────────────────────────────────────────────────────────
    def apply_theme() -> None:
        th      = _th()
        is_dark = cur_theme[0] == "dark"

        page.bgcolor    = th["bg"]
        page.theme_mode = ft.ThemeMode.DARK if is_dark else ft.ThemeMode.LIGHT

        header.bgcolor = th["panel"]
        header.border  = ft.Border(bottom=ft.BorderSide(1, th["border"]))

        for p in _panels:
            p.bgcolor = th["panel"]
            p.border  = ft.Border(
                top=ft.BorderSide(1, th["border"]), bottom=ft.BorderSide(1, th["border"]),
                left=ft.BorderSide(1, th["border"]), right=ft.BorderSide(1, th["border"]))

        for d in _dividers:
            d.color = th["border"]

        for w in [lbl_cfg, lbl_status, lbl_map, lbl_log, lbl_scan_mode, lbl_on_bad,
                  dot_unscan, dot_ok, dot_bad_lbl, txt_serial, txt_subtitle]:
            w.color = th["text_sec"]

        txt_progress.color = th["text_pri"]

        for rb in [rb_quick, rb_full, rb_stop_first, rb_continue]:
            rb.label_style = ft.TextStyle(color=th["text_pri"], size=14)

        dd_drive.bgcolor      = th["card"]
        dd_drive.border_color = th["border"]
        dd_drive.color        = th["text_pri"]
        dd_drive.label_style  = ft.TextStyle(color=th["text_sec"], size=13)
        dd_drive.text_style   = ft.TextStyle(color=th["text_pri"], size=14)

        prog_bar.bgcolor = th["card"]

        for cell in grid_cells:
            if cell.bgcolor not in (GREEN, RED):
                cell.bgcolor = th["grey_blk"]

        theme_btn.icon       = ft.Icons.LIGHT_MODE if is_dark else ft.Icons.DARK_MODE
        theme_btn.icon_color = ACCENT2 if is_dark else TEXT_SEC

        _safe_update()

    # ── apply language ────────────────────────────────────────────────────────
    def apply_lang() -> None:
        for code, btn in lang_btns.items():
            btn.style = ft.ButtonStyle(
                color={"": ACCENT if code == cur_lang[0] else _th()["text_sec"]},
                padding=ft.Padding(10, 6, 10, 6),
                text_style=ft.TextStyle(size=14, weight=ft.FontWeight.W_500),
            )
        lbl_cfg.value       = T("cfg_title")
        lbl_status.value    = T("status_title")
        lbl_map.value       = T("map_title")
        lbl_log.value       = T("log_title")
        txt_admin.value     = T("admin_ok") if admin_mode else T("admin_no")
        _btn_relaunch.text  = T("btn_relaunch")
        lbl_scan_mode.value = T("scan_mode")
        lbl_on_bad.value    = T("on_bad")
        dd_drive.label      = T("select_drive")
        rb_quick.label      = T("mode_quick")
        rb_full.label       = T("mode_full")
        rb_stop_first.label = T("stop_first")
        rb_continue.label   = T("scan_finish")
        btn_start_lbl.value = f"▶  {T('btn_start')}"
        btn_stop_lbl.value  = f"■  {T('btn_stop')}"
        btn_pdf_lbl.value   = T("btn_pdf")
        dot_unscan.value    = T("leg_unscan")
        dot_ok.value        = T("leg_ok")
        dot_bad_lbl.value   = T("leg_bad")
        chk_demo.label      = T("demo_mode")
        txt_demo_badge.value = T("demo_badge")
        demo_watermark.value = T("demo_banner")
        if not (scan_thread and scan_thread.is_alive()):
            txt_status.value = T("ready")
            txt_bad.value    = T("bad_zero")
            txt_speed.value  = T("speed_init")
        _safe_update()

    # ── UI helpers ────────────────────────────────────────────────────────────
    def _dot_row(color: str, label_widget: ft.Text) -> ft.Row:
        return ft.Row([
            ft.Container(width=12, height=12, bgcolor=color, border_radius=2),
            label_widget,
        ], spacing=6)

    def _panel(header_widget: ft.Text, *children,
               width=None, height=None, expand=False) -> ft.Container:
        th = _th()
        div = ft.Divider(height=1, color=th["border"])
        _dividers.append(div)
        c = ft.Container(
            content=ft.Column(
                [header_widget, div, *children],
                spacing=10, expand=expand),
            bgcolor=th["panel"],
            border=ft.Border(
                top=ft.BorderSide(1, th["border"]), bottom=ft.BorderSide(1, th["border"]),
                left=ft.BorderSide(1, th["border"]), right=ft.BorderSide(1, th["border"])),
            border_radius=8,
            padding=ft.Padding(18, 14, 18, 14),
            width=width, height=height, expand=expand,
        )
        _panels.append(c)
        return c

    # ── layout ────────────────────────────────────────────────────────────────
    config_panel = _panel(
        lbl_cfg,
        dd_drive,
        txt_serial,
        ft.Column([lbl_scan_mode, rg_mode], spacing=4),
        ft.Column([lbl_on_bad, rg_stop], spacing=4),
        ft.Row([btn_start, btn_stop], spacing=12),
        ft.Row([chk_demo], spacing=0,
               vertical_alignment=ft.CrossAxisAlignment.CENTER),
        width=390,
    )

    status_panel = _panel(
        lbl_status,
        txt_status,
        prog_bar,
        ft.Row([txt_progress, ft.Container(expand=True),
                txt_speed, txt_bad, btn_refresh],
               spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        ft.Row([btn_pdf], spacing=0),
        expand=True,
    )

    grid_stack = ft.Stack(
        controls=[
            ft.Container(content=grid_view),
            ft.Container(content=demo_watermark,
                         alignment=ft.Alignment(0, 0), height=280),
        ],
        height=280,
    )

    map_panel = _panel(
        lbl_map,
        ft.Row([ft.Container(expand=True),
                _dot_row(GREY_BLK, dot_unscan),
                _dot_row(GREEN, dot_ok),
                _dot_row(RED, dot_bad_lbl)], spacing=14),
        grid_stack,
    )

    log_panel = _panel(lbl_log, ft.Container(content=log_list, height=140))

    txt_subtitle = ft.Text("Disk Scanner  v4.0.1", size=13, color=TEXT_SEC)

    header = ft.Container(
        content=ft.Row([
            ft.Column([
                ft.Text("BlackCat", size=26,
                        weight=ft.FontWeight.BOLD, color=ACCENT),
                txt_subtitle,
            ], spacing=1),
            ft.Container(expand=True),
            admin_row,
            ft.Container(width=8),
            theme_btn,
            ft.Container(width=8),
            lang_row,
        ]),
        bgcolor=BG_PANEL,
        padding=ft.Padding(24, 12, 24, 12),
        border=ft.Border(bottom=ft.BorderSide(1, BORDER)),
    )

    body = ft.Container(
        content=ft.Column([
            ft.Row([config_panel, status_panel], spacing=14,
                   alignment=ft.MainAxisAlignment.START,
                   vertical_alignment=ft.CrossAxisAlignment.START),
            map_panel,
            log_panel,
        ], spacing=14, scroll=ft.ScrollMode.AUTO),
        padding=ft.Padding(20, 18, 20, 18),
        expand=True,
    )

    page.add(ft.Column([header, body], spacing=0, expand=True))

    # ── auto-refresh every 10 s ───────────────────────────────────────────────
    _alive = [True]   # flag to stop thread when session dies

    def _auto_refresh() -> None:
        while _alive[0]:
            time.sleep(10)
            if not _alive[0]:
                break
            _safe_update()

    _refresh_thread = threading.Thread(
        target=_auto_refresh, daemon=True, name="auto-refresh")
    _refresh_thread.start()

    apply_lang()
    apply_theme()

    if not admin_mode and platform.system() == "Windows":
        btn_start.disabled = True
        add_log("⚠  Not running as Administrator — scan disabled.", RED)
        add_log("   Enable Demo Mode to test UI without admin rights.")
    else:
        add_log(T("log_ready"))

    _safe_update()


# ══════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import asyncio
    import os

    # ── Monkey-patch the exact method that throws on Windows pipe teardown ──
    # _ProactorBasePipeTransport._call_connection_lost calls sock.shutdown()
    # after Flutter already closed the connection → WinError 10054 → process hangs
    try:
        from asyncio.proactor_events import _ProactorBasePipeTransport

        _orig_call_connection_lost = _ProactorBasePipeTransport._call_connection_lost

        def _safe_call_connection_lost(self, exc):
            try:
                _orig_call_connection_lost(self, exc)
            except (ConnectionResetError, OSError):
                pass  # swallow Windows pipe teardown noise

        _ProactorBasePipeTransport._call_connection_lost = _safe_call_connection_lost
    except Exception:
        pass

    try:
        ft.run(main)
    except Exception:
        pass
    finally:
        os._exit(0)