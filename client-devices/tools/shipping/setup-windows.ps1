[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

function Write-Step {
    param([Parameter(Mandatory = $true)][string]$Message)
    Write-Host ""
    Write-Host ("==> {0}" -f $Message) -ForegroundColor Cyan
}

function Resolve-Python {
    $launcher = Get-Command "py.exe" -ErrorAction SilentlyContinue
    if ($null -ne $launcher) {
        try {
            & $launcher.Source -3 -c "import sys; print(sys.executable)" | Out-Null
            if ($LASTEXITCODE -eq 0) {
                return @($launcher.Source, "-3")
            }
        }
        catch {
        }
    }

    foreach ($name in @("python.exe", "python")) {
        $command = Get-Command $name -ErrorAction SilentlyContinue
        if ($null -ne $command) {
            try {
                & $command.Source -c "import sys; print(sys.executable)" | Out-Null
                if ($LASTEXITCODE -eq 0) {
                    return @($command.Source)
                }
            }
            catch {
            }
        }
    }

    $localPrograms = Join-Path $env:LOCALAPPDATA "Programs\Python"
    if (Test-Path -LiteralPath $localPrograms) {
        $candidate = Get-ChildItem -LiteralPath $localPrograms -Filter python.exe -Recurse |
            Sort-Object FullName -Descending |
            Select-Object -First 1
        if ($null -ne $candidate) {
            return @($candidate.FullName)
        }
    }
    return $null
}

function Invoke-Python {
    param(
        [Parameter(Mandatory = $true)][string[]]$Command,
        [Parameter(Mandatory = $true)][string[]]$Arguments
    )
    $executable = $Command[0]
    $prefix = @()
    if ($Command.Count -gt 1) {
        $prefix = $Command[1..($Command.Count - 1)]
    }
    & $executable @prefix @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Python command failed with exit code $LASTEXITCODE"
    }
}

Write-Host "INAS Shipping Tool - initial setup" -ForegroundColor White
Write-Host "Python, GUI dependencies, esptool, PlatformIO and espressif32 will be prepared."

$pythonCommand = Resolve-Python
if ($null -eq $pythonCommand) {
    Write-Step "Installing Python 3.12"
    $winget = Get-Command "winget.exe" -ErrorAction SilentlyContinue
    if ($null -eq $winget) {
        throw "Python 3 and winget were not found. Install Python 3.11 or newer, then rerun setup-windows.bat."
    }
    & $winget.Source install --id Python.Python.3.12 --exact --scope user `
        --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) {
        throw "Python installation failed with exit code $LASTEXITCODE"
    }
    $pythonCommand = Resolve-Python
    if ($null -eq $pythonCommand) {
        throw "Python was installed but could not be located. Sign out and back in, then rerun setup-windows.bat."
    }
}

Write-Step "Creating the private Python environment"
if (-not (Test-Path -LiteralPath ".venv\Scripts\python.exe")) {
    Invoke-Python -Command $pythonCommand -Arguments @("-m", "venv", ".venv")
}
$venvPython = (Resolve-Path -LiteralPath ".venv\Scripts\python.exe").Path

Write-Step "Installing Python packages"
& $venvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) {
    throw "pip update failed"
}
& $venvPython -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) {
    throw "Package installation failed"
}

Write-Step "Installing PlatformIO espressif32 6.10.0"
& $venvPython -m platformio platform install "espressif32@6.10.0"
if ($LASTEXITCODE -ne 0) {
    throw "PlatformIO espressif32 installation failed"
}

Write-Step "Verifying the environment"
& $venvPython -c "import esptool, serial, tkinterdnd2; print('Python dependencies: OK')"
if ($LASTEXITCODE -ne 0) {
    throw "Python dependency verification failed"
}
& $venvPython -m platformio platform show espressif32
if ($LASTEXITCODE -ne 0) {
    throw "PlatformIO espressif32 verification failed"
}

$marker = @{
    completed_at = (Get-Date).ToString("o")
    python = $venvPython
    platformio = "6.1.18"
    espressif32 = "6.10.0"
} | ConvertTo-Json
Set-Content -LiteralPath ".shipping-setup.json" -Value $marker -Encoding UTF8

Write-Host ""
Write-Host "Environment setup completed successfully." -ForegroundColor Green
Write-Host "Run start-windows.bat to open INAS Shipping Tool."
