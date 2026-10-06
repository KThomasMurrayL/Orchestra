#Requires -Version 5.1
$ErrorActionPreference = "Stop"

$Here = Split-Path -Parent $MyInvocation.MyCommand.Path

$PythonExe = $null
$PythonArgs = @()
if ($env:PYTHON) {
    $PythonExe = $env:PYTHON
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    $PythonExe = "py"
    $PythonArgs = @("-3")
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $PythonExe = "python"
}
if (-not $PythonExe) {
    Write-Error "Python 3.11+ was not found on PATH. Install it from https://python.org and retry."
    exit 1
}

Write-Host "==> creating virtualenv at $Here\.venv"
& $PythonExe @PythonArgs -m venv "$Here\.venv"
$VenvPython = Join-Path $Here ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    Write-Error "Failed to create the virtualenv at $Here\.venv"
    exit 1
}

& $VenvPython -m pip install --quiet --upgrade pip
Write-Host "==> installing orchestra (with voice support)"
Push-Location $Here
try {
    & $VenvPython -m pip install --quiet -e ".[voice]"
} finally {
    Pop-Location
}

$BinDir = Join-Path $env:USERPROFILE ".orchestra-bin"
New-Item -ItemType Directory -Force -Path $BinDir | Out-Null
$Shim = Join-Path $BinDir "orchestra.cmd"
$Exe = Join-Path $Here ".venv\Scripts\orchestra.exe"
"@echo off`r`n`"$Exe`" %*" | Set-Content -Encoding ASCII -Path $Shim
Write-Host "==> installed: $Shim"

$UserPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($UserPath -notlike "*$BinDir*") {
    [Environment]::SetEnvironmentVariable("Path", "$UserPath;$BinDir", "User")
    Write-Host "==> added $BinDir to your user PATH (restart your terminal to use 'orchestra')"
}

& $Exe --version
