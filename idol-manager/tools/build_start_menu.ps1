$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$env:PYINSTALLER_CONFIG_DIR = Join-Path $projectRoot 'build\start-menu-cache'
# Drive Desktop can mark generated resource folders read-only for its icons.
# Normalize only this build's output; never touch source assets or user saves.
$releaseOutput = [System.IO.Path]::GetFullPath((Join-Path $projectRoot 'dist\release_start_menu\IDOL_Manager'))
$releaseBase = [System.IO.Path]::GetFullPath((Join-Path $projectRoot 'dist')) + [System.IO.Path]::DirectorySeparatorChar
if (-not $releaseOutput.StartsWith($releaseBase,[System.StringComparison]::OrdinalIgnoreCase)) { throw 'Invalid release output path' }
if (Test-Path -LiteralPath $releaseOutput) {
    $releaseItem = Get-Item -LiteralPath $releaseOutput -Force
    if ($releaseItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) { throw 'Release output must not be a link' }
    @($releaseItem) + @(Get-ChildItem -LiteralPath $releaseOutput -Recurse -Force) | ForEach-Object {
        if (-not ($_.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -and ($_.Attributes -band [System.IO.FileAttributes]::ReadOnly)) {
            $_.Attributes = $_.Attributes -band (-bnot [System.IO.FileAttributes]::ReadOnly)
        }
    }
}
& (Join-Path $projectRoot '.venv\Scripts\python.exe') (Join-Path $PSScriptRoot 'make_game_icon.py')
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& (Join-Path $projectRoot '.venv\Scripts\python.exe') -m PyInstaller --noconfirm --distpath (Join-Path $projectRoot 'dist\release_start_menu') --workpath (Join-Path $projectRoot 'build\start_menu') (Join-Path $projectRoot 'IDOL_Manager.spec')
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& (Join-Path $projectRoot '.venv\Scripts\python.exe') (Join-Path $PSScriptRoot 'package_friend_release.py') --build-dir (Join-Path $projectRoot 'dist\release_start_menu\IDOL_Manager')
exit $LASTEXITCODE
