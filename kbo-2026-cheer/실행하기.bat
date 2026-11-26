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

:: 1. 단독 실행 파일(EXE)이 있으면 파이썬 없이 즉시 실행!
if exist "%~dp0dist\kbo_cheer.exe" (
    echo [EXE 감지] 독립 실행 파일(kbo_cheer.exe)로 즉시 전광판을 엽니다...
    start "" "%~dp0dist\kbo_cheer.exe"
    timeout /t 2 >nul
    exit /b 0
)

:: 2. Python 환경 검사
where python >nul 2>&1
if %errorlevel% neq 0 (
    where py >nul 2>&1
    if !errorlevel! neq 0 (
        echo [오류] Python이 시스템에 설치되어 있지 않으며 dist\kbo_cheer.exe를 찾을 수 없습니다!
        echo https://www.python.org/ 에서 Python을 설치해 주세요.
        pause
        exit /b 1
    )
    set PY_CMD=py
) else (
    set PY_CMD=python
)

:: 3. 의존성 자동 점검 및 설치
echo [라이브러리 점검] 필요한 모듈을 확인합니다...
!PY_CMD! -m pip install -r requirements.txt >nul 2>&1

:: 4. 응원가 플레이어 실행
echo [실행 중] 애슐리 퀸즈 응원가 & 전광판 매니저를 시작합니다...
!PY_CMD! "%~dp0main.py"
if %errorlevel% neq 0 pause
exit /b 0
