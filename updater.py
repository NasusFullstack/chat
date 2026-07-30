"""GitHub Releases 기반 자동 업데이트.

exe로 빌드되어 실행 중일 때만 의미가 있음 (소스로 실행 중이면 git pull로 갱신하면 되므로
gui_client.py 쪽에서 sys.frozen을 확인해 이 모듈 자체를 안 부름).

흐름: check_for_update()로 최신 릴리즈 태그를 확인 -> 있으면 download_update()로 새 exe를
임시 파일에 받음 -> apply_update_and_relaunch()가 배치 스크립트를 하나 띄우고 즉시 종료.
그 배치 스크립트가 (지금 실행 중인 프로세스가 완전히 끝나길 기다렸다가) 현재 exe 파일을
새 exe로 바꿔치기하고 다시 실행함 - 실행 중인 exe 파일은 자기 자신을 직접 지우거나
덮어쓸 수 없기 때문에 별도 프로세스가 필요함.
"""
import json
import os
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request

from version import APP_VERSION

GITHUB_REPO = "NasusFullstack/chat"
RELEASES_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
ASSET_NAME = "FriendChat_GUI.exe"
CHECK_TIMEOUT_SEC = 4
DOWNLOAD_TIMEOUT_SEC = 60
# 다운로드가 이 값보다 작으면 잘렸거나(네트워크 오류) 엉뚱한 내용(HTML 오류 페이지 등)을
# 받은 것으로 보고 적용을 포기함 - PySide6를 담은 onefile exe는 보통 수십MB는 나감
MIN_VALID_EXE_BYTES = 5_000_000


def _parse_version(v: str) -> tuple[int, ...]:
    v = v.strip().lstrip("vV")
    parts = []
    for piece in v.split("."):
        digits = "".join(ch for ch in piece if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts) or (0,)


def check_for_update() -> dict | None:
    """새 버전이 있으면 {"version": str, "download_url": str}를 반환, 없거나 확인 실패 시 None."""
    try:
        req = urllib.request.Request(
            RELEASES_API_URL,
            headers={"Accept": "application/vnd.github+json", "User-Agent": "FriendChatUpdater"},
        )
        with urllib.request.urlopen(req, timeout=CHECK_TIMEOUT_SEC) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return None

    latest_tag = data.get("tag_name", "")
    if not latest_tag or _parse_version(latest_tag) <= _parse_version(APP_VERSION):
        return None

    download_url = next(
        (a.get("browser_download_url") for a in data.get("assets", []) if a.get("name") == ASSET_NAME),
        None,
    )
    if not download_url:
        return None

    return {"version": latest_tag, "download_url": download_url}


def download_update(download_url: str, progress_cb=None) -> str:
    """새 exe를 임시 파일로 내려받고 그 경로를 반환. 크기가 이상하면 예외 발생."""
    fd, tmp_path = tempfile.mkstemp(suffix=".exe", prefix="FriendChat_GUI_new_")
    os.close(fd)
    try:
        req = urllib.request.Request(download_url, headers={"User-Agent": "FriendChatUpdater"})
        with urllib.request.urlopen(req, timeout=DOWNLOAD_TIMEOUT_SEC) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            read = 0
            with open(tmp_path, "wb") as f:
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    f.write(chunk)
                    read += len(chunk)
                    if progress_cb is not None:
                        progress_cb(read, total)
        if os.path.getsize(tmp_path) < MIN_VALID_EXE_BYTES:
            raise ValueError("다운로드된 파일 크기가 비정상적으로 작습니다 (잘렸거나 오류 페이지를 받았을 수 있음)")
    except Exception:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise
    return tmp_path


def apply_update_and_relaunch(new_exe_path: str):
    """현재 실행 파일을 새 exe로 교체하고 재시작함. 호출 즉시 현재 프로세스를 종료시키므로
    이 함수 리턴 이후 코드는 실행되지 않는다고 가정하고 호출해야 함."""
    current_exe = sys.executable
    pid = os.getpid()
    bat_fd, bat_path = tempfile.mkstemp(suffix=".bat", prefix="friendchat_update_")
    os.close(bat_fd)
    # tasklist로 원래 프로세스(pid)가 완전히 끝날 때까지 기다린 뒤 파일을 바꿔치기함.
    # move가 안티바이러스 검사 등으로 곧바로 안 먹힐 수 있어 몇 번 재시도함.
    # chcp 65001(UTF-8)을 안 하면 cmd.exe가 시스템 기본 코드페이지(한국어 Windows는
    # CP949)로 이 배치 파일을 읽어서, 폴더/파일 경로에 한글이 있으면 깨진 경로로
    # move/start를 실행해 "파일을 찾을 수 없음" 오류가 남 - UTF-8 BOM으로 저장하고
    # chcp 65001로 맞춰야 한글 경로가 안전하게 처리됨
    script = f"""@echo off
chcp 65001 >nul
:wait
tasklist /fi "PID eq {pid}" 2>nul | find "{pid}" >nul
if not errorlevel 1 (
    timeout /t 1 /nobreak >nul
    goto wait
)
set RETRY=0
:retry_move
move /y "{new_exe_path}" "{current_exe}" >nul 2>nul
if errorlevel 1 (
    set /a RETRY+=1
    if %RETRY% LSS 5 (
        timeout /t 1 /nobreak >nul
        goto retry_move
    )
)
rem 백신 실시간 검사가 방금 옮긴 exe(수십MB)를 스캔하는 도중에 바로 실행하면
rem 스캔 중인 DLL이 잠깨/격리되어 LoadLibrary 오류로 죽는 경우가 있어, 검사가
rem 끝날 시간을 잠깐 벌어줌
timeout /t 2 /nobreak >nul
start "" "{current_exe}"
del "%~f0"
"""
    with open(bat_path, "w", encoding="utf-8-sig") as f:
        f.write(script)
    subprocess.Popen(["cmd.exe", "/c", bat_path], creationflags=subprocess.CREATE_NO_WINDOW)
    sys.exit(0)
