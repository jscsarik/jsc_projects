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
    echo [EXE 감지] 독립 실행 파일(dist\local_search_tray.exe)로 즉시 실행합니다.
    start "" "%~dp0dist\local_search_tray.exe"
    exit /b 0
)

:: 2. Python 환경 검사
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [오류] Python이 설치되어 있지 않으며 dist\local_search_tray.exe를 찾을 수 없습니다.
    echo Python 3.10 이상을 설치한 후 다시 실행해 주세요.
    echo.
    pause
    exit /b 1
)

:: 3. 의존성 자동 점검 및 설치
python -c "import watchdog, chardet, pystray, PIL" >nul 2>&1
if %errorlevel% neq 0 (
    echo [최초 실행 감지] 필수 검색/트레이 라이브러리를 설치합니다...
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

:: 4. 백그라운드 트레이 실행
echo [실행 중] 시스템 트레이로 검색기를 실행합니다...
where pythonw >nul 2>&1
if %errorlevel% eq 0 (
    start "" pythonw "%~dp0local_search_tray.py"
) else (
    start "" python "%~dp0local_search_tray.py"
)
exit /b 0
