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

echo [1/6] Installing required libraries...
pip install -q -r requirements.txt
pip install -q pyinstaller

echo [2/6] Building GUI client (recommended, for friends)...
rem --onedir: 실행할 때마다 임시폴더에 압축을 새로 푸는 --onefile 방식은 그 타이밍에
rem 백신이 끼어들면 "Failed to load Python DLL" 오류가 나는 경우가 있어서, 미리 풀린
rem 상태로 배포하는 --onedir로 바꿈 (대신 파일 하나가 아니라 폴더로 나눠줘야 함 -
rem installer.iss로 만든 설치 프로그램을 같이 배포하면 사용자는 그래도 파일 하나만 받음)
rem 치트 연출용 이미지(배틀크루저/미네랄/가스)는 있으면 같이 넣고, 없으면 건너뜀 -
rem 앱이 파일 없을 때는 직접 그리는 쪽으로 폴백하므로 없어도 빌드/실행 둘 다 정상
set EXTRA_DATA=
if exist battlecruiser.png set EXTRA_DATA=%EXTRA_DATA% --add-data "battlecruiser.png;."
if exist mineral.png set EXTRA_DATA=%EXTRA_DATA% --add-data "mineral.png;."
if exist gas.png set EXTRA_DATA=%EXTRA_DATA% --add-data "gas.png;."
pyinstaller --noconfirm --clean --onedir --windowed --icon=icon.ico --add-data "icon.ico;." --add-data "icon.png;." --add-data "CHANGELOG.md;."%EXTRA_DATA% --name FriendChat_GUI gui_client.py

echo [3/6] Building CLI client (lightweight, for friends)...
pyinstaller --noconfirm --clean --onefile --console --name FriendChat_CLI cli_client.py

echo [4/6] Building server program (for the host)...
pyinstaller --noconfirm --clean --onefile --console --name FriendChat_Server server.py

echo [5/6] Packaging GUI update archive (dist\FriendChat_GUI.zip)...
powershell -Command "Compress-Archive -Path 'dist\FriendChat_GUI\*' -DestinationPath 'dist\FriendChat_GUI.zip' -Force"

echo [6/6] Building installer (FriendChat_Setup.exe)...
set ISCC=
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe
if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe
if "%ISCC%"=="" (
    echo   [Skipped] Inno Setup not found. Install it from https://jrsoftware.org/isdl.php
    echo   to also build FriendChat_Setup.exe ^(the installer to share with friends^).
) else (
    "%ISCC%" /DAppVersion=0.0.0-local installer.iss
)

echo.
echo ============================================
echo  Files created:
echo   - installer_output\FriendChat_Setup.exe (share this with friends - recommended)
echo   - dist\FriendChat_GUI.zip                (used by the app's own auto-updater)
echo   - dist\FriendChat_CLI.exe                (lightweight alternative)
echo   - dist\FriendChat_Server.exe             (host runs this one)
echo.
echo  These exe files run without Python installed.
echo ============================================
echo.
pause
