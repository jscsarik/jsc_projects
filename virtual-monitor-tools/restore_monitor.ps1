$installerPath = "C:\정승찬\google-AI-studio\VirtualMonitor\deviceinstaller64.exe"

# Path verification (for log purposes)
if (-not (Test-Path $installerPath)) {
    Write-Host "Warning: deviceinstaller64.exe not found at '$installerPath'. Please check the path." -ForegroundColor Yellow
    # We try anyway in case it's a permission issue with Test-Path for the agent but works for the user
}

Write-Host "Attempting to enable virtual monitor (requires Admin privileges)..."
try {
    $proc = Start-Process -FilePath $installerPath -ArgumentList "enablevdd" -Verb RunAs -Wait -PassThru
    if ($proc.ExitCode -eq 0) {
        Write-Host "Virtual monitor enabled successfully!" -ForegroundColor Green
    }
    else {
        Write-Host "Process finished with exit code: $($proc.ExitCode)" -ForegroundColor Yellow
    }
}
catch {
    Write-Error "Failed to start process: $_"
}
