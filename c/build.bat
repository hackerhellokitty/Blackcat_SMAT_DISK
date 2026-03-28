@echo off
:: BlackCat SMART — C/C++ + Dear ImGui build script (MSVC)
setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo.
echo  BlackCat SMART -- Build (Phase 2 GUI)
echo  =======================================

:: ── Locate MSVC cl.exe ──────────────────────────────────────────
set CL_EXE=
for /f "delims=" %%f in ('where cl 2^>nul') do (
    set CL_EXE=%%f
    goto :found_cl
)
for %%p in (
    "C:\Program Files\Microsoft Visual Studio\18\Insiders\VC\Tools\MSVC\14.50.35717\bin\Hostx64\x64\cl.exe"
    "C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\VC\Tools\MSVC\14.50.35717\bin\Hostx64\x64\cl.exe"
) do if exist %%p set CL_EXE=%%~p

:found_cl
if not defined CL_EXE (
    echo  [ERROR] cl.exe not found.
    pause & exit /b 1
)
echo  Compiler : !CL_EXE!

:: ── MSVC / SDK paths ────────────────────────────────────────────
set VC_ROOT=C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\VC\Tools\MSVC\14.50.35717
if not exist "!VC_ROOT!\include" (
    set VC_ROOT=C:\Program Files\Microsoft Visual Studio\18\Insiders\VC\Tools\MSVC\14.50.35717
)
set SDK_ROOT=C:\Program Files (x86)\Windows Kits\10
set SDK_VER=
for /f "delims=" %%v in ('dir /b /ad "!SDK_ROOT!\Include" 2^>nul') do set SDK_VER=%%v
if not defined SDK_VER (
    echo  [ERROR] Windows SDK not found.
    pause & exit /b 1
)
echo  Windows SDK : !SDK_VER!

set INC=!VC_ROOT!\include
set INC_UM=!SDK_ROOT!\Include\!SDK_VER!\um
set INC_UCRT=!SDK_ROOT!\Include\!SDK_VER!\ucrt
set INC_SHARED=!SDK_ROOT!\Include\!SDK_VER!\shared
set LIB_VC=!VC_ROOT!\lib\x64
set LIB_UM=!SDK_ROOT!\Lib\!SDK_VER!\um\x64
set LIB_UCRT=!SDK_ROOT!\Lib\!SDK_VER!\ucrt\x64

set IMGUI=imgui
set BACKENDS=imgui\backends
set RC_EXE=!SDK_ROOT!\bin\!SDK_VER!\x64\rc.exe

echo.

:: ── Compile icon resource ─────────────────────────────────────────
"!RC_EXE!" /nologo /I"!INC_UM!" /I"!INC_SHARED!" /fo app.res app.rc
if errorlevel 1 (
    echo  [WARN] rc.exe failed — building without icon
    set APP_RES=
) else (
    set APP_RES=app.res
)

echo.

"!CL_EXE!" /nologo /W3 /wd4267 /wd4244 /O2 /D_CRT_SECURE_NO_WARNINGS /DUNICODE /D_UNICODE ^
    /I"include" ^
    /I"!INC!" ^
    /I"!INC_UM!" ^
    /I"!INC_UCRT!" ^
    /I"!INC_SHARED!" ^
    /I"!IMGUI!" ^
    /I"!BACKENDS!" ^
    src\main.c ^
    src\disk_enum.c ^
    src\smart_read.c ^
    src\report.c ^
    src\lang.c ^
    src\gui.cpp ^
    !IMGUI!\imgui.cpp ^
    !IMGUI!\imgui_draw.cpp ^
    !IMGUI!\imgui_tables.cpp ^
    !IMGUI!\imgui_widgets.cpp ^
    !BACKENDS!\imgui_impl_win32.cpp ^
    !BACKENDS!\imgui_impl_dx11.cpp ^
    pdfgen\pdfgen.c ^
    !APP_RES! ^
    /Fe:blackcat_smart.exe ^
    /link ^
    /SUBSYSTEM:WINDOWS ^
    /LIBPATH:"!LIB_VC!" ^
    /LIBPATH:"!LIB_UM!" ^
    /LIBPATH:"!LIB_UCRT!" ^
    setupapi.lib advapi32.lib ^
    d3d11.lib dxgi.lib d3dcompiler.lib shell32.lib comdlg32.lib

if %errorlevel% == 0 (
    echo.
    echo  [OK] blackcat_smart.exe  ^(GUI^)
) else (
    echo.
    echo  [FAIL] errorlevel=%errorlevel%
)

endlocal
pause
