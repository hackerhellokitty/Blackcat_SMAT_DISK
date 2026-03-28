# BlackCat SMART DISK

เครื่องมือตรวจสุขภาพ HDD / SSD บน Windows พร้อม UI แบบ real-time

---

## เครื่องมือในชุดนี้

### 1. BlackCat Disk Scanner (`disk_scan.py`)
สแกน HDD/SSD ระดับ sector เพื่อตรวจหา bad sector

### 2. BlackCat SMART Analyzer (`smart_viewer.py`)
อ่านข้อมูล SMART ของ disk และแสดงผลสุขภาพ drive

---

## Requirements

- Windows (Administrator required)
- Python 3.10+
- Flet >= 0.80

```bash
pip install flet reportlab
```

> SMART Analyzer ต้องการ `smartctl.exe` (รวมอยู่ในโปรเจกต์แล้ว)

---

## Run

```bash
# Disk Scanner
python disk_scan.py

# SMART Analyzer
python smart_viewer.py
```

---

## Build EXE

```bat
# Disk Scanner
build_scanner.bat

# SMART Analyzer
build_smart.bat
```

---

## Changelog

### v1.0.0
- Initial release — รวม Disk Scanner + SMART Analyzer ใน repo เดียว
- Disk Scanner: sector-level read scan, bad sector detection, PDF report, EN/TH language
- SMART Analyzer: SMART data reader, disk health scoring, temperature monitoring

---

## License

Internal tool — BlackCat Project
