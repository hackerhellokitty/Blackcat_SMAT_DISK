@echo off
chcp 65001 >nul
title BlackCat Disk Scanner — Build EXE

echo.
echo  ██████╗ ██╗      █████╗  ██████╗██╗  ██╗ ██████╗ █████╗ ████████╗
echo  ██╔══██╗██║     ██╔══██╗██╔════╝██║ ██╔╝██╔════╝██╔══██╗╚══██╔══╝
echo  ██████╔╝██║     ███████║██║     █████╔╝ ██║     ███████║   ██║
echo  ██╔══██╗██║     ██╔══██║██║     ██╔═██╗ ██║     ██╔══██║   ██║
echo  ██████╔╝███████╗██║  ██║╚██████╗██║  ██╗╚██████╗██║  ██║   ██║
echo  ╚═════╝ ╚══════╝╚═╝  ╚═╝ ╚═════╝╚═╝  ╚═╝ ╚═════╝╚═╝  ╚═╝   ╚═╝
echo.
echo  BlackCat Disk Scanner v1.0.0 — EXE Builder
echo  =========================================
echo.

set EXE_NAME=blackcat_Disk_Scanner
set PY_FILE=disk_scan.py
set DIST_EXE=dist\%EXE_NAME%.exe

echo [0/5] ปิด EXE เก่าที่อาจค้างอยู่...
taskkill /f /im "%EXE_NAME%.exe" >nul 2>&1
timeout /t 2 /nobreak >nul

if exist "%DIST_EXE%" (
    del /f /q "%DIST_EXE%" >nul 2>&1
    if exist "%DIST_EXE%" (
        echo  [ERROR] ลบ EXE เก่าไม่ได้
        pause
        exit /b 1
    )
    echo   OK  ลบ EXE เก่าแล้ว
) else (
    echo   OK  ไม่มี EXE เก่า
)

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
if not exist "%PY_FILE%" (
    echo  [ERROR] ไม่พบ %PY_FILE%!
    pause
    exit /b 1
)
echo   OK  %PY_FILE%
if not exist "assets" mkdir assets
echo   OK  assets\

set ICON_ARG=
if exist "assets\ssd.ico" (
    set ICON_ARG=--icon "assets\ssd.ico"
    echo   OK  assets\ssd.ico
) else (
    echo   --  assets\ssd.ico ไม่พบ (ข้าม)
)

echo.
echo [4/5] กำลัง build EXE...
echo  (อาจใช้เวลา 1-3 นาที กรุณารอ)
echo.

flet pack %PY_FILE% ^
    --name "%EXE_NAME%" ^
    --add-data "assets;assets" ^
    %ICON_ARG% ^
    --product-name "BlackCat Disk Scanner" ^
    --file-description "HDD/SSD Sector Scanner" ^
    --product-version "1.0.0.0" ^
    --file-version "1.0.0.0" ^
    --company-name "Kuroneko Tools"

if errorlevel 1 (
    echo.
    echo  [!] flet pack ไม่สำเร็จ — ลอง PyInstaller โดยตรง...
    pyinstaller ^
        --onefile --windowed ^
        --name "%EXE_NAME%" ^
        --add-data "assets;assets" ^
        %ICON_ARG% ^
        --uac-admin ^
        --hidden-import flet --hidden-import flet.fastapi --collect-all flet ^
        --noconfirm ^
        %PY_FILE%
)

echo.
echo [5/5] ตรวจสอบผลลัพธ์...
echo.
if exist "%DIST_EXE%" (
    echo  =========================================
    echo   BUILD สำเร็จ!  ไฟล์: %DIST_EXE%
    echo  =========================================
    explorer dist
) else (
    echo  [ERROR] Build ล้มเหลว — ดู error ด้านบน
)
echo.
pause
