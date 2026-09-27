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

REM ---- 2. not found: try winget silent install ----
echo Python 3.10-3.12 not found. Trying winget silent install (may take a few minutes)...
winget install -e --id Python.Python.3.12 --silent --accept-package-agreements --accept-source-agreements >nul 2>&1
for %%v in (3.12 3.11 3.10) do (
    py -%%v -c "import sys" >nul 2>&1 && (set "PYVER=%%v" & goto :found)
)

REM ---- 3. winget missing too: download Python installer from CN mirror, silent install ----
echo winget unavailable. Downloading Python 3.12 installer from CN mirror...
set "PYSETUP=%TEMP%\python-3.12.10-amd64.exe"
curl -L -o "%PYSETUP%" https://registry.npmmirror.com/-/binary/python/3.12.10/python-3.12.10-amd64.exe
if not exist "%PYSETUP%" (
    echo [ERROR] Download failed. Check network, or install Python manually:
    echo         https://www.python.org/downloads/  ^(check "Add python.exe to PATH"^)
    pause
    exit /b 1
)
echo Installing Python silently (per-user, no admin needed)...
"%PYSETUP%" /quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1 Include_test=0
del "%PYSETUP%" >nul 2>&1
REM refresh PATH for this session after per-user install
set "PATH=%LOCALAPPDATA%\Programs\Python\Python312\;%LOCALAPPDATA%\Programs\Python\Python312\Scripts\;%PATH%"
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
