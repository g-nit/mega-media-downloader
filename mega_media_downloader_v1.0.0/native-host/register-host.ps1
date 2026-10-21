
param(
    [Parameter(Mandatory = $true)]
    [string]$ExtensionId
)

$ErrorActionPreference = "Stop"

# Validate the Chrome extension ID
if ($ExtensionId -notmatch '^[a-p]{32}$') {
    throw "Invalid Chrome extension ID. Copy the 32-character ID from chrome://extensions."
}

# Find the prebuilt EXE in the extracted ZIP
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$sourceExe = Join-Path $here "dist\MegaMediaNativeHost.exe"

if (-not (Test-Path -LiteralPath $sourceExe)) {
    throw "Cannot find dist\MegaMediaNativeHost.exe. Keep the dist folder beside this script."
}

# Permanent installation directory for this Windows user
$installDir = Join-Path $env:LOCALAPPDATA "MegaMediaDownloader"
$exePath = Join-Path $installDir "MegaMediaNativeHost.exe"
$manifestPath = Join-Path $installDir "com.megamediadownloader.host.json"

# Create the folder and copy the EXE
New-Item -ItemType Directory -Path $installDir -Force | Out-Null
Copy-Item -LiteralPath $sourceExe -Destination $exePath -Force

# Create Chrome Native Messaging manifest
$manifest = @{
    name = "com.megamediadownloader.host"
    description = "MEGA Media Downloader native host"
    path = $exePath
    type = "stdio"
    allowed_origins = @("chrome-extension://$ExtensionId/")
} | ConvertTo-Json -Depth 5

Set-Content -LiteralPath $manifestPath -Value $manifest -Encoding UTF8

# Register the native host for the current Windows user
$key = "HKCU:\Software\Google\Chrome\NativeMessagingHosts\com.megamediadownloader.host"
New-Item -Path $key -Force | Out-Null
Set-Item -Path $key -Value $manifestPath

Write-Host ""
Write-Host "MEGA Media Downloader native host registered successfully!" -ForegroundColor Green
Write-Host "Installed EXE: $exePath"
Write-Host "Manifest: $manifestPath"
Write-Host ""
Write-Host "Reload your extension at chrome://extensions."
