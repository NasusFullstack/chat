@echo off
chcp 65001 >nul
title 친구 채팅
cd /d "%~dp0"

echo ============================================
echo   친구 채팅 실행 준비 중...
echo ============================================
echo.

REM --- Python 설치 확인 ---
python --version >nul 2>&1
if errorlevel 1 (
    echo [오류] Python이 설치되어 있지 않습니다.
    echo https://www.python.org/downloads/ 에서 설치 후 다시 실행해주세요.
    echo 설치 시 "Add Python to PATH" 체크박스를 꼭 체크하세요.
    pause
    exit /b 1
)

echo [1/2] 필요한 라이브러리 확인/설치 중...
pip install -q -r requirements.txt
if errorlevel 1 (
    echo [오류] 라이브러리 설치 실패. 인터넷 연결을 확인해주세요.
    pause
    exit /b 1
)

echo [2/2] 준비 완료!
echo.

set /p SERVER_IP="서버 주소를 입력하세요 (같은 컴퓨터면 그냥 Enter): "
if "%SERVER_IP%"=="" set SERVER_IP=127.0.0.1

set /p SERVER_PORT="포트 번호 (그냥 Enter하면 6667): "
if "%SERVER_PORT%"=="" set SERVER_PORT=6667

cd client
python tui_client.py %SERVER_IP% %SERVER_PORT%

pause
