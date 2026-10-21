$key = "HKCU:\Software\Google\Chrome\NativeMessagingHosts\com.megamediadownloader.host"
if (Test-Path $key) { Remove-Item $key -Force; Write-Host "Native host registration removed." } else { Write-Host "Native host was not registered." }
