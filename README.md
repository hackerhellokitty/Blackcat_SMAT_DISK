# BlackCat SMART

เครื่องมือตรวจสุขภาพ HDD / SSD บน Windows — คุยกับ hardware ตรงๆ ผ่าน Win32 IOCTL

---

## ภาษา C (หลัก) — `c/`

เขียนใหม่ทั้งหมดในภาษา C / C++ ไม่พึ่ง Python หรือ smartctl.exe

### Features
- อ่าน ATA SMART attributes โดยตรงผ่าน `IOCTL_ATA_PASS_THROUGH`
- อ่าน NVMe Health Log ผ่าน `StorageDeviceProtocolSpecificProperty`
- แสดง drive letters ของแต่ละ physical disk
- คำนวณ Health Score 0–100 พร้อม verdict
- GUI dark theme — Dear ImGui + DirectX 11
- Export PDF report พร้อม save dialog
- รองรับ 2 ภาษา EN / TH (สลับได้ real-time)
- พกใส่ flash drive ได้ — single exe ไม่ต้องติดตั้ง

### Requirements
- Windows (Administrator required)
- MSVC (Visual Studio Build Tools)
- Dear ImGui (วางไว้ใน `c/imgui/`)

### Build

```bat
cd c
build.bat
```

ได้ `blackcat_smart.exe`

---

## ภาษา Python (ความทรงจำ) — `python/`

เวอร์ชันแรกที่ใช้ Python + Flet + smartctl.exe
เก็บไว้เป็น reference — ไม่ได้ maintain แล้ว

---

## License

Internal tool — BlackCat Project
