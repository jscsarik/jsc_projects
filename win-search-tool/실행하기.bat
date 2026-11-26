@echo off
chcp 65001 > nul
setlocal enabledelayedexpansion
title win-search-tool (로컬 문서 실시간 검색기) - 실행기
cd /d "%~dp0"

echo ============================================================
echo   🔍 win-search-tool - Windows 실시간 문서 본문 검색기
echo   Developer : 정승찬 (jscsarik)
echo   GitHub    : https://github.com/jscsarik/jsc_projects
echo ============================================================
echo.

:: 1. 기빌드된 단독 실행 파일(EXE)이 있으면 즉시 실행 (Python 불필요)
if exist "%~dp0dist\local_search_tray.exe" (
    echo [EXE 감지] 독립 실행 파일(local_search_tray.exe)로 검색기 창을 즉시 엽니다...
    start "" "%~dp0dist\local_search_tray.exe"
    timeout /t 2 >nul
    exit /b 0
)

:: 2. Python 환경 검사
where python >nul 2>&1
if %errorlevel% neq 0 (
    where py >nul 2>&1
    if !errorlevel! neq 0 (
        echo [오류] Python이 설치되어 있지 않으며 dist\local_search_tray.exe를 찾을 수 없습니다.
        echo Python 3.10 이상을 설치한 후 다시 실행해 주세요.
        pause
        exit /b 1
    )
    set PY_CMD=py
) else (
    set PY_CMD=python
)

:: 3. 의존성 자동 점검 및 설치
echo [라이브러리 확인] 필수 모듈을 확인합니다...
!PY_CMD! -m pip install -r requirements.txt >nul 2>&1

:: 4. 검색기 실행
echo [실행 중] 검색기 창을 엽니다...
!PY_CMD! "%~dp0local_search_tray.py"
if %errorlevel% neq 0 pause
exit /b 0
