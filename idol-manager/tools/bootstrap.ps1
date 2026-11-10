param([switch] $CheckOnly)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$venvPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
$environmentChecker = Join-Path $PSScriptRoot 'check_environment.py'

function Test-PythonVersion([string] $Executable) {
    try {
        & $Executable $environmentChecker python-version 2>$null
        return $LASTEXITCODE -eq 0
    } catch { return $false }
}

if (-not (Test-Path -LiteralPath $venvPython)) {
    $candidates = [System.Collections.Generic.List[string]]::new()
    foreach ($version in @('3.14', '3.13', '3.12')) {
        try {
            $located = & py "-$version" $environmentChecker executable 2>$null
            if ($LASTEXITCODE -eq 0 -and $located) { $candidates.Add([string]$located) }
        } catch {}
    }
    foreach ($commandName in @('python', 'python3')) {
        $command = Get-Command $commandName -ErrorAction SilentlyContinue
        if ($command) { $candidates.Add($command.Source) }
    }
    foreach ($base in @("$env:LOCALAPPDATA\Programs\Python", "$env:ProgramFiles\Python")) {
        if (Test-Path -LiteralPath $base) {
            Get-ChildItem -LiteralPath $base -Directory | Sort-Object Name -Descending | ForEach-Object {
                $candidate = Join-Path $_.FullName 'python.exe'
                if (Test-Path -LiteralPath $candidate) { $candidates.Add($candidate) }
            }
        }
    }
    $selectedPython = $null
    foreach ($candidate in $candidates) {
        if (Test-PythonVersion $candidate) { $selectedPython = $candidate; break }
    }
    if (-not $selectedPython) {
        throw 'Python 3.12 or newer was not found. Install Python from https://www.python.org/downloads/windows/ and try again.'
    }
    & $selectedPython -m venv (Join-Path $projectRoot '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Failed to create the virtual environment.' }
}
if (-not (Test-PythonVersion $venvPython)) { throw 'The .venv environment requires Python 3.12 or newer.' }
& $venvPython $environmentChecker dependencies
if ($LASTEXITCODE -ne 0) {
    & $venvPython -m pip install -r (Join-Path $projectRoot 'requirements.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed. Check your internet connection.' }
}
if ($CheckOnly) {
    Write-Output 'IDOL Manager environment check: OK'
    exit 0
}
$venvPythonW = Join-Path $projectRoot '.venv\Scripts\pythonw.exe'
if (-not (Test-Path -LiteralPath $venvPythonW)) { throw 'pythonw.exe was not found in the virtual environment.' }
$gameArguments = '"' + (Join-Path $projectRoot 'main.py') + '"'
$gameProcess = Start-Process -FilePath $venvPythonW -ArgumentList $gameArguments -WorkingDirectory $projectRoot -WindowStyle Hidden -Wait -PassThru
if ($gameProcess.ExitCode -ne 0) { throw 'IDOL Manager exited with an error. Check the user logs folder.' }
