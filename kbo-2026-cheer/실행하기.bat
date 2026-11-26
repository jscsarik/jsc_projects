@echo off
chcp 65001 > nul
setlocal enabledelayedexpansion
title KBO 2026 애슐리 퀸즈 응원가 & 프로필 전광판 - 실행기
cd /d "%~dp0"

echo ============================================================
echo   ⚾ KBO 2026 애슐리 퀸즈 - 응원가(40곡) & 선수단 전광판
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

:: 2. 의존성 자동 점검 및 설치
python -c "import customtkinter, pygame, keyboard, psutil, PIL, win32gui" >nul 2>&1
if %errorlevel% neq 0 (
    echo [최초 실행 감지] 필수 라이브러리(CustomTkinter, Pygame 등)를 설치합니다...
    echo (최초 1회만 진행되며, 잠시만 기다려 주세요.)
    pip install -r requirements.txt
    if %errorlevel% neq 0 (
        echo [경고] 라이브러리 설치 실패. 인터넷 연결을 확인해 주세요.
        pause
        exit /b 1
    )
    echo [성공] 필수 라이브러리 설치가 완료되었습니다!
    echo.
)

:: 3. 응원가 플레이어 실행
echo [실행 중] 애슐리 퀸즈 응원가 & 전광판 매니저를 시작합니다...
where pythonw >nul 2>&1
if %errorlevel% eq 0 (
    start "" pythonw "%~dp0main.py"
) else (
    start "" python "%~dp0main.py"
)
exit /b 0
