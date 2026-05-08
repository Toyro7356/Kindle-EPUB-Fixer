param(
    [string]$Configuration = "Release"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$localDotnet = Join-Path $root ".dotnet\dotnet.exe"
$dotnet = if (Test-Path $localDotnet) { $localDotnet } else { "dotnet" }
$dotnetCliHome = Join-Path $root "build\dotnet-cli-home"
$nugetPackages = Join-Path $root "build\nuget-packages"
$appData = Join-Path $root "build\appdata"
New-Item -ItemType Directory -Path $dotnetCliHome -Force | Out-Null
New-Item -ItemType Directory -Path $nugetPackages -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $appData "NuGet") -Force | Out-Null
$env:DOTNET_CLI_HOME = $dotnetCliHome
$env:DOTNET_SKIP_FIRST_TIME_EXPERIENCE = "1"
$env:DOTNET_NOLOGO = "1"
$env:NUGET_PACKAGES = $nugetPackages
$env:APPDATA = $appData
$nugetConfig = Join-Path $appData "NuGet\NuGet.Config"
if (-not (Test-Path $nugetConfig)) {
    @"
<?xml version="1.0" encoding="utf-8"?>
<configuration>
  <packageSources>
    <clear />
    <add key="nuget.org" value="https://api.nuget.org/v3/index.json" />
  </packageSources>
</configuration>
"@ | Set-Content -LiteralPath $nugetConfig -Encoding UTF8
}
if (Test-Path $localDotnet) {
    $env:DOTNET_ROOT = Split-Path -Parent $localDotnet
    $env:PATH = "$env:DOTNET_ROOT;$env:PATH"
}
$version = (& "$root\.venv\Scripts\python.exe" -c "from src import __version__; print(__version__)").Trim()

$sdkList = & $dotnet --list-sdks 2>$null
if (-not $sdkList) {
    throw "No .NET SDK found. Run: powershell -ExecutionPolicy Bypass -File tools\install_dotnet_sdk.ps1"
}

& "$root\.venv\Scripts\python.exe" "$root\build_backend.py"
if ($LASTEXITCODE -ne 0) {
    throw "Backend build failed with exit code $LASTEXITCODE"
}

$project = Join-Path $root "native\KindleEpubFixer.WinUI\KindleEpubFixer.WinUI.csproj"
& $dotnet publish $project -c $Configuration -r win-x64 --self-contained true
if ($LASTEXITCODE -ne 0) {
    throw "WinUI publish failed with exit code $LASTEXITCODE"
}

$buildRoot = Join-Path $root "native\KindleEpubFixer.WinUI\bin\$Configuration\net10.0-windows10.0.26100.0\win-x64"
$publishRoot = Join-Path $buildRoot "publish"
if (-not (Test-Path $publishRoot)) {
    $publishRoot = Get-ChildItem (Join-Path $root "native\KindleEpubFixer.WinUI\bin") -Directory -Recurse |
        Where-Object { $_.FullName -like "*\win-x64\publish" } |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1 -ExpandProperty FullName
    $buildRoot = Split-Path $publishRoot -Parent
}

$payloadRoot = Join-Path $root "dist\InstallerPayload"
Remove-Item -LiteralPath $payloadRoot -Recurse -Force -ErrorAction SilentlyContinue
$legacySingleExe = Join-Path $root "dist\Kindle EPUB Fixer.exe"
Remove-Item -LiteralPath $legacySingleExe -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $payloadRoot -Force | Out-Null

Copy-Item (Join-Path $publishRoot "*") $payloadRoot -Recurse -Force
foreach ($resourceName in @("App.xbf", "MainWindow.xbf", "KindleEpubFixer.WinUI.pri")) {
    $resourcePath = Join-Path $buildRoot $resourceName
    if (Test-Path $resourcePath) {
        Copy-Item -LiteralPath $resourcePath -Destination $payloadRoot -Force
    }
}
$compiledViews = Join-Path $buildRoot "Views"
if (Test-Path $compiledViews) {
    Copy-Item -LiteralPath $compiledViews -Destination (Join-Path $payloadRoot "Views") -Recurse -Force
}
Copy-Item (Join-Path $root "dist\KindleEpubFixer.Backend.exe") $payloadRoot -Force
Copy-Item (Join-Path $root "fonts") (Join-Path $payloadRoot "fonts") -Recurse -Force
Copy-Item (Join-Path $root "native\KindleEpubFixer.WinUI\Assets") (Join-Path $payloadRoot "Assets") -Recurse -Force
foreach ($logName in @("home-crash.log", "winui-crash.log", "launcher-error.log")) {
    Remove-Item -LiteralPath (Join-Path $payloadRoot $logName) -ErrorAction SilentlyContinue
}

$csc = Join-Path $env:WINDIR "Microsoft.NET\Framework64\v4.0.30319\csc.exe"
if (-not (Test-Path $csc)) {
    throw "Cannot find .NET Framework C# compiler for installer: $csc"
}

$launcherIcon = Join-Path $root "native\KindleEpubFixer.WinUI\Assets\app.ico"
$payloadZip = Join-Path $root "dist\KindleEpubFixer.Payload.zip"
Remove-Item -LiteralPath $payloadZip -ErrorAction SilentlyContinue
Compress-Archive -Path (Join-Path $payloadRoot "*") -DestinationPath $payloadZip -CompressionLevel Optimal

$installerSource = Join-Path $root "tools\Installer.cs"
$installerManifest = Join-Path $root "tools\Installer.manifest"
$installerExe = Join-Path $root "dist\KindleEpubFixer.Setup.exe"
$versionedInstallerExe = Join-Path $root "dist\KindleEpubFixer-$version-Setup.exe"
Remove-Item -LiteralPath $installerExe -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $versionedInstallerExe -ErrorAction SilentlyContinue
& $csc /nologo /target:winexe /reference:System.Windows.Forms.dll /reference:System.Drawing.dll /reference:System.IO.Compression.dll /reference:System.IO.Compression.FileSystem.dll /win32icon:$launcherIcon /win32manifest:$installerManifest /resource:$payloadZip,KindleEpubFixer.Payload.zip /out:$installerExe $installerSource
if ($LASTEXITCODE -ne 0) {
    throw "Installer build failed with exit code $LASTEXITCODE"
}
Copy-Item -LiteralPath $installerExe -Destination $versionedInstallerExe -Force
Remove-Item -LiteralPath $payloadZip -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $payloadRoot -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath (Join-Path $root "dist\KindleEpubFixer.Backend.exe") -ErrorAction SilentlyContinue

Write-Host "Native WinUI build finished:"
Write-Host $publishRoot
Write-Host "Installer package:"
Write-Host $installerExe
Write-Host $versionedInstallerExe
