"""
BlackCat SMART v7.0 — Disk Health Analyzer
Platform : Windows (primary), macOS, Linux
License  : Internal use
Security : READ-ONLY — no disk writes, no network, no registry
"""

import datetime
import json
import os
import platform
import re
import subprocess
import sys
import tempfile
import threading

import flet as ft

# ── App metadata ──────────────────────────────────────────────
APP_VERSION = "7.0"
APP_NAME    = "BlackCat SMART"

# ── Platform flags ────────────────────────────────────────────
_OS        = platform.system()
IS_WINDOWS = _OS == "Windows"
IS_MAC     = _OS == "Darwin"
IS_LINUX   = _OS == "Linux"

# ── Windows: hide console for subprocess ──────────────────────
_NO_WINDOW = 0x08000000 if IS_WINDOWS else 0

# ── Risk thresholds ───────────────────────────────────────────
RISK = {
    "temp_warn":       55,
    "temp_crit":       70,
    "health_warn":     80,   # NVMe % used
    "health_crit":     90,
    "hours_warn":   20000,
    "hours_crit":   40000,
    "pending_warn":     1,
    "realloc_warn":     1,
}

# ═══════════════════════════════════════════════════════════════
# FLET COMPATIBILITY HELPERS
# flet < 0.80 uses ft.border.all() / ft.padding.only()
# flet ≥ 0.80 uses ft.Border() / ft.Padding()
# ═══════════════════════════════════════════════════════════════
_NEW_FLET = hasattr(ft, "Padding")

def _pad(l=0, t=0, r=0, b=0):
    return ft.Padding(l, t, r, b) if _NEW_FLET else ft.padding.only(left=l, top=t, right=r, bottom=b)

def _margin(l=0, t=0, r=0, b=0):
    return ft.Margin(l, t, r, b) if _NEW_FLET else ft.margin.only(left=l, top=t, right=r, bottom=b)

def _border_all(w, c):
    if _NEW_FLET:
        s = ft.BorderSide(w, c)
        return ft.Border(left=s, top=s, right=s, bottom=s)
    return ft.border.all(w, c)

def _border_bottom(w, c):
    return ft.Border(bottom=ft.BorderSide(w, c)) if _NEW_FLET else ft.border.only(bottom=ft.BorderSide(w, c))

def _align_center():
    return ft.Alignment(0, 0) if _NEW_FLET else ft.alignment.center

# ═══════════════════════════════════════════════════════════════
# PRIVILEGE HANDLING
# ═══════════════════════════════════════════════════════════════

def _is_privileged() -> bool:
    if IS_WINDOWS:
        try:
            import ctypes
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            return False
    return os.geteuid() == 0


def _elevate_windows():
    """Re-launch with UAC elevation (Windows only)."""
    import ctypes
    ctypes.windll.shell32.ShellExecuteW(
        None, "runas", sys.executable,
        " ".join(f'"{a}"' for a in sys.argv), None, 1
    )
    sys.exit()


# Windows: request UAC at startup
# macOS/Linux: run as normal user; sudo is added per-command in run_privileged()
if IS_WINDOWS and not _is_privileged():
    _elevate_windows()


# ═══════════════════════════════════════════════════════════════
# SAFE COMMAND RUNNERS
# ═══════════════════════════════════════════════════════════════

def run_safe(cmd: list, timeout: int = 30):
    """
    Run a subprocess safely:
    - shell=False always (prevents shell injection)
    - No console window on Windows
    - Hard timeout
    Returns CompletedProcess or None on any error.
    """
    try:
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
            creationflags=_NO_WINDOW,
        )
    except Exception:
        return None


def run_privileged(cmd: list, timeout: int = 30):
    """
    Run a command that needs elevated privileges:
    - Windows  : UAC was obtained at startup — use run_safe directly
    - macOS    : osascript with administrator privileges (no terminal needed)
                 Uses temp files to capture full output (preserves newlines)
    - Linux    : prepend sudo
    """
    if IS_WINDOWS or _is_privileged():
        return run_safe(cmd, timeout)

    if IS_MAC:
        def _q(s: str) -> str:
            return "'" + s.replace("'", "'\\''") + "'"

        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".sh", delete=False, prefix="/tmp/bcsc_"
            ) as tf:
                out_path = tf.name + ".out"
                err_path = tf.name + ".err"
                sh_path  = tf.name
                tf.write(
                    " ".join(_q(c) for c in cmd)
                    + f" > {_q(out_path)} 2> {_q(err_path)}"
                )

            os.chmod(sh_path, 0o700)
            osc_result = subprocess.run(
                ["osascript", "-e",
                 f"do shell script {_q('/bin/sh ' + sh_path)} with administrator privileges"],
                capture_output=True, text=True, timeout=timeout,
            )

            stdout = open(out_path, "r", errors="replace").read() if os.path.isfile(out_path) else ""
            stderr = open(err_path, "r", errors="replace").read() if os.path.isfile(err_path) else ""

            class _R:
                def __init__(self, o, e, rc):
                    self.stdout = o; self.stderr = e; self.returncode = rc

            return _R(stdout, stderr, osc_result.returncode)
        except Exception:
            return None
        finally:
            for p in (sh_path, out_path, err_path):
                try: os.unlink(p)
                except Exception: pass

    # Linux
    return run_safe(["sudo"] + cmd, timeout)


# ═══════════════════════════════════════════════════════════════
# SMARTCTL PATH DISCOVERY
# ═══════════════════════════════════════════════════════════════

def _find_smartctl() -> str:
    """
    Locate the smartctl binary.
    Search order:
      1. PyInstaller bundle (_MEIPASS)
      2. Directory of this script (__file__)
      3. Directory of sys.executable + parent dirs (handles .app bundles)
      4. Hardcoded Homebrew / system paths
      5. PATH environment variable

    Security: only returns paths where the file exists and is executable.
    Never constructs paths from user-controlled input.
    """
    SC = "smartctl.exe" if IS_WINDOWS else "smartctl"
    dirs: list = []

    if hasattr(sys, "_MEIPASS"):
        dirs.append(sys._MEIPASS)

    try:
        dirs.append(os.path.dirname(os.path.abspath(__file__)))
    except Exception:
        pass

    try:
        exe = os.path.dirname(os.path.abspath(sys.executable))
        for rel in (".", "..", "../Resources", "../Frameworks", "../..", "../../MacOS", "../../Resources"):
            dirs.append(os.path.normpath(os.path.join(exe, rel)))
    except Exception:
        pass

    if not IS_WINDOWS:
        dirs += [
            "/opt/homebrew/bin", "/opt/homebrew/sbin",
            "/usr/local/bin",    "/usr/local/sbin",
            "/opt/local/bin",
            "/usr/bin",          "/usr/sbin",
        ]

    dirs += [p for p in os.environ.get("PATH", "").split(os.pathsep) if p]

    seen: set = set()
    for d in dirs:
        if not d or d in seen:
            continue
        seen.add(d)
        path = os.path.join(d, SC)
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path

    return "smartctl.exe" if IS_WINDOWS else ""


# ═══════════════════════════════════════════════════════════════
# DISK DISCOVERY
# ═══════════════════════════════════════════════════════════════

def _disk_idx(name: str) -> int:
    """Extract a numeric disk index from a device name."""
    for pat in (r"physicaldrive(\d+)", r"nvme(\d+)", r"disk(\d+)", r"(\d+)$"):
        m = re.search(pat, name.lower())
        if m:
            return int(m.group(1))
    last = name[-1] if name else "a"
    return ord(last.lower()) - ord("a") if last.isalpha() else 0


def _label_windows(idx: int) -> str:
    """Return drive letters for a Windows disk index (e.g. 'C:, D:')."""
    if not isinstance(idx, int) or not 0 <= idx <= 99:
        return "N/A"
    res = run_safe([
        "powershell", "-NoProfile", "-NonInteractive", "-Command",
        f"Get-Partition -DiskNumber {idx} -ErrorAction SilentlyContinue"
        f" | Get-Volume -ErrorAction SilentlyContinue"
        f" | Select-Object -ExpandProperty DriveLetter",
    ])
    if res and res.stdout.strip():
        return ", ".join(f"{l.strip()}:" for l in res.stdout.splitlines() if l.strip())
    return "No Letter"


def _size_windows(idx: int) -> int:
    """Return disk size in GB for a Windows disk index."""
    if not isinstance(idx, int) or not 0 <= idx <= 99:
        return 0
    res = run_safe([
        "powershell", "-NoProfile", "-NonInteractive", "-Command",
        f"(Get-Disk -Number {idx} -ErrorAction SilentlyContinue).Size",
    ])
    val = res.stdout.strip() if res else ""
    return round(int(val) / 1024 ** 3) if val.isdigit() else 0


def _label_size_mac(device: str) -> tuple:
    """Return (mount_label, size_gb) for a macOS device using diskutil."""
    base = re.sub(r"s\d+$", "", os.path.basename(device))
    res  = run_safe(["diskutil", "info", "-plist", f"/dev/{base}"])
    if not res or not res.stdout.strip():
        return "N/A", 0
    try:
        import plistlib
        info       = plistlib.loads(res.stdout.encode())
        size_bytes = info.get("TotalSize") or info.get("Size") or 0
        size_gb    = round(size_bytes / 1024 ** 3) if size_bytes else 0
        mount      = info.get("MountPoint") or info.get("VolumeName") or info.get("MediaName") or "No Mount"
        return mount, size_gb
    except Exception:
        return "N/A", 0


def _label_size_linux(device: str) -> tuple:
    """Return (mount_label, size_gb) for a Linux device using lsblk."""
    res = run_safe(["lsblk", "-J", "-o", "NAME,SIZE,MOUNTPOINT", device])
    if not res or not res.stdout.strip():
        return "N/A", 0
    try:
        blocks = json.loads(res.stdout).get("blockdevices", [])
        if not blocks:
            return "N/A", 0
        dev  = blocks[0]
        # parse size string e.g. "500G" → GB
        s    = dev.get("size", "0").strip().upper()
        m    = re.match(r"([\d.]+)\s*([KMGT]?)", s)
        mul  = {"K": 0, "M": 0, "G": 1, "T": 1024}.get(m.group(2), 1) if m else 1
        size = int(float(m.group(1)) * mul) if m else 0

        mounts: list = []
        def _collect(node):
            mp = node.get("mountpoint") or node.get("mountpoints", [])
            if isinstance(mp, str) and mp:
                mounts.append(mp)
            elif isinstance(mp, list):
                mounts += [x for x in mp if x]
            for child in node.get("children", []):
                _collect(child)
        _collect(dev)
        return (", ".join(mounts) or "No Mount"), size
    except Exception:
        return "N/A", 0


def get_disk_list() -> list:
    """
    Scan for all disks using 'smartctl --scan'.
    Returns a list of device dicts, or [{"_error": True}] if smartctl is missing.
    READ-ONLY — does not modify any disk.
    """
    sc = _find_smartctl()
    if not sc or not os.path.isfile(sc):
        return [{"_error": True}]

    devices: list = []

    def _build(name: str, dtype) -> dict:
        idx = _disk_idx(name)
        if IS_WINDOWS:
            label, size_gb = _label_windows(idx), _size_windows(idx)
        elif IS_MAC:
            label, size_gb = _label_size_mac(name)
        else:
            label, size_gb = _label_size_linux(name)
        size_str = f"{size_gb} GB" if size_gb < 1024 else f"{round(size_gb / 1024, 1)} TB"
        display  = f"DISK {idx}  [{label}]  {size_str}"
        if dtype:
            display += f"  ({dtype})"
        return {"real": name, "display": display, "label": label, "idx": idx, "dtype": dtype}

    # ── text scan (most reliable) ────────────────────────────
    res = run_privileged([sc, "--scan"])
    if res and res.stdout.strip():
        for line in res.stdout.splitlines():
            parts = line.split()
            if not parts:
                continue
            name  = parts[0]
            dtype = parts[parts.index("-d") + 1] if "-d" in parts else None
            devices.append(_build(name, dtype))

    # ── JSON fallback ─────────────────────────────────────────
    if not devices:
        res2 = run_privileged([sc, "--scan", "--json"])
        if res2 and res2.stdout.strip():
            try:
                for d in json.loads(res2.stdout).get("devices", []):
                    name = d.get("name", "")
                    if name:
                        devices.append(_build(name, d.get("type")))
            except (json.JSONDecodeError, KeyError):
                pass

    return devices


# ═══════════════════════════════════════════════════════════════
# SMART DATA READER
# ═══════════════════════════════════════════════════════════════

def _to_int(val) -> int:
    try:
        return int(str(val).split()[0].replace(",", ""))
    except (ValueError, IndexError):
        return 0


def get_smart_data(device: str, label: str, dtype: str = None) -> tuple:
    """
    Read SMART attributes using 'smartctl -a' (read-only flag).
    Returns (rows, summary, raw_json_str).
    rows    : list of (label, value, status, ft_color)
    summary : dict with score, verdict, verdict_detail, risks, warnings
    raw     : raw JSON string from smartctl
    """
    sc  = _find_smartctl()
    cmd = [sc, "-a", "-d", dtype, device, "--json"] if dtype else [sc, "-a", device, "--json"]

    res = run_privileged(cmd)
    raw = res.stdout if res else ""

    if not raw.strip():
        return [], {
            "score": 0, "verdict": "อ่านข้อมูลไม่ได้",
            "verdict_detail": "ไม่สามารถเชื่อมต่อกับ disk",
            "risks": ["❌ ไม่สามารถอ่านข้อมูล SMART ได้"], "warnings": [],
        }, raw

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return [], {
            "score": 0, "verdict": "Parse Error",
            "verdict_detail": "JSON จาก smartctl ไม่ถูกต้อง",
            "risks": ["❌ JSON parse failed"], "warnings": [],
        }, raw

    rows:     list = []
    risks:    list = []
    warnings: list = []
    score:    int  = 100

    C = ft.Colors  # alias

    # ── Identity ────────────────────────────────────────────
    model    = data.get("model_name", "N/A")
    serial   = data.get("serial_number", "N/A")
    firmware = data.get("firmware_version", "N/A")
    dtype_str = (
        "NVMe SSD" if data.get("nvme_smart_health_information_log")
        else "SATA SSD" if "ssd" in model.lower()
        else "HDD"
    )
    rows += [
        ("💾  ยี่ห้อ / รุ่น",   model,    dtype_str,  C.CYAN_200),
        ("🔢  Serial Number",   serial,   "S/N",       C.BLUE_200),
        ("⚡  Firmware",        firmware, "Version",   C.BLUE_200),
        ("📍  Drive / Mount",   label,    "Location",  C.AMBER_300),
    ]

    # ── SMART overall status ─────────────────────────────────
    passed = data.get("smart_status", {}).get("passed")
    if passed is True:
        rows.append(("🛡️  SMART Status", "PASSED", "ผ่านการตรวจ", C.GREEN_400))
    elif passed is False:
        rows.append(("🛡️  SMART Status", "FAILED ⚠️", "ดิสก์ล้มเหลว!", C.RED_400))
        risks.append("❌ SMART Status FAILED — ดิสก์อาจพังแล้ว!")
        score -= 60

    # ── NVMe ─────────────────────────────────────────────────
    nvme = data.get("nvme_smart_health_information_log", {})
    if nvme:
        used     = int(nvme.get("percentage_used", 0))
        health   = 100 - used
        temp     = int(nvme.get("temperature", 0))
        w_tb     = round(int(nvme.get("data_units_written", 0)) * 512 * 1000 / 1024 ** 4, 2)
        cycles   = int(nvme.get("power_cycles", 0))
        unsafe   = int(nvme.get("unsafe_shutdowns", 0))
        merr     = int(nvme.get("media_errors", 0))
        elog     = int(nvme.get("num_err_log_entries", 0))

        if used >= RISK["health_crit"]:
            hc, hn = C.RED_400, "⚠️ วิกฤต"
            risks.append(f"❌ อายุดิสก์ใช้ไปแล้ว {used}% — ใกล้หมดอายุมาก!")
            score -= 40
        elif used >= RISK["health_warn"]:
            hc, hn = C.ORANGE_400, "⚠️ เฝ้าระวัง"
            warnings.append(f"⚠️ อายุดิสก์ใช้ไปแล้ว {used}%")
            score -= 15
        else:
            hc, hn = C.GREEN_400, "ปกติ"
        rows.append(("❤️  สุขภาพดิสก์", f"{health} %", hn, hc))

        if temp >= RISK["temp_crit"]:
            tc, tn = C.RED_400, "🔥 ร้อนมาก!"
            risks.append(f"🔥 อุณหภูมิสูงวิกฤต {temp}°C!")
            score -= 20
        elif temp >= RISK["temp_warn"]:
            tc, tn = C.ORANGE_400, "⚠️ เริ่มร้อน"
            warnings.append(f"🌡️ อุณหภูมิเริ่มสูง {temp}°C")
            score -= 5
        else:
            tc, tn = C.CYAN_200, "ปกติ"
        rows.append(("🌡️  อุณหภูมิ", f"{temp} °C", tn, tc))

        rows.append(("✍️  เขียนสะสม",       f"{w_tb} TB",   "TBW",   C.CYAN_200))
        rows.append(("🔄  Power Cycles",     f"{cycles:,}", "ครั้ง", C.BLUE_200))

        if unsafe > 50:
            rows.append(("⚠️  ปิดเครื่องผิดปกติ", f"{unsafe:,}", "สูง!", C.ORANGE_400))
            warnings.append(f"⚠️ ปิดเครื่องผิดปกติ {unsafe} ครั้ง")
            score -= 5
        else:
            rows.append(("⚠️  ปิดเครื่องผิดปกติ", f"{unsafe:,}", "ปกติ", C.CYAN_200))

        if merr > 0:
            rows.append(("💥  Media Errors", f"{merr:,}", "มีปัญหา!", C.RED_400))
            risks.append(f"❌ พบ Media Errors {merr} ครั้ง — ข้อมูลอาจเสียหาย!")
            score -= 30
        else:
            rows.append(("💥  Media Errors", "0", "ดี ✓", C.GREEN_400))

        if elog > 0:
            rows.append(("📋  Error Log", f"{elog:,}", "พบ Error", C.ORANGE_400))
            score -= 5
        else:
            rows.append(("📋  Error Log", "0", "สะอาด ✓", C.GREEN_400))

    # ── ATA / HDD / SATA ─────────────────────────────────────
    ata = data.get("ata_smart_attributes", {}).get("table", [])
    if ata:
        am = {a.get("name"): a for a in ata}

        def _raw(name: str):
            a = am.get(name)
            return a.get("raw", {}).get("string") if a else None

        # Temperature
        t_raw = _raw("Temperature_Celsius") or _raw("Airflow_Temperature_Cel") or _raw("Temperature_Internal")
        if t_raw:
            temp = _to_int(t_raw)
            if temp >= RISK["temp_crit"]:
                tc, tn = C.RED_400, "🔥 ร้อนมาก!"
                risks.append(f"🔥 อุณหภูมิสูงวิกฤต {temp}°C!")
                score -= 20
            elif temp >= RISK["temp_warn"]:
                tc, tn = C.ORANGE_400, "⚠️ เริ่มร้อน"
                warnings.append(f"🌡️ อุณหภูมิเริ่มสูง {temp}°C")
                score -= 5
            else:
                tc, tn = C.CYAN_200, "ปกติ"
            rows.append(("🌡️  อุณหภูมิ", f"{temp} °C", tn, tc))

        # Power-on hours
        h_raw = _raw("Power_On_Hours")
        if h_raw:
            hours = _to_int(h_raw)
            years = round(hours / 8760, 1)
            if hours >= RISK["hours_crit"]:
                hc, hn = C.RED_400, "⚠️ อายุมาก"
                risks.append(f"⏰ ใช้งาน {hours:,} ชม. ({years} ปี) — เกินอายุมาตรฐาน")
                score -= 25
            elif hours >= RISK["hours_warn"]:
                hc, hn = C.ORANGE_400, "⚠️ เฝ้าระวัง"
                warnings.append(f"⏰ ใช้งาน {hours:,} ชั่วโมง")
                score -= 10
            else:
                hc, hn = C.CYAN_200, "ปกติ"
            rows.append(("⏰  ชั่วโมงใช้งาน", f"{hours:,} ชม. ({years} ปี)", hn, hc))

        # Power cycles
        c_raw = _raw("Power_Cycle_Count")
        if c_raw:
            rows.append(("🔄  Power Cycles", f"{_to_int(c_raw):,} ครั้ง", "เปิดปิดเครื่อง", C.BLUE_200))

        # Reallocated sectors
        r_raw = _raw("Reallocated_Sector_Ct")
        if r_raw is not None:
            v = _to_int(r_raw)
            if v >= RISK["realloc_warn"]:
                rows.append(("💔  Bad Sectors", f"{v:,}", "⚠️ พบเซกเตอร์เสีย!", C.RED_400))
                risks.append(f"❌ Bad Sectors {v} จุด — ดิสก์มีปัญหาร้ายแรง!")
                score -= 35
            else:
                rows.append(("💔  Bad Sectors", "0", "ดี ✓", C.GREEN_400))

        # Pending sectors
        p_raw = _raw("Current_Pending_Sector")
        if p_raw is not None:
            v = _to_int(p_raw)
            if v >= RISK["pending_warn"]:
                rows.append(("⏳  Pending Sectors", f"{v:,}", "⚠️ รอแก้ไข!", C.ORANGE_400))
                warnings.append(f"⚠️ Pending Sectors {v} จุด")
                score -= 15
            else:
                rows.append(("⏳  Pending Sectors", "0", "ดี ✓", C.GREEN_400))

        # Uncorrectable errors
        u_raw = _raw("Offline_Uncorrectable")
        if u_raw is not None:
            v = _to_int(u_raw)
            if v > 0:
                rows.append(("🚨  Uncorrectable", f"{v:,}", "⚠️ แก้ไขไม่ได้!", C.RED_400))
                risks.append(f"❌ Uncorrectable Errors {v} — ข้อมูลเสียหายถาวร!")
                score -= 25
            else:
                rows.append(("🚨  Uncorrectable", "0", "ดี ✓", C.GREEN_400))

        # Seek error rate (HDD)
        sk_raw = _raw("Seek_Error_Rate")
        if sk_raw and _to_int(sk_raw) > 10000:
            rows.append(("🔍  Seek Errors", f"{_to_int(sk_raw):,}", "⚠️ หัวอ่านผิดปกติ", C.ORANGE_400))
            warnings.append("⚠️ Seek Error Rate สูง — หัวอ่านอาจมีปัญหา")
            score -= 10

        # Spin retry (HDD)
        sp_raw = _raw("Spin_Retry_Count")
        if sp_raw and _to_int(sp_raw) > 0:
            v = _to_int(sp_raw)
            rows.append(("🌀  Spin Retry", f"{v:,}", "⚠️ มอเตอร์มีปัญหา", C.ORANGE_400))
            warnings.append(f"⚠️ Spin Retry = {v} — มอเตอร์อาจเสื่อม")
            score -= 10

    score = max(0, min(100, score))

    if score >= 85:
        verdict, detail = "🟢 สุขภาพดี",       "ดิสก์อยู่ในสภาพดี ไม่พบปัญหาร้ายแรง"
    elif score >= 60:
        verdict, detail = "🟡 ควรเฝ้าระวัง",   "พบบางปัญหา ควรแบ็คอัพข้อมูลสำคัญและติดตามอาการ"
    elif score >= 30:
        verdict, detail = "🔴 เสี่ยงสูง",       "ควรแบ็คอัพข้อมูลด่วนและเตรียมเปลี่ยนดิสก์"
    else:
        verdict, detail = "💀 วิกฤต",           "ดิสก์ใกล้พัง! แบ็คอัพทันทีก่อนที่จะสาย"

    return rows, {
        "score": score, "verdict": verdict, "verdict_detail": detail,
        "risks": risks, "warnings": warnings,
    }, raw


# ═══════════════════════════════════════════════════════════════
# PDF EXPORT
# ═══════════════════════════════════════════════════════════════

def _clean_for_pdf(text: str) -> str:
    """
    Strip emoji/symbols that ReportLab built-in fonts cannot render.
    Preserves ASCII, Thai (U+0E00–U+0E7F), and Latin Extended.
    Known emoji are replaced with readable [TAG] equivalents.
    """
    _MAP = {
        "💾":"[DISK]","🔢":"[SN]","⚡":"[FW]","📍":"[LOC]","🛡":"[SMART]",
        "❤":"[HEALTH]","🌡":"[TEMP]","✍":"[WRITE]","🔄":"[CYCLE]","⚠":"[WARN]",
        "💥":"[ERR]","📋":"[LOG]","⏰":"[HOURS]","💔":"[BAD]","⏳":"[PEND]",
        "🚨":"[CRIT]","🔍":"[SEEK]","🌀":"[SPIN]","❌":"[FAIL]","✅":"[OK]",
        "🟢":"[GREEN]","🟡":"[WARN]","🔴":"[RED]","💀":"[DEAD]","🔥":"[HOT]",
    }
    out = []
    for ch in str(text):
        cp = ord(ch)
        if ch in _MAP:
            out.append(_MAP[ch])
        elif (0x0020 <= cp <= 0x007E or   # ASCII printable
              0x0E00 <= cp <= 0x0E7F or   # Thai
              0x00A0 <= cp <= 0x024F or   # Latin Extended
              ch in "\n\r\t"):
            out.append(ch)
        # silently drop other Unicode (emoji, variation selectors, ZWJ, etc.)
    return "".join(out).strip()


def _register_thai_font():
    """
    Register a Thai-capable TrueType font for ReportLab.
    Returns (font_name, font_name_bold).
    Falls back to Helvetica if no suitable font is found.
    """
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfbase.pdfmetrics import registerFontFamily

    candidates = [
        (r"C:\Windows\Fonts\THSarabunNew.ttf",
         r"C:\Windows\Fonts\THSarabunNew Bold.ttf", "THSarabun"),
        (r"C:\Windows\Fonts\tahoma.ttf",
         r"C:\Windows\Fonts\tahomabd.ttf",          "Tahoma"),
        (r"C:\Windows\Fonts\arial.ttf",
         r"C:\Windows\Fonts\arialbd.ttf",            "Arial"),
        (r"C:\Windows\Fonts\segoeui.ttf",
         r"C:\Windows\Fonts\segoeuib.ttf",           "SegoeUI"),
        ("/System/Library/Fonts/Supplemental/Tahoma.ttf",
         "/System/Library/Fonts/Supplemental/Tahoma Bold.ttf", "Tahoma"),
    ]
    for reg, bold, name in candidates:
        if not os.path.isfile(reg):
            continue
        try:
            pdfmetrics.registerFont(TTFont(name, reg))
            bold_src = bold if os.path.isfile(bold) else reg
            pdfmetrics.registerFont(TTFont(f"{name}-Bold", bold_src))
            registerFontFamily(name, normal=name, bold=f"{name}-Bold",
                               italic=name, boldItalic=f"{name}-Bold")
            return name, f"{name}-Bold"
        except Exception:
            continue
    return "Helvetica", "Helvetica-Bold"


def generate_pdf(rows: list, summary: dict, raw_json: str,
                 disk_display: str, out_path: str) -> tuple:
    """
    Build a print-friendly PDF report with:
      Page 1: Health summary + alerts + SMART attributes table
      Page 2: Raw JSON output from smartctl

    Returns (True, out_path) on success, (False, error_message) on failure.
    """
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            HRFlowable, PageBreak, Paragraph,
            SimpleDocTemplate, Spacer, Table, TableStyle,
        )
    except ImportError:
        return False, "กรุณาติดตั้ง reportlab:  pip install reportlab"

    FONT, FONT_B = _register_thai_font()
    FONT_MONO    = "Courier"

    # ── Colour palette (print-friendly light theme) ──────────
    C_BLUE   = colors.HexColor("#0066cc")
    C_GREEN  = colors.HexColor("#16a34a")
    C_RED    = colors.HexColor("#dc2626")
    C_AMBER  = colors.HexColor("#d97706")
    C_DARK   = colors.HexColor("#111827")
    C_GRAY   = colors.HexColor("#4b5563")
    C_LGRAY  = colors.HexColor("#d1d5db")
    C_ROW1   = colors.white
    C_ROW2   = colors.HexColor("#f9fafb")
    C_HEAD   = colors.HexColor("#e5e7eb")

    # ── Paragraph styles ─────────────────────────────────────
    def _ps(name, font=FONT, size=10, color=C_DARK, **kw):
        return ParagraphStyle(name, fontName=font, fontSize=size, textColor=color,
                              leading=size * 1.4, **kw)

    s_title  = _ps("title",  font=FONT_B, size=18, color=C_BLUE,  spaceAfter=4)
    s_sub    = _ps("sub",    size=9,  color=C_GRAY, spaceAfter=8)
    s_head   = _ps("head",   font=FONT_B, size=13, color=C_DARK, spaceAfter=4, spaceBefore=10)
    s_alert_r= _ps("alr",   size=10, color=C_RED,  spaceAfter=3)
    s_alert_a= _ps("ala",   size=10, color=C_AMBER, spaceAfter=3)
    s_mono   = _ps("mono",  font=FONT_MONO, size=7, color=C_GRAY, spaceAfter=1)

    doc   = SimpleDocTemplate(out_path, pagesize=A4,
                               leftMargin=20*mm, rightMargin=20*mm,
                               topMargin=20*mm, bottomMargin=20*mm)
    story = []
    now   = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    score = summary.get("score", 0)
    score_color = C_GREEN if score >= 85 else C_AMBER if score >= 60 else C_RED

    # ── Header ───────────────────────────────────────────────
    story += [
        Paragraph(f"{APP_NAME} — Disk Health Report", s_title),
        Paragraph(f"Generated: {now}   |   Disk: {_clean_for_pdf(disk_display)}", s_sub),
        HRFlowable(width="100%", thickness=1, color=C_BLUE, spaceAfter=10),
    ]

    # ── Summary table ────────────────────────────────────────
    story.append(Paragraph("HEALTH SUMMARY", s_head))
    verdict = _clean_for_pdf(summary.get("verdict", ""))
    detail  = _clean_for_pdf(summary.get("verdict_detail", ""))
    s_tbl = Table(
        [["Health Score", f"{score} / 100"], ["Verdict", verdict], ["Detail", detail]],
        colWidths=[50*mm, 120*mm],
    )
    s_tbl.setStyle(TableStyle([
        ("ROWBACKGROUNDS",  (0, 0), (-1, -1), [C_ROW1, C_ROW2]),
        ("TEXTCOLOR",       (0, 0), (0, -1),  C_GRAY),
        ("FONTNAME",        (0, 0), (0, -1),  FONT_B),
        ("TEXTCOLOR",       (1, 0), (1, 0),   score_color),
        ("FONTNAME",        (1, 0), (1, 0),   FONT_B),
        ("FONTSIZE",        (1, 0), (1, 0),   14),
        ("TEXTCOLOR",       (1, 1), (1, -1),  C_DARK),
        ("FONTNAME",        (0, 1), (-1, -1), FONT),
        ("FONTSIZE",        (0, 1), (-1, -1), 10),
        ("GRID",            (0, 0), (-1, -1), 0.5, C_LGRAY),
        ("TOPPADDING",      (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING",   (0, 0), (-1, -1), 6),
        ("LEFTPADDING",     (0, 0), (-1, -1), 8),
    ]))
    story += [s_tbl, Spacer(1, 8)]

    # ── Alerts ───────────────────────────────────────────────
    all_alerts = summary.get("risks", []) + summary.get("warnings", [])
    if all_alerts:
        story.append(Paragraph("ALERTS", s_head))
        for a in all_alerts:
            is_err = a.startswith("❌") or a.startswith("🔥")
            story.append(Paragraph(f"• {_clean_for_pdf(a)}", s_alert_r if is_err else s_alert_a))
        story.append(Spacer(1, 8))

    # ── SMART attributes table ────────────────────────────────
    story += [
        HRFlowable(width="100%", thickness=0.5, color=C_LGRAY, spaceAfter=8),
        Paragraph("SMART ATTRIBUTES", s_head),
    ]
    tdata = [["Attribute", "Value", "Status"]] + [
        [_clean_for_pdf(r[0]), str(r[1]), _clean_for_pdf(r[2])] for r in rows
    ]
    attr_tbl = Table(tdata, colWidths=[75*mm, 55*mm, 40*mm], repeatRows=1)
    attr_tbl.setStyle(TableStyle([
        ("BACKGROUND",      (0, 0), (-1, 0),  C_HEAD),
        ("TEXTCOLOR",       (0, 0), (-1, 0),  C_BLUE),
        ("FONTNAME",        (0, 0), (-1, 0),  FONT_B),
        ("FONTSIZE",        (0, 0), (-1, 0),  10),
        ("ROWBACKGROUNDS",  (0, 1), (-1, -1), [C_ROW1, C_ROW2]),
        ("TEXTCOLOR",       (0, 1), (0, -1),  C_GRAY),
        ("FONTNAME",        (0, 1), (0, -1),  FONT_B),
        ("TEXTCOLOR",       (1, 1), (1, -1),  C_DARK),
        ("FONTNAME",        (1, 1), (1, -1),  FONT_B),
        ("TEXTCOLOR",       (2, 1), (2, -1),  C_GRAY),
        ("FONTNAME",        (0, 1), (-1, -1), FONT),
        ("FONTSIZE",        (0, 1), (-1, -1), 9),
        ("GRID",            (0, 0), (-1, -1), 0.4, C_LGRAY),
        ("TOPPADDING",      (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING",   (0, 0), (-1, -1), 5),
        ("LEFTPADDING",     (0, 0), (-1, -1), 6),
    ]))
    story.append(attr_tbl)

    # ── Raw JSON (page 2) ─────────────────────────────────────
    story += [
        PageBreak(),
        Paragraph("RAW SMART DATA (JSON)", s_head),
        HRFlowable(width="100%", thickness=0.5, color=C_LGRAY, spaceAfter=6),
    ]
    try:
        raw_pretty = json.dumps(json.loads(raw_json), indent=2, ensure_ascii=False)
    except Exception:
        raw_pretty = raw_json or "(no data)"
    for line in raw_pretty.splitlines():
        safe = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        story.append(Paragraph(safe, s_mono))

    try:
        doc.build(story)
        return True, out_path
    except Exception as e:
        return False, str(e)


# ═══════════════════════════════════════════════════════════════
# OS FILE / PRINT HELPERS
# ═══════════════════════════════════════════════════════════════

def open_file(path: str):
    """Open a file with the OS default application."""
    try:
        if IS_WINDOWS:
            os.startfile(path)
        elif IS_MAC:
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception:
        pass


def print_pdf(path: str):
    """Send a PDF to the default printer."""
    try:
        if IS_WINDOWS:
            os.startfile(path, "print")
        else:
            subprocess.Popen(["lpr", path])
    except Exception:
        open_file(path)   # fallback: open instead of print


# ═══════════════════════════════════════════════════════════════
# UI — main()
# ═══════════════════════════════════════════════════════════════

def main(page: ft.Page):
    os_label = {"Windows": "🪟 Windows", "Darwin": "🍎 macOS", "Linux": "🐧 Linux"}.get(_OS, _OS)

    page.title      = f"{APP_NAME} v{APP_VERSION}"
    page.theme_mode = ft.ThemeMode.DARK
    page.padding    = 0
    page.bgcolor    = "#0a0e1a"
    try:
        page.window_width  = 1050
        page.window_height = 950
    except Exception:
        pass
    try:
        icon = os.path.join(
            sys._MEIPASS if hasattr(sys, "_MEIPASS") else os.path.abspath("."),
            "assets", "ssd.ico" if IS_WINDOWS else "ssd.png",
        )
        if os.path.isfile(icon):
            page.window_icon = icon
    except Exception:
        pass

    # ── Palette ──────────────────────────────────────────────
    CARD    = "#111827"
    BORDER  = "#1e2d45"
    ACCENT  = "#00d4ff"
    ACCENT2 = "#7c3aed"
    TEXT    = "#e2e8f0"
    MUTED   = "#64748b"

    # ── State (mutable dict so nested functions can write) ───
    state = {
        "devices": [],
        "cache":   {"rows": [], "summary": {}, "raw": "", "disk": ""},
    }

    # ── Header bar ───────────────────────────────────────────
    header = ft.Container(
        content=ft.Row([
            ft.Column([
                ft.Row([
                    ft.Container(ft.Text("⬡", size=28, color=ACCENT), margin=_margin(r=8)),
                    ft.Text(APP_NAME,           size=26, weight="bold",  color=ACCENT, font_family="Consolas"),
                    ft.Text(f" v{APP_VERSION}", size=20,                  color=TEXT,   font_family="Consolas"),
                ]),
                ft.Text(f"Disk Health Analyzer — {os_label}", size=11, color=MUTED, font_family="Consolas"),
            ], expand=True),
            ft.Container(
                ft.Text("● LIVE", size=10, color=ft.Colors.GREEN_400, font_family="Consolas"),
                bgcolor="#0d1f0d", border=_border_all(1, ft.Colors.GREEN_800),
                border_radius=4, padding=_pad(8, 4, 8, 4),
            ),
        ]),
        padding=_pad(24, 14, 24, 14), bgcolor=CARD, border=_border_bottom(1, BORDER),
    )

    # ── Score card ───────────────────────────────────────────
    score_num   = ft.Text("--", size=48, weight="bold", color=ACCENT, font_family="Consolas")
    score_bar   = ft.ProgressBar(value=0, color=ACCENT, bgcolor=BORDER, height=6, width=160)
    verdict_lbl = ft.Text("รอการสแกน", size=14, weight="bold", color=MUTED)
    detail_lbl  = ft.Text("เลือก disk แล้วกด SCAN", size=11, color=MUTED, text_align="center")

    score_card = ft.Container(
        ft.Column([
            ft.Text("HEALTH SCORE", size=9, color=MUTED, font_family="Consolas"),
            score_num, score_bar,
            ft.Text("/ 100", size=10, color=MUTED),
            ft.Divider(height=1, color=BORDER),
            verdict_lbl, detail_lbl,
        ], horizontal_alignment="center", spacing=4),
        padding=16, bgcolor=CARD,
        border=_border_all(1, BORDER), border_radius=10,
        width=200, alignment=_align_center(),
    )

    # ── Alert panel ──────────────────────────────────────────
    alert_col  = ft.Column([], spacing=5, scroll="auto", expand=True)
    alert_panel = ft.Container(
        ft.Column([
            ft.Text("⚠  ALERTS", size=11, color=MUTED, font_family="Consolas"),
            ft.Divider(height=1, color=BORDER),
            alert_col,
        ], spacing=6, expand=True),
        padding=14, bgcolor=CARD,
        border=_border_all(1, BORDER), border_radius=10,
        expand=True, height=200,
    )

    # ── Data table ───────────────────────────────────────────
    data_table = ft.DataTable(
        columns=[
            ft.DataColumn(ft.Text("ข้อมูล",      size=13, color=MUTED, font_family="Consolas")),
            ft.DataColumn(ft.Text("ค่าที่วัดได้", size=13, color=MUTED, font_family="Consolas")),
            ft.DataColumn(ft.Text("สถานะ",       size=13, color=MUTED, font_family="Consolas")),
        ],
        rows=[], column_spacing=30,
    )
    table_wrap = ft.Container(
        ft.Column([data_table], scroll="auto"),
        padding=4, bgcolor=CARD,
        border=_border_all(1, BORDER), border_radius=10, expand=True,
    )

    # ── Controls ─────────────────────────────────────────────
    dd = ft.Dropdown(label="เลือก Disk", options=[], expand=True)

    progress    = ft.ProgressBar(visible=False, color=ACCENT, bgcolor=BORDER)
    status_lbl  = ft.Text("พร้อมใช้งาน", size=11, color=MUTED, font_family="Consolas")

    scan_btn    = ft.ElevatedButton("⚡  FULL SCAN",  bgcolor=ACCENT2, color="white")
    refresh_btn = ft.IconButton(
        icon=ft.Icons.REFRESH if hasattr(ft.Icons, "REFRESH") else "refresh",
        tooltip="รีเฟรชรายการ Disk",
    )
    pdf_btn   = ft.ElevatedButton("💾  Save PDF", bgcolor="#1e3a5f", color="white", visible=False)
    print_btn = ft.ElevatedButton("🖨️  Print",    bgcolor="#1a3320", color="white", visible=False)

    # ── Helpers ──────────────────────────────────────────────

    def _make_option(d: dict):
        try:
            return ft.dropdown.Option(key=d["real"], text=d["display"])
        except Exception:
            return ft.DropdownOption(key=d["real"], text=d["display"])

    def _show_alert(text: str, is_error: bool):
        bg = ft.Colors.RED if is_error else ft.Colors.ORANGE_400
        return ft.Container(
            ft.Text(text, size=12, color="white" if is_error else TEXT, no_wrap=False),
            bgcolor=ft.Colors.with_opacity(0.15, bg),
            border=_border_all(1, ft.Colors.with_opacity(0.3, bg)),
            border_radius=6, padding=_pad(8, 6, 8, 6), expand=True,
        )

    # ── Logic ────────────────────────────────────────────────

    def refresh_disks():
        try:
            status_lbl.value    = "กำลังสแกนหา disk..."
            refresh_btn.disabled = True
            page.update()
        except Exception:
            pass

        found = get_disk_list()

        try:
            if found and found[0].get("_error"):
                state["devices"] = []
                dd.options, dd.value = [], None
                hint = (
                    "brew install smartmontools" if IS_MAC else
                    "sudo apt install smartmontools" if IS_LINUX else
                    "วาง smartctl.exe ในโฟลเดอร์เดียวกัน"
                )
                status_lbl.value = f"❌ ไม่พบ smartctl — {hint}"
                status_lbl.color = ft.Colors.RED_400
                # Show dialog
                def _close(e):
                    try: dlg.open = False; page.update()
                    except Exception: pass
                dlg = ft.AlertDialog(
                    title=ft.Text("ไม่พบ smartctl", color=ft.Colors.RED_400),
                    content=ft.Column([
                        ft.Text("โปรแกรมต้องการ smartmontools", size=13),
                        ft.Divider(),
                        ft.Text("ติดตั้งด้วย:", weight="bold", size=12),
                        ft.Text(f"  {hint}", font_family="Consolas", size=12, color=ft.Colors.CYAN_200),
                        ft.Text("จากนั้น restart app", size=11, color=ft.Colors.ORANGE_400),
                    ], tight=True, spacing=6),
                    actions=[ft.TextButton("ตกลง", on_click=_close)],
                )
                try: page.dialog = dlg; dlg.open = True
                except Exception: pass
            else:
                state["devices"] = found
                dd.options = [_make_option(d) for d in found]
                dd.value   = None
                status_lbl.value = (
                    f"พบ {len(found)} disk — เลือก disk แล้วกด SCAN"
                    if found else f"ไม่พบ disk"
                )
                status_lbl.color = MUTED

            refresh_btn.disabled = False
            page.update()
        except Exception:
            pass

    def do_scan(e):
        if not dd.value:
            status_lbl.value = "กรุณาเลือก disk ก่อน"
            page.update()
            return

        # Reset UI
        data_table.rows.clear()
        alert_col.controls.clear()
        score_num.value   = "--"
        verdict_lbl.value = "กำลังสแกน.. รอก่อนนะ"
        detail_lbl.value  = ""
        score_bar.value   = 0
        progress.visible  = True
        scan_btn.disabled = True
        pdf_btn.visible   = False
        print_btn.visible = False
        status_lbl.value  = "กำลังอ่านข้อมูล SMART... รออีกนิด จะได้รู้ผลแล้ว"
        page.update()

        def _run():
            dev = next((d for d in state["devices"] if d["real"] == dd.value), None)
            if not dev:
                return

            rows, summary, raw = get_smart_data(dev["real"], dev["label"], dev.get("dtype"))

            # Update table
            for lbl, val, note, color in rows:
                data_table.rows.append(ft.DataRow(cells=[
                    ft.DataCell(ft.Text(lbl,      size=13, color=TEXT,           font_family="Consolas")),
                    ft.DataCell(ft.Text(str(val), size=13, color=color or TEXT,  weight="bold", font_family="Consolas")),
                    ft.DataCell(ft.Text(note,     size=12, color=color or MUTED, font_family="Consolas")),
                ]))

            # Update score card
            sc = summary.get("score", 0)
            sc_color = (
                ft.Colors.GREEN_400  if sc >= 85 else
                ft.Colors.ORANGE_400 if sc >= 60 else
                ft.Colors.RED_400
            )
            score_num.value   = str(sc)
            score_num.color   = sc_color
            score_bar.value   = sc / 100
            score_bar.color   = sc_color
            verdict_lbl.value = summary.get("verdict", "")
            detail_lbl.value  = summary.get("verdict_detail", "")

            # Update alerts
            alerts = summary.get("risks", []) + summary.get("warnings", [])
            if alerts:
                for a in alerts:
                    is_err = a.startswith("❌") or a.startswith("🔥")
                    alert_col.controls.append(_show_alert(a, is_err))
            else:
                alert_col.controls.append(ft.Container(
                    ft.Text("ไม่พบปัญหาใด ๆ", size=12, color=ft.Colors.GREEN_400),
                    bgcolor=ft.Colors.with_opacity(0.1, ft.Colors.GREEN_400),
                    border=_border_all(1, ft.Colors.with_opacity(0.3, ft.Colors.GREEN_400)),
                    border_radius=6, padding=_pad(8, 6, 8, 6), expand=True,
                ))

            # Cache for PDF/Print
            state["cache"] = {"rows": rows, "summary": summary, "raw": raw, "disk": dev["display"]}

            progress.visible  = False
            scan_btn.disabled = False
            pdf_btn.visible   = True
            print_btn.visible = True
            status_lbl.value  = f"สแกนเสร็จแล้ว — {dev['display']}"
            page.update()

        threading.Thread(target=_run, daemon=True).start()

    def do_save_pdf(e):
        c = state["cache"]
        if not c["rows"]:
            return

        # Pick save path via native dialog
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk(); root.withdraw(); root.attributes("-topmost", True)
            ts   = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            path = filedialog.asksaveasfilename(
                parent=root, title="บันทึก PDF รายงาน",
                defaultextension=".pdf",
                filetypes=[("PDF", "*.pdf"), ("All files", "*.*")],
                initialfile=f"BlackCat_SMART_{ts}.pdf",
            )
            root.destroy()
        except Exception:
            ts   = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            path = os.path.join(os.path.expanduser("~"), "Desktop", f"BlackCat_SMART_{ts}.pdf")

        if not path:
            return

        status_lbl.value  = "กำลังสร้าง PDF..."
        pdf_btn.disabled  = True
        page.update()

        def _build():
            ok, result = generate_pdf(c["rows"], c["summary"], c["raw"], c["disk"], path)
            status_lbl.value = f"บันทึกแล้ว: {os.path.basename(result)}" if ok else f"PDF Error: {result}"
            pdf_btn.disabled = False
            page.update()
            if ok:
                open_file(result)

        threading.Thread(target=_build, daemon=True).start()

    def do_print(e):
        c = state["cache"]
        if not c["rows"]:
            return

        status_lbl.value   = "กำลังเตรียมพิมพ์..."
        print_btn.disabled = True
        page.update()

        def _build():
            tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False, prefix="bcprint_")
            tmp.close()
            ok, result = generate_pdf(c["rows"], c["summary"], c["raw"], c["disk"], tmp.name)
            if ok:
                print_pdf(tmp.name)
                status_lbl.value = "ส่งไปยัง Printer แล้ว"
            else:
                status_lbl.value = f"Print Error: {result}"
            print_btn.disabled = False
            page.update()

        threading.Thread(target=_build, daemon=True).start()

    # ── Wire events ──────────────────────────────────────────
    scan_btn.on_click    = do_scan
    refresh_btn.on_click = lambda _: threading.Thread(target=refresh_disks, daemon=True).start()
    pdf_btn.on_click     = do_save_pdf
    print_btn.on_click   = do_print

    # ── Layout ───────────────────────────────────────────────
    page.add(
        header,
        ft.Container(
            ft.Column([
                ft.Row([dd, refresh_btn, scan_btn, pdf_btn, print_btn], spacing=10),
                progress,
                status_lbl,
                ft.Row([score_card, alert_panel], spacing=12, vertical_alignment="start"),
                ft.Text("SMART ATTRIBUTES", size=11, color=MUTED, font_family="Consolas"),
                ft.Column([table_wrap], expand=True, height=400),
            ], spacing=10, expand=True),
            padding=_pad(20, 20, 20, 20), expand=True,
        ),
    )

    threading.Thread(target=refresh_disks, daemon=True).start()


# ═══════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    if hasattr(ft, "run"):
        ft.run(main, assets_dir="assets")
    else:
        ft.app(target=main, assets_dir="assets")