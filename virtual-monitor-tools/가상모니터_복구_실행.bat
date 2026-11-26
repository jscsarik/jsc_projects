@echo off
chcp 65001 > nul
title virtual-monitor-tools - 가상 모니터 복구 도구
cd /d "%~dp0"

echo ============================================================
echo   🖥️ virtual-monitor-tools - 가상 디스플레이 복구 실행기
echo   Developer : 정승찬 (jscsarik)
echo   GitHub    : https://github.com/jscsarik/jsc_projects
echo ============================================================
echo.

:: 관리자 권한 확인 및 요청
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [안내] 가상 디스플레이 드라이버 제어를 위해 관리자 권한으로 재실행합니다...
    powershell -Command "Start-Process cmd.exe -ArgumentList '/c `\"%~f0`\"' -Verb RunAs"
    exit /b
)

echo [1/2] 가상 모니터 상태를 진단하고 복구를 시작합니다...
python "%~dp0restore_monitor.py"
if %errorlevel% neq 0 (
    echo [대체 실행] PowerShell 복구 스크립트로 재시도합니다...
    powershell -ExecutionPolicy Bypass -File "%~dp0restore_monitor.ps1"
)

echo.
echo ============================================================
echo   작업이 완료되었습니다.
echo ============================================================
pause
