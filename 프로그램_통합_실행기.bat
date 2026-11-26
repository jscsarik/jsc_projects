@echo off
chcp 65001 > nul
setlocal enabledelayedexpansion
title JSC Projects - 데스크톱 프로그램 올인원 통합 실행기
cd /d "%~dp0"

:MENU
cls
echo ========================================================================
echo    ██╗███████╗ ██████╗    ██████╗ ██████╗  ██████╗      ██╗███████╗ ██████╗
echo    ██║██╔════╝██╔════╝    ██╔══██╗██╔══██╗██╔═══██╗     ██║██╔════╝██╔════╝
echo    ██║███████╗██║         ██████╔╝██████╔╝██║   ██║     ██║█████╗  ██║     
echo ██   ██║╚════██║██║         ██╔═══╝ ██╔══██╗██║   ██║██   ██║██╔══╝  ██║     
echo ╚█████╔╝███████║╚██████╗    ██║     ██║  ██║╚██████╔╝╚█████╔╝███████╗╚██████╗
echo  ╚════╝ ╚══════╝ ╚═════╝    ╚═╝     ╚═╝  ╚═╝ ╚═════╝  ╚════╝ ╚══════╝ ╚═════╝
echo ========================================================================
echo   🚀 JSC Projects - 데스크톱 프로그램 원클릭 통합 실행기
echo   Developer : 정승찬 (jscsarik)
echo   GitHub    : https://github.com/jscsarik/jsc_projects
echo ========================================================================
echo.
echo   [1] 🎵 가무음곡 (KaMuEumGok)      - 감성 데스크톱 로컬 음악 플레이어 (Next.js + Electron)
echo   [2] 👑 IDOL Manager             - K-POP 아이돌 기획사 육성 경영 시뮬레이션 게임 (PySide6)
echo   [3] ⚾ KBO 2026 애슐리 퀸즈      - 실시간 응원가(40곡) & 22인 선수단 프로필 전광판
echo   [4] 🎙️ DiscordAutoMute           - 마이크 음성인식 디스코드 자동 음소거 & 통화 제어
echo   [5] 🔍 win-search-tool          - Windows 로컬 문서 초고속 본문/파일명 실시간 검색기
echo   [6] 📡 24h-auto-broadcaster     - DIMA 24시간 무인 자동 방송 송출 관제 시스템 (OBS)
echo   [7] 🖥️ virtual-monitor-tools    - 가상 디스플레이 드라이버 진단 및 원클릭 복구
echo.
echo   [0] 🚪 종료
echo ========================================================================
set /p CHOICE="원하시는 프로그램 번호를 입력하세요 (0-7): "

if "%CHOICE%"=="1" (
    echo.
    echo 가무음곡을 실행합니다...
    start "" cmd /c "%~dp0kamueumgok\실행하기.bat"
    goto MENU
)
if "%CHOICE%"=="2" (
    echo.
    echo IDOL Manager를 실행합니다...
    start "" cmd /c "%~dp0idol-manager\실행하기.bat"
    goto MENU
)
if "%CHOICE%"=="3" (
    echo.
    echo KBO 2026 애슐리 퀸즈 응원가를 실행합니다...
    start "" cmd /c "%~dp0kbo-2026-cheer\실행하기.bat"
    goto MENU
)
if "%CHOICE%"=="4" (
    echo.
    echo DiscordAutoMute를 실행합니다...
    start "" cmd /c "%~dp0discord-auto-mute\실행하기.bat"
    goto MENU
)
if "%CHOICE%"=="5" (
    echo.
    echo win-search-tool을 실행합니다...
    start "" cmd /c "%~dp0win-search-tool\실행하기.bat"
    goto MENU
)
if "%CHOICE%"=="6" (
    echo.
    echo 24h-auto-broadcaster를 실행합니다...
    start "" cmd /k "%~dp024h-auto-broadcaster\실행하기.bat"
    goto MENU
)
if "%CHOICE%"=="7" (
    echo.
    echo virtual-monitor-tools를 실행합니다...
    start "" cmd /k "%~dp0virtual-monitor-tools\가상모니터_복구_실행.bat"
    goto MENU
)
if "%CHOICE%"=="0" (
    exit /b 0
)

echo 잘못 입력하셨습니다. 다시 선택해 주세요.
timeout /t 2 >nul
goto MENU
