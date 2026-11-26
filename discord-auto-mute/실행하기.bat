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
echo   [음성 제어 명령어 안내]
echo   - "마이크 오프" 또는 "마이크 꺼줘" : 디스코드 음소거 토글 (Ctrl+PageDown)
echo   - "좀 있다 올게" 또는 "나갈게"     : 디스코드 통화 종료 (Ctrl+PageUp)
echo.
echo ============================================================
echo   [상태] 음성 감지 엔진이 실행 중입니다. (종료: 이 창을 닫으세요)
echo ============================================================
echo.

:: 1. 단독 실행 파일(EXE)이 있으면 파이썬 없이 즉시 실행
if exist "%~dp0dist\discord_mute.exe" (
    "%~dp0dist\discord_mute.exe"
    pause
    exit /b 0
)

:: 2. Python 환경 검사
where python >nul 2>&1
if %errorlevel% neq 0 (
    where py >nul 2>&1
    if !errorlevel! neq 0 (
        echo [오류] Python이 설치되어 있지 않습니다.
        pause
        exit /b 1
    )
    set PY_CMD=py
) else (
    set PY_CMD=python
)

:: 3. 의존성 점검
!PY_CMD! -m pip install -r requirements.txt >nul 2>&1

:: 4. 실행
!PY_CMD! "%~dp0discord_mute.py"
pause
exit /b 0
