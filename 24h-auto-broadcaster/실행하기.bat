@echo off
chcp 65001 > nul
setlocal enabledelayedexpansion
title 24h-auto-broadcaster (DIMA 24시간 무인 자동 방송 송출) - 실행기
cd /d "%~dp0"

echo ============================================================
echo   📡 24h-auto-broadcaster - OBS 24시간 무인 자동 송출 관제
echo   Developer : 정승찬 (jscsarik)
echo   GitHub    : https://github.com/jscsarik/jsc_projects
echo ============================================================
echo.

:: 1. Python 환경 검사
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [오류] Python이 시스템에 설치되어 있지 않습니다!
    echo https://www.python.org/ 에서 Python을 설치(PATH 체크 필수)한 후 다시 실행해 주세요.
    echo.
    pause
    exit /b 1
)

:: 2. 필수 라이브러리 검사 및 자동 설치
python -c "import obsws_python, cv2" >nul 2>&1
if %errorlevel% neq 0 (
    echo [최초 실행 감지] 필수 라이브러리(obsws-python, opencv-python)를 설치합니다...
    echo (최초 1회만 진행되며, 잠시만 기다려 주세요.)
    python -m pip install -r requirements.txt
    if %errorlevel% neq 0 (
        echo [경고] 라이브러리 설치 실패. 인터넷 연결을 확인해 주세요.
        pause
        exit /b 1
    )
    echo [성공] 필수 라이브러리 설치가 완료되었습니다.
    echo.
)

:: 3. 송출 관제 시스템 시작
echo [실행 중] 24시간 무인 자동 송출 APC 시스템을 시작합니다...
echo (종료하려면 이 콘솔 창을 닫거나 Ctrl+C를 누르세요.)
echo.
python "%~dp0apc_main.py"
pause
