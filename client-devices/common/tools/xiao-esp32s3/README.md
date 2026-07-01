# Seeed XIAO ESP32S3 Flash Tools

Windows PowerShell flashing tools for client devices that use the Seeed XIAO
ESP32S3 board and the shared OTA-capable flash layout.

These scripts are not universal across all device boards. If another device uses
a different MCU, bootloader flow, partition offsets, flash size, or OTA layout,
create a separate tool directory for that board.

## File

- `flash.ps1`: writes prebuilt XIAO ESP32S3 images. The default mode writes
  `firmware.bin` to OTA app slots only and preserves LittleFS. Use
  `-Mode WithBoot` to also write bootloader, partition table, and `boot_app0.bin`
  without writing LittleFS. Use `-Mode Merged` to write `flash_merged.bin` at
  offset `0x0`, which overwrites LittleFS and saved Wi-Fi/MQTT settings.

Examples:

```powershell
.\flash.ps1 -InstallEsptool
.\flash.ps1 -Mode WithBoot -InstallEsptool
.\flash.ps1 -Mode Merged -InstallEsptool
.\flash.ps1 -Help
```

## COM Port Selection

If `-Port COMx` is omitted, each script auto-selects the only detected COM port.
When multiple COM ports are present, it prints a list and asks the user to choose
one.
