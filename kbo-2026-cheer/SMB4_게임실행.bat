@echo off
chcp 65001 > nul
title SMB4 + KBO 응원가 플레이어 실행기

echo ============================================================
echo  Super Mega Baseball 4 및 KBO 응원가 플레이어를 실행합니다!
echo ============================================================

:: 1. 응원가 플레이어 실행 (검은색 콘솔창 없이 백그라운드 실행)
start "" pythonw "%~dp0main.py"

:: 2. 스팀을 통해 Super Mega Baseball 4 실행
start "" "steam://rungameid/1487210"

exit
