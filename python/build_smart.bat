@echo off
chcp 65001 >nul
title BlackCat SMART — Build EXE

echo.
echo  ██████╗ ██╗      █████╗  ██████╗██╗  ██╗ ██████╗ █████╗ ████████╗
echo  ██╔══██╗██║     ██╔══██╗██╔════╝██║ ██╔╝██╔════╝██╔══██╗╚══██╔══╝
echo  ██████╔╝██║     ███████║██║     █████╔╝ ██║     ███████║   ██║
echo  ██╔══██╗██║     ██╔══██║██║     ██╔═██╗ ██║     ██╔══██║   ██║
echo  ██████╔╝███████╗██║  ██║╚██████╗██║  ██╗╚██████╗██║  ██║   ██║
echo  ╚═════╝ ╚══════╝╚═╝  ╚═╝ ╚═════╝╚═╝  ╚═╝ ╚═════╝╚═╝  ╚═╝   ╚═╝
echo.
echo  BlackCat SMART Analyzer v1.0.0 — EXE Builder
echo  ========================================
echo.

echo [1/5] ตรวจสอบ flet...
python -c "import flet; print('  flet version:', flet.version.version)" 2>nul
if errorlevel 1 (
    echo  [!] ไม่พบ flet — กำลัง install...
    pip install flet
)

echo [2/5] ตรวจสอบ PyInstaller...
python -c "import PyInstaller; print('  PyInstaller:', PyInstaller.__version__)" 2>nul
if errorlevel 1 (
    echo  [!] ไม่พบ PyInstaller — กำลัง install...
    pip install pyinstaller
)

echo [3/5] ตรวจสอบไฟล์...
if not exist "smartctl.exe" (
    echo  [ERROR] ไม่พบ smartctl.exe!
    pause
    exit /b 1
)
echo   OK  smartctl.exe
if not exist "smart_viewer.py" (
    echo  [ERROR] ไม่พบ smart_viewer.py!
    pause
    exit /b 1
)
echo   OK  smart_viewer.py
if not exist "assets" mkdir assets
echo   OK  assets\

echo.
echo [4/5] กำลัง build EXE...
echo  (อาจใช้เวลา 1-3 นาที กรุณารอ)
echo.

flet pack smart_viewer.py ^
    --name "blackcat_smart_DISK" ^
    --add-data "smartctl.exe;." ^
    --add-data "assets;assets" ^
    --icon "assets\ssd.ico" ^
    --product-name "BlackCat SMART Analyzer" ^
    --file-description "Disk Health Analyzer" ^
    --product-version "1.0.0.0" ^
    --file-version "1.0.0.0" ^
    --company-name "Kuroneko Tools"

if errorlevel 1 (
    echo.
    echo  [!] flet pack ไม่สำเร็จ — ลอง PyInstaller โดยตรง...
    pyinstaller ^
        --onefile --windowed ^
        --name "blackcat_smart_DISK" ^
        --add-data "smartctl.exe;." ^
        --add-data "assets;assets" ^
        --icon "assets\ssd.ico" ^
        --uac-admin ^
        --hidden-import flet --hidden-import flet.fastapi --collect-all flet ^
        smart_viewer.py
)

echo.
echo [5/5] ตรวจสอบผลลัพธ์...
echo.
if exist "dist\blackcat_smart_DISK.exe" (
    echo  ========================================
    echo   BUILD สำเร็จ!  ไฟล์: dist\blackcat_smart_DISK.exe
    echo  ========================================
    explorer dist
) else (
    echo  [ERROR] Build ล้มเหลว — ดู error ด้านบน
)
echo.
pause
