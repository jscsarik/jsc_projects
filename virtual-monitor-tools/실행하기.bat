@echo off
chcp 65001 > nul
setlocal enabledelayedexpansion
title virtual-monitor-tools - 가상 모니터 드라이버 진단 및 복구
cd /d "%~dp0"

echo ============================================================
echo   🖥️ virtual-monitor-tools - 가상 디스플레이 진단 & 복구
echo   Developer : 정승찬 (jscsarik)
echo   GitHub    : https://github.com/jscsarik/jsc_projects
echo ============================================================
echo.
echo   [1] 🛠️ 가상 모니터 원클릭 복구 실행 (권장)
echo   [2] 🔍 현재 디스플레이 모니터 상태 진단
echo   [0] 🚪 나가기
echo ============================================================
set /p CHOICE="원하시는 작업 번호를 입력하세요 (1/2/0): "

if "%CHOICE%"=="1" (
    call "%~dp0가상모니터_복구_실행.bat"
    exit /b 0
)
if "%CHOICE%"=="2" (
    call "%~dp0가상모니터_상태_진단.bat"
    exit /b 0
)
if "%CHOICE%"=="0" (
    exit /b 0
)

echo 잘못 입력하셨습니다.
pause
