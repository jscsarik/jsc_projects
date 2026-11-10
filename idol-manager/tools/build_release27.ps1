$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$env:PYINSTALLER_CONFIG_DIR = Join-Path $projectRoot 'build\pyinstaller-cache'
& (Join-Path $projectRoot '.venv\Scripts\python.exe') -m PyInstaller --noconfirm (Join-Path $projectRoot 'IDOL_Manager.spec')
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& (Join-Path $projectRoot '.venv\Scripts\python.exe') (Join-Path $PSScriptRoot 'package_friend_release.py') --build-dir (Join-Path $projectRoot 'dist\IDOL_Manager')
exit $LASTEXITCODE
