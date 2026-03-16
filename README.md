# ⬡ BlackCat SMART v7.0
### Disk Health Analyzer · วิเคราะห์สุขภาพฮาร์ดดิสก์

> **READ-ONLY** — โปรแกรมอ่านข้อมูลเท่านั้น ไม่แก้ไข ไม่ลบ ไม่เขียนข้อมูลลงดิสก์  
> **READ-ONLY** — This application never writes to, modifies, or deletes any disk data.

---

## ภาษาไทย · Thai

### 🔍 คืออะไร

BlackCat SMART เป็นโปรแกรม GUI สำหรับตรวจสอบสุขภาพของ HDD, SATA SSD และ NVMe SSD โดยอ่านข้อมูล S.M.A.R.T. ผ่าน `smartctl` แล้วแสดงผลเป็น Health Score พร้อมคำแนะนำ และสามารถส่งออกรายงานเป็น PDF หรือพิมพ์ได้ทันที

### 💻 รองรับ

| ระบบปฏิบัติการ | สถานะ | หมายเหตุ |
|---|---|---|
| Windows 10/11 | ✅ Primary | ต้อง run as Administrator |
| macOS (Intel + Apple Silicon) | ✅ รองรับ | ต้องติดตั้ง smartmontools ผ่าน Homebrew |
| Linux | ✅ รองรับ | ต้องติดตั้ง smartmontools และรันด้วย sudo |

### 📦 ติดตั้ง Dependencies

```bash
# Python dependencies
pip install flet reportlab

# Windows: วาง smartctl.exe ในโฟลเดอร์เดียวกับ blackcat_SMART_DISK.py
# (ดาวน์โหลดจาก https://www.smartmontools.org)

# macOS:
brew install smartmontools

# Linux (Debian/Ubuntu):
sudo apt install smartmontools
```

### 🚀 วิธีรัน

```bash
# Windows (ต้องการ Admin — โปรแกรมขอ UAC อัตโนมัติ)
python blackcat_SMART_DISK.py

# macOS / Linux
python3 blackcat_SMART_DISK.py
```

### 🔨 Build เป็น .exe (Windows)

```bash
pip install pyinstaller
# วาง smartctl.exe ไว้ในโฟลเดอร์เดียวกันก่อน
build.bat
```

ไฟล์ output: `dist/blackcat_smart_DISK.exe`

### 🍎 Build เป็น .app และ .dmg (macOS)

```bash
chmod +x build_mac.sh
./build_mac.sh
```

ไฟล์ output: `dist/BlackCat_SMART.app` และ `BlackCat_SMART_v7.0.dmg`

### 📊 ข้อมูลที่แสดง

**NVMe SSD**
- สุขภาพดิสก์ (%) / Health percentage
- อุณหภูมิ / Temperature
- ข้อมูลที่เขียนสะสม (TBW) / Total bytes written
- Power Cycles
- Unsafe Shutdowns
- Media Errors
- Error Log entries

**HDD / SATA SSD**
- อุณหภูมิ / Temperature
- ชั่วโมงใช้งาน / Power-on hours
- Power Cycles
- Reallocated Sectors (Bad Sectors)
- Pending Sectors
- Uncorrectable Errors
- Seek Error Rate (HDD)
- Spin Retry Count (HDD)

### 🎯 Health Score

| คะแนน | สีแสดงผล | ความหมาย |
|---|---|---|
| 85–100 | 🟢 เขียว | สุขภาพดี |
| 60–84 | 🟡 เหลือง | ควรเฝ้าระวัง |
| 30–59 | 🔴 แดง | เสี่ยงสูง |
| 0–29 | 💀 แดงเข้ม | วิกฤต — แบ็คอัพด่วน |

### 📄 Export PDF / Print

หลังจาก scan เสร็จแล้ว จะมีปุ่ม **💾 Save PDF** และ **🖨️ Print** โผล่ขึ้นมา

PDF ประกอบด้วย 2 หน้า:
- **หน้า 1**: Health Score, คำวินิจฉัย, Alerts, ตารางข้อมูล SMART
- **หน้า 2**: Raw JSON จาก smartctl (ข้อมูลดิบทั้งหมด)

> ต้องติดตั้ง reportlab ก่อน: `pip install reportlab`

### 🔒 ความปลอดภัย

- ไม่มีการเชื่อมต่อ Network ทุกประเภท
- ไม่มีการแก้ไข Registry
- ไม่ใช้ `shell=True` ในทุก subprocess
- Input จาก user ไม่ถูกส่งตรงไปยัง command ใดๆ
- Disk index ผ่านการ validate ก่อนส่งไปยัง PowerShell เสมอ
- smartctl ใช้เฉพาะ `--scan` และ `-a` (read-only flags)

### 📁 โครงสร้างไฟล์

```
project/
├── blackcat_SMART_DISK.py   # source หลัก
├── smartctl.exe             # Windows: วางไว้ในโฟลเดอร์นี้
├── build.bat                # Windows build script
├── build_mac.sh             # macOS build script
├── assets/
│   ├── ssd.ico              # Windows icon
│   └── ssd.png              # macOS/Linux icon
└── README.md
```

---

## English

### 🔍 What is it?

BlackCat SMART is a cross-platform GUI application for monitoring disk health. It reads S.M.A.R.T. data via `smartctl`, calculates a Health Score, displays actionable alerts, and can export a full PDF report or send it directly to a printer.

### 💻 Platform Support

| OS | Status | Notes |
|---|---|---|
| Windows 10/11 | ✅ Primary | Requires Administrator (UAC prompt shown automatically) |
| macOS (Intel + Apple Silicon) | ✅ Supported | Requires smartmontools via Homebrew |
| Linux | ✅ Supported | Requires smartmontools; run with sudo |

### 📦 Install Dependencies

```bash
# Python packages
pip install flet reportlab

# Windows: place smartctl.exe in the same folder as blackcat_SMART_DISK.py
# Download from https://www.smartmontools.org

# macOS:
brew install smartmontools

# Linux (Debian/Ubuntu):
sudo apt install smartmontools
```

### 🚀 Running

```bash
# Windows (UAC elevation is requested automatically)
python blackcat_SMART_DISK.py

# macOS / Linux
python3 blackcat_SMART_DISK.py
```

### 🔨 Build — Windows .exe

```bash
pip install pyinstaller
# Place smartctl.exe in the same folder first
build.bat
```

Output: `dist/blackcat_smart_DISK.exe`

### 🍎 Build — macOS .app and .dmg

```bash
chmod +x build_mac.sh
./build_mac.sh
```

Output: `dist/BlackCat_SMART.app` and `BlackCat_SMART_v7.0.dmg`

### 📊 Monitored Attributes

**NVMe SSD**
- Health percentage (100 − percentage_used)
- Temperature
- Total bytes written (TBW)
- Power cycles
- Unsafe shutdowns
- Media errors
- Error log entries

**HDD / SATA SSD**
- Temperature
- Power-on hours (with years estimate)
- Power cycles
- Reallocated sectors (Bad Sectors)
- Pending sectors
- Offline uncorrectable errors
- Seek error rate (HDD)
- Spin retry count (HDD)

### 🎯 Health Score

| Score | Indicator | Meaning |
|---|---|---|
| 85–100 | 🟢 Green | Healthy |
| 60–84 | 🟡 Yellow | Monitor closely |
| 30–59 | 🔴 Red | High risk — back up data soon |
| 0–29 | 💀 Critical | Imminent failure — back up immediately |

Score is calculated by starting at 100 and subtracting points for each detected issue (SMART failure, bad sectors, high temperature, excessive hours, etc.).

### 📄 PDF Export and Print

After a scan completes, **💾 Save PDF** and **🖨️ Print** buttons appear.

The PDF contains two pages:
- **Page 1**: Health Score, verdict, alerts, and the full SMART attribute table
- **Page 2**: Raw JSON output from smartctl

Font support: automatically detects THSarabunNew → Tahoma → Arial → Segoe UI on Windows for Thai character support.

> Requires reportlab: `pip install reportlab`

### 🔒 Security

- No network access of any kind
- No registry access
- `shell=False` enforced on all subprocesses (prevents shell injection)
- User-supplied device names are never concatenated into shell strings
- Disk index is validated as integer in range 0–99 before being passed to PowerShell
- smartctl is invoked with read-only flags only (`--scan`, `-a`)
- macOS privilege escalation uses `osascript` with temp files (no terminal required)
- Temp files are always cleaned up in `finally` blocks

### 📁 Project Structure

```
project/
├── blackcat_SMART_DISK.py   # Main source
├── smartctl.exe             # Windows: place here
├── build.bat                # Windows build script
├── build_mac.sh             # macOS build script
├── assets/
│   ├── ssd.ico              # Windows icon
│   └── ssd.png              # macOS/Linux icon
└── README.md
```

### ⚙️ Configuration

Risk thresholds can be adjusted in the `RISK` dictionary near the top of the source file:

```python
RISK = {
    "temp_warn":    55,   # °C — warning threshold
    "temp_crit":    70,   # °C — critical threshold
    "health_warn":  80,   # NVMe % used — warning
    "health_crit":  90,   # NVMe % used — critical
    "hours_warn": 20000,  # Power-on hours — warning
    "hours_crit": 40000,  # Power-on hours — critical
    "pending_warn":  1,   # Pending sectors before warning
    "realloc_warn":  1,   # Reallocated sectors before warning
}
```

### 🛠️ Tech Stack

| Component | Library/Tool |
|---|---|
| GUI | [Flet](https://flet.dev) (Flutter-based Python UI) |
| SMART data | [smartmontools](https://www.smartmontools.org) (`smartctl`) |
| PDF export | [ReportLab](https://www.reportlab.com) |
| Packaging | [PyInstaller](https://pyinstaller.org) via `flet pack` |
| Disk info (Windows) | PowerShell `Get-Disk`, `Get-Partition`, `Get-Volume` |
| Disk info (macOS) | `diskutil info -plist` |
| Disk info (Linux) | `lsblk -J` |

---

*BlackCat SMART v7.0 — Internal use*
