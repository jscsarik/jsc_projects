@echo off
chcp 65001 > nul
echo ====================================================
echo   로컬 텍스트 검색기 의존성 라이브러리 설치를 시작합니다.
echo ====================================================
echo.
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [오류] Python이 설치되어 있지 않거나 PATH에 추가되지 않았습니다.
    echo Python을 설치하고 다시 시도해 주세요.
    pause
    exit /b
)

echo [정보] pip를 통해 requirements.txt에 등록된 패키지를 설치합니다...
pip install -r requirements.txt

if %errorlevel% eq 0 (
    echo.
    echo ====================================================
    echo   의존성 라이브러리 설치가 성공적으로 완료되었습니다!
    echo   이제 local_search_tray.py를 실행하실 수 있습니다.
    echo ====================================================
) else (
    echo.
    echo [오류] 설치 중 문제가 발생했습니다. 에러 메시지를 확인해 주세요.
)
echo.
pause
