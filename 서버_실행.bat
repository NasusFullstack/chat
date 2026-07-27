@echo off
chcp 65001 >nul
title 친구 채팅 - 서버
cd /d "%~dp0"

echo ============================================
echo   친구 채팅 서버 실행 준비 중...
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

REM --- 라이브러리 설치 (최초 1회만 오래 걸리고 이후엔 빠름) ---
echo [1/2] 필요한 라이브러리 확인/설치 중...
pip install -q -r requirements.txt
if errorlevel 1 (
    echo [오류] 라이브러리 설치 실패. 인터넷 연결을 확인해주세요.
    pause
    exit /b 1
)

echo [2/2] 서버 시작...
echo.
echo ============================================
echo  이 창은 서버가 켜져있는 동안 계속 켜두세요.
echo  친구들이 접속할 때 이 컴퓨터의 IP 주소가 필요합니다.
echo  (아래 IP 확인 참고)
echo ============================================
echo.
ipconfig | findstr /i "IPv4"
echo.

cd server
python server.py 6667

pause
