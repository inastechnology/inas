@echo off
setlocal

if "%~1"=="" (
  echo Usage: flash-windows.bat COM44
  exit /b 2
)

python -m esptool --chip esp32s3 --port "%~1" --baud 460800 write-flash 0x0 rs485-debug-device-esp32s3.bin
if errorlevel 1 exit /b %errorlevel%

echo.
echo Flash completed. Reconnect the board and open the USB Debug COM at 115200 bps.
