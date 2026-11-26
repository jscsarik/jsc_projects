@echo off
chcp 65001 > nul
title IDOL Manager - 실행기
cd /d "%~dp0"

echo ============================================================
echo   👑 IDOL Manager - K-POP 아이돌 기획사 육성 경영 시뮬레이터
echo   Developer : 정승찬 (jscsarik)
echo   GitHub    : https://github.com/jscsarik/jsc_projects
echo ============================================================
echo.

start "" "%SystemRoot%\System32\wscript.exe" "%~dp0tools\launch.vbs"
exit /b 0
