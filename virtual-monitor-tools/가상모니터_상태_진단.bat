@echo off
chcp 65001 > nul
title virtual-monitor-tools - 모니터 상태 진단
cd /d "%~dp0"

echo ============================================================
echo   🖥️ virtual-monitor-tools - 현재 디스플레이 모니터 진단
echo   Developer : 정승찬 (jscsarik)
echo   GitHub    : https://github.com/jscsarik/jsc_projects
echo ============================================================
echo.

python "%~dp0check_monitors.py"
echo.
pause
