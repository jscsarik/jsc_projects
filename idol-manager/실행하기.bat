@echo off
chcp 65001 > nul
setlocal enabledelayedexpansion
title IDOL Manager - K-POP 아이돌 기획사 육성 경영 시뮬레이션
cd /d "%~dp0"

echo ============================================================
echo   👑 IDOL Manager - K-POP 아이돌 기획사 육성 경영 시뮬레이션
echo   Developer : 정승찬 (jscsarik)
echo   GitHub    : https://github.com/jscsarik/jsc_projects
echo ============================================================
echo.

:: 1. 가상환경 및 Python 3.12+ 런타임 확인
echo [1/2] 게임 실행 환경 및 Python 3.12+ 검사 중...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\bootstrap.ps1" -CheckOnly >nul 2>&1
if %errorlevel% neq 0 (
    echo [최초 실행 감지] 게임 구동에 필요한 라이브러리(PySide6)를 설정합니다...
    echo (최초 1회만 약 1~2분 소요되며, 잠시만 기다려 주세요...)
    echo.
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\bootstrap.ps1"
    if %errorlevel% neq 0 (
        echo.
        echo [오류] IDOL Manager 환경 구성에 실패했습니다.
        echo Python 3.12 이상이 설치되어 있는지 확인해 주세요.
        echo 다운로드: https://www.python.org/downloads/
        echo (설치 시 'Add python.exe to PATH' 옵션을 반드시 체크해 주세요.)
        echo.
        pause
        exit /b 1
    )
)

:: 2. 게임 시작
echo [2/2] IDOL Manager를 시작합니다! 게임 화면이 곧 나타납니다...
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\bootstrap.ps1"
if %errorlevel% neq 0 (
    echo.
    echo [안내] 게임이 비정상 종료되었거나 오류가 발생했습니다.
    pause
    exit /b %errorlevel%
)
exit /b 0
