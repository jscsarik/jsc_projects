$ErrorActionPreference = "Continue"
$log = "C:\Users\정승찬\.gemini\antigravity\scratch\install_log.txt"
Start-Transcript -Path $log -Force
$path = "C:\정승찬\google-AI-studio\VirtualMonitor"

if (-not (Test-Path $path)) {
    Write-Host "Error: Path $path does not exist." -ForegroundColor Red
    exit 1
}

Set-Location $path
Write-Host "Current Directory: $PWD"

Write-Host "1. Stopping..."
.\deviceinstaller64.exe stop usbmmidd

Write-Host "2. Removing..."
.\deviceinstaller64.exe remove usbmmidd

Write-Host "3. Installing..."
.\deviceinstaller64.exe install usbmmidd.inf usbmmidd

Write-Host "4. Enabling VDD..."
.\deviceinstaller64.exe enablevdd

Stop-Transcript
Write-Host "Done. Closing in 5 seconds..."
Start-Sleep -Seconds 5
