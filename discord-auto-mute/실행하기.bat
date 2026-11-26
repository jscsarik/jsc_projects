@echo off
chcp 65001 > nul
setlocal enabledelayedexpansion
title DiscordAutoMute (음성인식 디스코드 자동 제어) - 실행기
cd /d "%~dp0"

echo ============================================================
echo   🎙️ DiscordAutoMute - 음성 인식 디스코드 마이크 제어기
echo   Developer : 정승찬 (jscsarik)
echo   GitHub    : https://github.com/jscsarik/jsc_projects
echo ============================================================
echo.

:: 1. 기빌드된 단독 실행 파일(EXE)이 있으면 즉시 실행 (Python 불필요)
if exist "%~dp0dist\discord_mute.exe" (
    echo [EXE 감지] 독립 실행 파일(dist\discord_mute.exe)로 즉시 실행합니다.
    start "" "%~dp0dist\discord_mute.exe"
    exit /b 0
)

:: 2. Python 환경 검사
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [오류] Python이 설치되어 있지 않으며 pre-built EXE를 찾을 수 없습니다.
    echo Python 3.10 이상을 설치한 후 다시 실행해 주세요.
    echo.
    pause
    exit /b 1
)

:: 3. 의존성 자동 점검 및 설치
python -c "import speech_recognition, keyboard, pyaudio, psutil, win32gui" >nul 2>&1
if %errorlevel% neq 0 (
    echo [최초 실행 감지] 필수 음성인식 라이브러리를 설치합니다...
    echo (최초 1회만 진행되며, 잠시만 기다려 주세요.)
    pip install -r requirements.txt
    if %errorlevel% neq 0 (
        echo [경고] 라이브러리 설치 실패. 인터넷 연결 또는 파이썬 환경을 확인해 주세요.
        pause
        exit /b 1
    )
    echo [성공] 필수 라이브러리 설치가 완료되었습니다!
    echo.
)

:: 4. 백그라운드 실행
echo [실행 중] DiscordAutoMute를 백그라운드로 실행합니다...
where pythonw >nul 2>&1
if %errorlevel% eq 0 (
    start "" pythonw "%~dp0discord_mute.py"
) else (
    start "" python "%~dp0discord_mute.py"
)
exit /b 0
