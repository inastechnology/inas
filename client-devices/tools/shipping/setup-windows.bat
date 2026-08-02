@echo off
setlocal
cd /d "%~dp0"

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup-windows.ps1"
if errorlevel 1 (
  echo.
  echo Setup failed. Review the messages above.
  pause
  exit /b 1
)

echo.
echo Setup completed.
pause
