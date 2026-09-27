@echo off
title Laya Chat Advisor Installer
cd /d %~dp0

echo ============================================
echo   Laya Chat Advisor - One-Click Installer
echo   Python / deps / models - all automatic
echo ============================================
echo.

REM ---- 1. look for an existing Python 3.10-3.12 ----
set "PYVER="
for %%v in (3.12 3.11 3.10) do (
    py -%%v -c "import sys" >nul 2>&1 && (set "PYVER=%%v" & goto :found)
)

REM ---- 2. not found: download from CN mirror (fast in China), silent install ----
echo Python 3.10-3.12 not found. Downloading from CN mirror (~25MB)...
set "PYSETUP=%TEMP%\python-3.12.10-amd64.exe"
curl -L -# -o "%PYSETUP%" https://registry.npmmirror.com/-/binary/python/3.12.10/python-3.12.10-amd64.exe
if not exist "%PYSETUP%" (
    echo [WARN] CN mirror download failed, falling back to winget...
    goto :winget
)
echo Download done. Installing silently (no windows will pop up, ~1 min)...
"%PYSETUP%" /quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1 Include_test=0
del "%PYSETUP%" >nul 2>&1
REM refresh PATH for this session after per-user install
set "PATH=%LOCALAPPDATA%\Programs\Python\Python312\;%LOCALAPPDATA%\Programs\Python\Python312\Scripts\;%PATH%"
for %%v in (3.12 3.11 3.10) do (
    py -%%v -c "import sys" >nul 2>&1 && (set "PYVER=%%v" & goto :found)
)

REM ---- 3. mirror path failed: winget as fallback ----
:winget
echo Trying winget (progress below, may take a few minutes)...
winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
for %%v in (3.12 3.11 3.10) do (
    py -%%v -c "import sys" >nul 2>&1 && (set "PYVER=%%v" & goto :found)
)

echo [ERROR] Python still not detected after install. Reboot and run this file again.
pause
exit /b 1

:found
echo Using Python %PYVER%.
py -%PYVER% install.py
pause
