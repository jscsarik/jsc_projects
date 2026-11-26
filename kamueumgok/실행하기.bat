@echo off
chcp 65001 > nul
setlocal enabledelayedexpansion
title KaMuEumGok (가무음곡) - 실행기
cd /d "%~dp0"

echo ============================================================
echo   🎵 KaMuEumGok (가무음곡) - 감성 데스크톱 음악 플레이어
echo   Developer : 정승찬 (jscsarik)
echo   GitHub    : https://github.com/jscsarik/jsc_projects
echo ============================================================
echo.

:: 1. Node.js 설치 확인
where node >nul 2>&1
if %errorlevel% neq 0 (
    echo [오류] Node.js가 시스템에 설치되어 있지 않습니다!
    echo.
    echo 가무음곡을 실행하려면 Node.js 환경이 필요합니다.
    echo https://nodejs.org/ 에서 LTS 버전을 다운로드 및 설치한 후 다시 실행해 주세요.
    echo.
    pause
    exit /b 1
)

:: 2. 필수 의존성(node_modules) 확인 및 자동 설치
if not exist "%~dp0node_modules" (
    echo ------------------------------------------------------------
    echo [최초 실행 감지] 필수 라이브러리(Next.js, Electron 등)가 없습니다.
    echo 자동으로 패키지를 설치합니다... (인터넷 연결 필요, 최초 1회만 진행)
    echo ------------------------------------------------------------
    echo.
    call npm install
    if %errorlevel% neq 0 (
        echo.
        echo [경고] 패키지 설치 중 오류가 발생했습니다. 네트워크 연결을 확인해 주세요.
        pause
        exit /b 1
    )
    echo.
    echo [성공] 모든 패키지 설치가 완료되었습니다!
    echo.
)

:: 3. 가무음곡 실행
echo [실행 중] 가무음곡(KaMuEumGok)을 시작합니다. 잠시만 기다려 주세요...

:: 이전 실행에서 멈춰있던 3000번 포트의 잔여 node 프로세스 정리
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :3000 ^| findstr LISTENING 2^>nul') do (
    tasklist /fi "pid eq %%a" 2^>nul | findstr /i "node" >nul && taskkill /f /pid %%a >nul 2>&1
)

if exist "%~dp0node_modules\.bin\electron.cmd" (
    start "" "%~dp0node_modules\.bin\electron.cmd" .
) else (
    start "" npx electron .
)
exit /b 0
