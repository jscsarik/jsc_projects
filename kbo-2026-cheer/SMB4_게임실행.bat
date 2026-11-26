@echo off
chcp 65001 > nul
setlocal enabledelayedexpansion
title SMB4 + KBO 응원가 플레이어 동시 실행기
cd /d "%~dp0"

echo ============================================================
echo   ⚾ SMB4 게임 + KBO 애슐리 퀸즈 응원가 통합 실행기
echo   Developer : 정승찬 (jscsarik)
echo   GitHub    : https://github.com/jscsarik/jsc_projects
echo ============================================================
echo.

:: 1. 응원가 플레이어 실행 (실행하기.bat 호출로 의존성 점검 및 실행)
call "%~dp0실행하기.bat"

:: 2. Steam을 통해 Super Mega Baseball 4 실행
echo [스팀 연동] Super Mega Baseball 4를 실행합니다...
start "" "steam://rungameid/1487210"

exit /b 0
