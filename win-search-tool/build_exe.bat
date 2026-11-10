@echo off
chcp 65001 > nul
echo ====================================================
echo   로컬 텍스트 검색기 EXE 빌드 스크립트를 시작합니다.
echo ====================================================
echo.

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [오류] Python이 설치되어 있지 않거나 PATH에 추가되지 않았습니다.
    echo Python을 설치하고 다시 시도해 주세요.
    pause
    exit /b
)

echo [1/3] 의존성 라이브러리 설치 상태 확인 및 갱신...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [경고] 의존성 패키지 설치 중 오류가 발생했습니다. 빌드 오류로 이어질 수 있습니다.
)

echo.
echo [2/3] PyInstaller 설치 확인 및 설치...
pip show pyinstaller >nul 2>&1
if %errorlevel% neq 0 (
    echo PyInstaller가 설치되어 있지 않아 설치를 시작합니다...
    pip install pyinstaller
) else (
    echo PyInstaller가 이미 설치되어 있습니다.
)

echo.
echo [3/3] EXE 단일 실행 파일 빌드 중... (콘솔창 없음, 단일 파일, 아이콘 적용)
echo 명령어: pyinstaller --noconsole --onefile --icon=app_icon.ico local_search_tray.py
pyinstaller --noconsole --onefile --icon=app_icon.ico local_search_tray.py

if %errorlevel% eq 0 (
    echo.
    echo ====================================================
    echo   ★ 빌드 완료! 실행 파일이 성공적으로 생성되었습니다!
    echo   위치: dist\local_search_tray.exe
    echo.
    echo   dist 폴더로 이동하여 생성된 exe 파일을 실행해 보세요.
    echo ====================================================
) else (
    echo.
    echo [오류] 빌드 도중 에러가 발생했습니다. 로그를 확인해 주세요.
)
echo.
pause
