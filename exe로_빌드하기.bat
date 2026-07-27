@echo off
chcp 65001 >nul
title Build EXE
cd /d "%~dp0"

echo ============================================
echo   Friend Chat - Building EXE files
echo   (Run this once on your computer only)
echo ============================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [Error] Python is not installed.
    echo Install it from https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during install.
    pause
    exit /b 1
)

echo [1/4] Installing required libraries...
pip install -q -r requirements.txt
pip install -q pyinstaller

echo [2/4] Building client program (for friends)...
pyinstaller --noconfirm --onefile --console --name FriendChat --distpath dist --workpath build client\tui_client.py

echo [3/4] Building server program (for the host)...
pyinstaller --noconfirm --onefile --console --name FriendChat_Server --distpath dist --workpath build --paths server server\server.py

echo [4/4] Done!
echo.
echo ============================================
echo  Files created inside the 'dist' folder:
echo   - FriendChat.exe         (share this with friends)
echo   - FriendChat_Server.exe  (host runs this one)
echo.
echo  These exe files run without Python installed.
echo ============================================
echo.
pause
