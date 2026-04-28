param(
    [string]$Channel = "8.0",
    [string]$InstallDir = ".dotnet"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$target = Join-Path $root $InstallDir
$script = Join-Path $env:TEMP "dotnet-install.ps1"

Invoke-WebRequest -Uri "https://dot.net/v1/dotnet-install.ps1" -OutFile $script
& powershell -NoProfile -ExecutionPolicy Bypass -File $script -Channel $Channel -InstallDir $target

Write-Host "Installed .NET SDK to $target"
Write-Host "Use: $target\dotnet.exe --info"
