@echo off
setlocal
cd /d "%~dp0"

if not exist ".shipping-setup.json" (
  echo [INAS Shipping Tool] Initial setup is required.
  call setup-windows.bat
  if errorlevel 1 exit /b 1
)

start "" ".venv\Scripts\pythonw.exe" run.py
