@echo off
title Laya Chat Advisor Installer
cd /d %~dp0

echo ============================================
echo   Laya Chat Advisor - One-Click Installer
echo   (Python env + deps + models, fully auto)
echo ============================================
echo.

REM ---- find a Python 3.10-3.12 launcher ----
set "PYEXE="
for %%v in (3.12 3.11 3.10) do (
    py -%%v -c "import sys" >nul 2>&1 && (set "PYVER=%%v" & goto :found)
)
echo Python 3.10-3.12 not found. Trying winget silent install...
winget install -e --id Python.Python.3.12 --silent --accept-package-agreements --accept-source-agreements
if errorlevel 1 (
    echo.
    echo [ERROR] Could not auto-install Python.
    echo Please install Python 3.12 from https://www.python.org/downloads/
    echo ^(check "Add python.exe to PATH"^), then run this file again.
    pause
    exit /b 1
)
set "PYVER=3.12"
:found
echo Using Python %PYVER%.
py -%PYVER% install.py
pause
