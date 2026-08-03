<#
.SYNOPSIS
Flash prebuilt XIAO ESP32S3 images from Windows.

.DESCRIPTION
This script writes prebuilt images for client devices using the Seeed XIAO
ESP32S3 OTA-capable flash layout.

Modes:
- FirmwareOnly: writes firmware.bin to OTA app partition(s) only. This preserves
  LittleFS Wi-Fi/MQTT settings.
- WithBoot: writes bootloader.bin, partitions.bin, boot_app0.bin, and
  firmware.bin without writing LittleFS.
- Merged: writes firmware.factory.bin at offset 0x0. This overwrites LittleFS.

By default, FirmwareOnly writes firmware.bin to both OTA slots. This avoids
ambiguity after previous OTA updates, where the currently selected boot slot may
be app0 or app1. Use -Slot app0 or -Slot app1 only when you intentionally want
one slot.

.EXAMPLE
.\flash.ps1

.EXAMPLE
.\flash.ps1 -Port COM12 -InstallEsptool

.EXAMPLE
.\flash.ps1 -Mode WithBoot -ArtifactDir . -InstallEsptool

.EXAMPLE
.\flash.ps1 -Mode Merged -ImagePath .\firmware.factory.bin -InstallEsptool

.EXAMPLE
.\flash.ps1 -Help
#>

[CmdletBinding(SupportsShouldProcess = $true, PositionalBinding = $false)]
param(
    [Alias("h", "?")]
    [switch]$Help,
    [string]$Port,
    [string]$ImagePath,
    [string]$Mode = "FirmwareOnly",
    [string]$Slot = "both",
    [string]$ArtifactDir,
    [string]$BootloaderPath,
    [string]$PartitionsPath,
    [string]$BootApp0Path,
    [string]$Python,
    [string]$Esptool,
    [int]$Baud = 460800,
    [switch]$InstallEsptool,
    [switch]$NoReset,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$RemainingArgs
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Show-FlashHelp {
    Write-Host @"
Seeed XIAO ESP32S3 flash tool

Usage:
  powershell -ExecutionPolicy Bypass -File .\flash.ps1 [options]

Modes:
  FirmwareOnly  Write firmware.bin to OTA app slot(s). This is the default.
                LittleFS is not written, so saved Wi-Fi/MQTT settings remain.

  WithBoot      Write bootloader.bin, partitions.bin, boot_app0.bin, and
                firmware.bin. LittleFS is not written.

  Merged        Write firmware.factory.bin at offset 0x0. This overwrites LittleFS,
                including saved Wi-Fi/MQTT settings and runtime config.

Typical commands:
  .\flash.ps1 -InstallEsptool
  .\flash.ps1 -Mode WithBoot -InstallEsptool
  .\flash.ps1 -Mode Merged -InstallEsptool

Required files in the same folder:
  FirmwareOnly:
    firmware.bin
    flash.ps1

  WithBoot:
    bootloader.bin
    partitions.bin
    boot_app0.bin
    firmware.bin
    flash.ps1

  Merged:
    firmware.factory.bin
    flash.ps1

Options:
  -Mode <FirmwareOnly|WithBoot|Merged>
      Select write mode. Default: FirmwareOnly.

  -Port COMx
      Serial port. If omitted, the only detected COM port is used. If multiple
      ports are detected, this script asks you to select one.

  -Slot <both|app0|app1>
      FirmwareOnly/WithBoot target app slot. Default: both.
      app0 = 0x10000, app1 = 0x340000.

  -ImagePath <path>
      Explicit firmware.bin or firmware.factory.bin path.

  -ArtifactDir <path>
      Directory containing bootloader.bin, partitions.bin, boot_app0.bin, and
      firmware.bin for -Mode WithBoot.

  -BootloaderPath <path>
  -PartitionsPath <path>
  -BootApp0Path <path>
      Explicit paths for -Mode WithBoot.

  -InstallEsptool
      Install esptool with Python pip before flashing if needed.

  -Python <path>
      Explicit Python executable path.

  -Esptool <path>
      Explicit esptool executable path.

  -Baud <rate>
      Serial baud rate. Default: 460800.

  -NoReset
      Do not hard reset after flashing.

  -WhatIf
      Show what would be done without flashing.

  -Help
      Show this help and exit.
"@
}

function Stop-WithMessage {
    param(
        [Parameter(Mandatory = $true)][string]$Message,
        [int]$ExitCode = 1
    )

    Write-Host ""
    Write-Host "エラー: $Message" -ForegroundColor Red
    exit $ExitCode
}

if ($Help) {
    Show-FlashHelp
    exit 0
}

if ($null -ne $RemainingArgs -and $RemainingArgs.Count -gt 0) {
    Write-Host ("不明なオプションまたは引数です: {0}" -f ($RemainingArgs -join " ")) -ForegroundColor Red
    Write-Host ""
    Show-FlashHelp
    exit 1
}

$validModes = @("FirmwareOnly", "WithBoot", "Merged")
if ($validModes -notcontains $Mode) {
    Write-Host "Mode の指定が不正です: $Mode" -ForegroundColor Red
    Write-Host ""
    Show-FlashHelp
    exit 1
}

$validSlots = @("both", "app0", "app1")
if ($validSlots -notcontains $Slot) {
    Write-Host "Slot の指定が不正です: $Slot" -ForegroundColor Red
    Write-Host ""
    Show-FlashHelp
    exit 1
}

function Resolve-ExistingFile {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Description
    )

    if ([string]::IsNullOrWhiteSpace($Path) -or -not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        Stop-WithMessage "$Description が見つかりません: $Path"
    }

    $resolved = Resolve-Path -LiteralPath $Path -ErrorAction Stop
    return $resolved.ProviderPath
}

function Resolve-ExistingDirectory {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Description
    )

    if ([string]::IsNullOrWhiteSpace($Path) -or -not (Test-Path -LiteralPath $Path -PathType Container)) {
        Stop-WithMessage "$Description が見つかりません: $Path"
    }

    $resolved = Resolve-Path -LiteralPath $Path -ErrorAction Stop
    return $resolved.ProviderPath
}

function Get-DefaultImagePath {
    $imageName = "firmware.bin"
    if ($Mode -eq "Merged") {
        $imageName = "firmware.factory.bin"
    }

    $scriptImage = Join-Path $PSScriptRoot $imageName
    if (Test-Path -LiteralPath $scriptImage -PathType Leaf) {
        return $scriptImage
    }

    $workingImage = Join-Path (Get-Location) $imageName
    if (Test-Path -LiteralPath $workingImage -PathType Leaf) {
        return $workingImage
    }

    return $scriptImage
}

function Get-DefaultArtifactDirectory {
    $scriptBootloader = Join-Path $PSScriptRoot "bootloader.bin"
    $scriptPartitions = Join-Path $PSScriptRoot "partitions.bin"
    $scriptFirmware = Join-Path $PSScriptRoot "firmware.bin"
    if ((Test-Path -LiteralPath $scriptBootloader -PathType Leaf) -and
        (Test-Path -LiteralPath $scriptPartitions -PathType Leaf) -and
        (Test-Path -LiteralPath $scriptFirmware -PathType Leaf)) {
        return $PSScriptRoot
    }

    $workingDirectory = (Get-Location).Path
    $workingBootloader = Join-Path $workingDirectory "bootloader.bin"
    $workingPartitions = Join-Path $workingDirectory "partitions.bin"
    $workingFirmware = Join-Path $workingDirectory "firmware.bin"
    if ((Test-Path -LiteralPath $workingBootloader -PathType Leaf) -and
        (Test-Path -LiteralPath $workingPartitions -PathType Leaf) -and
        (Test-Path -LiteralPath $workingFirmware -PathType Leaf)) {
        return $workingDirectory
    }

    return $PSScriptRoot
}

function Resolve-ArtifactFile {
    param(
        [string]$ExplicitPath,
        [Parameter(Mandatory = $true)][string]$ArtifactDirectory,
        [Parameter(Mandatory = $true)][string]$FileName,
        [Parameter(Mandatory = $true)][string]$Description
    )

    if (-not [string]::IsNullOrWhiteSpace($ExplicitPath)) {
        return (Resolve-ExistingFile -Path $ExplicitPath -Description $Description)
    }

    return (Resolve-ExistingFile -Path (Join-Path $ArtifactDirectory $FileName) -Description $Description)
}

function Resolve-BootApp0File {
    param(
        [string]$ExplicitPath,
        [Parameter(Mandatory = $true)][string]$ArtifactDirectory
    )

    $candidates = @()
    if (-not [string]::IsNullOrWhiteSpace($ExplicitPath)) {
        $candidates += $ExplicitPath
    }
    $candidates += (Join-Path $ArtifactDirectory "boot_app0.bin")

    if (-not [string]::IsNullOrWhiteSpace($env:USERPROFILE)) {
        $candidates += (Join-Path $env:USERPROFILE ".platformio\packages\framework-arduinoespressif32\tools\partitions\boot_app0.bin")
    }

    foreach ($candidate in $candidates) {
        if (-not [string]::IsNullOrWhiteSpace($candidate) -and (Test-Path -LiteralPath $candidate -PathType Leaf)) {
            return (Resolve-ExistingFile -Path $candidate -Description "boot_app0.bin")
        }
    }

    Stop-WithMessage "boot_app0.bin が見つかりません。artifact directory にコピーするか、-BootApp0Path で指定してください。"
}

function Get-SerialPorts {
    $portsById = @{}

    try {
        $cimPorts = @(Get-CimInstance Win32_SerialPort | Where-Object { $_.DeviceID -match '^COM\d+$' })
        foreach ($item in $cimPorts) {
            $portsById[$item.DeviceID] = [pscustomobject]@{
                DeviceID = $item.DeviceID
                Name = $item.Name
            }
        }
    }
    catch {
    }

    try {
        $dotNetPorts = @([System.IO.Ports.SerialPort]::GetPortNames())
        foreach ($item in $dotNetPorts) {
            if (-not $portsById.ContainsKey($item)) {
                $portsById[$item] = [pscustomobject]@{
                    DeviceID = $item
                    Name = ""
                }
            }
        }
    }
    catch {
    }

    return @($portsById.Values | Sort-Object @{ Expression = {
        $match = [regex]::Match($_.DeviceID, '^COM(\d+)$')
        if ($match.Success) { [int]$match.Groups[1].Value } else { 9999 }
    }}, DeviceID)
}

function Select-SerialPort {
    $ports = @(Get-SerialPorts)

    if ($ports.Count -eq 0) {
        Stop-WithMessage "COM ポートが見つかりません。デバイスを接続するか、-Port COMx を指定してください。"
    }

    if ($ports.Count -eq 1) {
        return $ports[0].DeviceID
    }

    Write-Host "複数の COM ポートが見つかりました。書き込み対象を選択してください:" -ForegroundColor Yellow
    for ($i = 0; $i -lt $ports.Count; $i++) {
        $name = $ports[$i].Name
        if ([string]::IsNullOrWhiteSpace($name)) {
            $name = "(no description)"
        }
        Write-Host ("  [{0}] {1}  {2}" -f ($i + 1), $ports[$i].DeviceID, $name)
    }

    while ($true) {
        $answer = Read-Host ("Select port number [1-{0}]" -f $ports.Count)
        $selected = 0
        if ([int]::TryParse($answer, [ref]$selected) -and $selected -ge 1 -and $selected -le $ports.Count) {
            return $ports[$selected - 1].DeviceID
        }
        Write-Host "選択が不正です。" -ForegroundColor Yellow
    }
}

function Get-CommandPathOrNull {
    param([Parameter(Mandatory = $true)][string]$Name)

    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if ($null -eq $command) {
        return $null
    }
    return $command.Source
}

function Get-PythonCommand {
    if (-not [string]::IsNullOrWhiteSpace($Python)) {
        return @((Resolve-ExistingFile -Path $Python -Description "Python executable"))
    }

    $pyLauncher = Get-CommandPathOrNull -Name "py.exe"
    if ($null -ne $pyLauncher) {
        return @($pyLauncher, "-3")
    }

    $pythonExe = Get-CommandPathOrNull -Name "python.exe"
    if ($null -ne $pythonExe) {
        return @($pythonExe)
    }

    $python = Get-CommandPathOrNull -Name "python"
    if ($null -ne $python) {
        return @($python)
    }

    Stop-WithMessage "Python が見つかりません。Python をインストールするか、-Esptool で esptool.exe のパスを指定してください。"
}

function Show-ExternalFailureHelp {
    param(
        [Parameter(Mandatory = $true)][string]$FailureMessage,
        [Parameter(Mandatory = $true)][int]$ExitCode,
        [switch]$FlashOperation
    )

    Write-Host ""
    Write-Host ("エラー: {0} (終了コード: {1})" -f $FailureMessage, $ExitCode) -ForegroundColor Red

    if ($FlashOperation) {
        $portLabel = $Port
        if ([string]::IsNullOrWhiteSpace($portLabel)) {
            $portLabel = "対象の COM ポート"
        }

        Write-Host ""
        Write-Host "書き込みに失敗しました。COM ポートを開けない、または書き込み中に通信できない状態です。" -ForegroundColor Yellow
        Write-Host "確認してください:"
        Write-Host ("  - {0} をシリアルモニタ、Arduino IDE、PlatformIO、Tera Term などで開いたままにしていないか" -f $portLabel)
        Write-Host "  - デバイスを抜き差しした後、同じ COM ポート番号のまま認識されているか"
        Write-Host "  - 別のデバイスを選んでいないか。複数ある場合は -Port を省略して選択し直してください"
        Write-Host "  - USB ケーブルがデータ通信対応か、または別の USB ポートで改善するか"
        Write-Host "  - それでも接続できない場合は、BOOT ボタンを押しながら RESET してから再実行してください"
        Write-Host ""
        Write-Host "ログに 'アクセスが拒否されました' または 'PermissionError(13)' がある場合は、ほぼ COM ポートが別アプリに使用されています。" -ForegroundColor Yellow
    }
}

function Invoke-External {
    param(
        [Parameter(Mandatory = $true)][string[]]$Command,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [string]$FailureMessage = "コマンドの実行に失敗しました",
        [switch]$FlashOperation
    )

    $exe = $Command[0]
    $prefixArgs = @()
    if ($Command.Count -gt 1) {
        $prefixArgs = $Command[1..($Command.Count - 1)]
    }

    try {
        & $exe @prefixArgs @Arguments
        $exitCode = $LASTEXITCODE
    }
    catch {
        Write-Host ""
        Write-Host ("エラー: 外部コマンドを起動できません: {0}" -f $exe) -ForegroundColor Red
        Write-Host $_.Exception.Message
        exit 1
    }

    if ($exitCode -ne 0) {
        Show-ExternalFailureHelp -FailureMessage $FailureMessage -ExitCode $exitCode -FlashOperation:$FlashOperation
        exit $exitCode
    }
}

function Get-EsptoolCommand {
    if (-not [string]::IsNullOrWhiteSpace($Esptool)) {
        return @((Resolve-ExistingFile -Path $Esptool -Description "esptool executable"))
    }

    $esptoolExe = Get-CommandPathOrNull -Name "esptool.exe"
    if ($null -ne $esptoolExe) {
        return @($esptoolExe)
    }

    $pythonCommand = Get-PythonCommand

    if ($InstallEsptool) {
        Invoke-External -Command $pythonCommand -Arguments @("-m", "pip", "install", "--user", "esptool") -FailureMessage "esptool のインストールに失敗しました" | Out-Null
    }

    Invoke-External -Command $pythonCommand -Arguments @("-m", "esptool", "version") -FailureMessage "esptool が利用できません。-InstallEsptool を付けて再実行するか、-Esptool でパスを指定してください。" | Out-Null
    return @($pythonCommand + @("-m", "esptool"))
}

$artifactDirectory = $null
$bootloader = $null
$partitions = $null
$bootApp0 = $null
if ($Mode -eq "WithBoot") {
    $effectiveArtifactDir = $ArtifactDir
    if ([string]::IsNullOrWhiteSpace($effectiveArtifactDir)) {
        $effectiveArtifactDir = Get-DefaultArtifactDirectory
    }

    $artifactDirectory = Resolve-ExistingDirectory -Path $effectiveArtifactDir -Description "Artifact directory"
    $bootloader = Resolve-ArtifactFile -ExplicitPath $BootloaderPath -ArtifactDirectory $artifactDirectory -FileName "bootloader.bin" -Description "bootloader.bin"
    $partitions = Resolve-ArtifactFile -ExplicitPath $PartitionsPath -ArtifactDirectory $artifactDirectory -FileName "partitions.bin" -Description "partitions.bin"
    $bootApp0 = Resolve-BootApp0File -ExplicitPath $BootApp0Path -ArtifactDirectory $artifactDirectory
}

$effectiveImagePath = $ImagePath
if ([string]::IsNullOrWhiteSpace($effectiveImagePath)) {
    if ($Mode -eq "WithBoot") {
        $effectiveImagePath = Join-Path $artifactDirectory "firmware.bin"
    }
    else {
        $effectiveImagePath = Get-DefaultImagePath
    }
}

$imageDescription = "firmware.bin"
if ($Mode -eq "Merged") {
    $imageDescription = "firmware.factory.bin"
}
$image = Resolve-ExistingFile -Path $effectiveImagePath -Description $imageDescription

if ([string]::IsNullOrWhiteSpace($Port)) {
    $Port = Select-SerialPort
}

$afterMode = "hard-reset"
if ($NoReset) {
    $afterMode = "no-reset"
}

$esptoolCommand = Get-EsptoolCommand
$writeArgs = @(
    "--chip", "esp32s3",
    "--port", $Port,
    "--baud", [string]$Baud,
    "--before", "default-reset",
    "--after", $afterMode,
    "write-flash",
    "-z",
    "--flash-mode", "keep",
    "--flash-freq", "keep",
    "--flash-size", "keep"
)

if ($Mode -eq "WithBoot") {
    $writeArgs += @(
        "0x0", $bootloader,
        "0x8000", $partitions,
        "0xe000", $bootApp0
    )
}

if ($Mode -eq "Merged") {
    $writeArgs += @("0x0", $image)
}
else {
    if ($Slot -eq "app0" -or $Slot -eq "both") {
        $writeArgs += @("0x10000", $image)
    }
    if ($Slot -eq "app1" -or $Slot -eq "both") {
        $writeArgs += @("0x340000", $image)
    }
}

Write-Host "イメージ: $image"
Write-Host "ポート: $Port"
Write-Host "ボーレート: $Baud"
Write-Host "モード: $Mode"
if ($Mode -ne "Merged") {
    Write-Host "スロット: $Slot"
}
if ($Mode -eq "WithBoot") {
    Write-Host "成果物ディレクトリ: $artifactDirectory"
    Write-Host "ブートローダ: $bootloader"
    Write-Host "パーティション: $partitions"
    Write-Host "boot_app0: $bootApp0"
}
Write-Host ""
if ($Mode -eq "Merged") {
    Write-Host "firmware.factory.bin を 0x0 に書き込みます。" -ForegroundColor Yellow
    Write-Host "既存の LittleFS Wi-Fi/MQTT 設定と runtime config は上書きされます。" -ForegroundColor Yellow
}
elseif ($Mode -eq "WithBoot") {
    Write-Host "boot 情報と firmware.bin を書き込みます。LittleFS の Wi-Fi/MQTT 設定は保持します。" -ForegroundColor Green
    Write-Host "bootloader、partition table、OTA boot metadata も書き込みます。" -ForegroundColor Yellow
}
else {
    Write-Host "firmware.bin のみを書き込みます。LittleFS の Wi-Fi/MQTT 設定は保持します。" -ForegroundColor Green
}
if ($Mode -ne "Merged" -and $Slot -eq "both") {
    Write-Host "OTA app0/app1 の両方に同じ firmware.bin を書き込みます。" -ForegroundColor Yellow
}

$operation = "XIAO ESP32S3 に $Mode を書き込み"
if ($Mode -ne "Merged") {
    $operation += " (LittleFS は保持)"
}
if ($PSCmdlet.ShouldProcess($Port, $operation)) {
    Invoke-External -Command $esptoolCommand -Arguments $writeArgs -FailureMessage "書き込みに失敗しました" -FlashOperation
    Write-Host "書き込みが完了しました。" -ForegroundColor Green
}
