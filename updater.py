"""GitHub Releases 기반 자동 업데이트.

exe로 빌드되어 실행 중일 때만 의미가 있음 (소스로 실행 중이면 git pull로 갱신하면 되므로
gui_client.py 쪽에서 sys.frozen을 확인해 이 모듈 자체를 안 부름).

--onedir 배포로 바뀌면서(설치 폴더 = exe + _internal 폴더 세트) 업데이트 단위도 파일
하나가 아니라 폴더 전체가 됨. 흐름: check_for_update()로 최신 릴리즈 태그를 확인 ->
있으면 download_update()로 업데이트 패키지(zip)를 임시 파일에 받음 -> Python에서 미리
압축을 풀어둔 뒤 apply_update_and_relaunch()가 배치 스크립트를 하나 띄우고 즉시 종료.
그 배치 스크립트가 (지금 실행 중인 프로세스가 완전히 끝나길 기다렸다가) 설치 폴더를
통째로 백업해두고 새 폴더로 바꿔치기한 뒤 다시 실행함 - 실행 중인 자기 자신의 파일들은
직접 지우거나 덮어쓸 수 없기 때문에 별도 프로세스가 필요함.
"""
import json
import os
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile

from version import APP_VERSION

GITHUB_REPO = "NasusFullstack/chat"
RELEASES_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
# 인스톨러(FriendChat_Setup.exe)는 최초 설치 전용이고, 자동 업데이트는 이 zip을 받아서
# 설치 폴더 내용물을 통째로 교체함 (onedir 배포라 파일이 exe 하나가 아니라 여러 개임)
ASSET_NAME = "FriendChat_GUI.zip"
CHECK_TIMEOUT_SEC = 4
DOWNLOAD_TIMEOUT_SEC = 120
# 다운로드가 이 값보다 작으면 잘렸거나(네트워크 오류) 엉뚱한 내용(HTML 오류 페이지 등)을
# 받은 것으로 보고 적용을 포기함 - PySide6를 담은 업데이트 패키지는 보통 수십MB는 나감
MIN_VALID_PACKAGE_BYTES = 20_000_000
# 교체 후 새 exe 파일 자체가 이 값보다 작으면(손상/잘림) 롤백함
MIN_VALID_EXE_BYTES = 1_000_000


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
    """새 버전 패키지(zip)를 임시 파일로 내려받고 그 경로를 반환. 크기가 이상하면 예외 발생."""
    fd, tmp_path = tempfile.mkstemp(suffix=".zip", prefix="FriendChat_GUI_new_")
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
        actual_size = os.path.getsize(tmp_path)
        if actual_size < MIN_VALID_PACKAGE_BYTES:
            raise ValueError("다운로드된 파일 크기가 비정상적으로 작습니다 (잘렸거나 오류 페이지를 받았을 수 있음)")
        # Content-Length를 서버가 알려준 경우, 실제로 받은 바이트 수가 정확히 일치하는지도
        # 확인함 - 최소 크기 기준만으로는 "충분히 크지만 중간에 끊긴" 다운로드를 못 걸러냄
        if total and actual_size != total:
            raise ValueError(f"다운로드가 중간에 끊겼습니다 (받은 크기 {actual_size} != 예상 크기 {total})")
    except Exception:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise
    return tmp_path


def apply_update_and_relaunch(new_package_path: str):
    """새 버전 zip을 미리 풀어둔 뒤, 설치 폴더 전체를 새 내용으로 교체하고 재시작함.
    호출 즉시 현재 프로세스를 종료시키므로 이 함수 리턴 이후 코드는 실행되지 않는다고
    가정하고 호출해야 함.

    교체 전에 기존 설치 폴더를 통째로 백업해뒀다가, 교체 후 새 exe 크기가 이상하면
    (안티바이러스가 옮기는 도중 내용을 건드렸거나 손상된 경우) 백업으로 롤백함 -
    그냥 덮어쓰기만 하면 실패했을 때 앱 자체가 완전히 망가진 채로 남기 때문에,
    실패해도 최소한 원래 쓰던 버전으로는 계속 실행되도록 안전망을 둠."""
    # 배치 스크립트가 폴더를 통째로 옮기기만 하면 되도록, 압축은 여기서 미리 풀어둠
    # (배치/cmd로 zip을 안정적으로 푸는 것보다 Python zipfile이 훨씬 신뢰할 수 있음)
    extract_dir = tempfile.mkdtemp(prefix="FriendChat_GUI_new_")
    with zipfile.ZipFile(new_package_path, "r") as zf:
        zf.extractall(extract_dir)
    try:
        os.remove(new_package_path)
    except OSError:
        pass

    current_exe = sys.executable
    exe_name = os.path.basename(current_exe)
    install_dir = os.path.dirname(current_exe)
    backup_dir = install_dir + ".bak"
    new_exe_path = os.path.join(install_dir, exe_name)
    pid = os.getpid()

    bat_fd, bat_path = tempfile.mkstemp(suffix=".bat", prefix="friendchat_update_")
    os.close(bat_fd)
    # tasklist로 원래 프로세스(pid)가 완전히 끝날 때까지 기다린 뒤 폴더를 통째로 바꿔치기함.
    # move가 안티바이러스 검사 등으로 곧바로 안 먹힐 수 있어 몇 번 재시도함.
    # chcp 65001(UTF-8)을 안 하면 cmd.exe가 시스템 기본 코드페이지(한국어 Windows는
    # CP949)로 이 배치 파일을 읽어서, 폴더/파일 경로에 한글이 있으면 깨진 경로로
    # move/start를 실행해 "파일을 찾을 수 없음" 오류가 남 - UTF-8 BOM으로 저장하고
    # chcp 65001로 맞춰야 한글 경로가 안전하게 처리됨.
    #
    # timeout /t 는 콘솔이 없는 상태로 실행되면(우리 GUI exe 자체가 --windowed라
    # 콘솔이 없고, 거기서 띄운 이 배치도 콘솔이 없음) "Input redirection is not
    # supported"라며 그 자리에서 바로 실패해서 실제로는 전혀 안 기다려짐 - 그래서
    # 백신 스캔을 피하려던 지연시간이 사실 하나도 작동을 안 하고 있었음. 콘솔 여부와
    # 무관하게 항상 동작하는 ping을 딜레이 용도로 대신 씀(ping -n N은 대략 N-1초 걸림).
    #
    # move는 대상 경로가 이미 폴더로 존재하면 그 안으로 들어가버리므로(덮어쓰기가 아니라
    # 중첩됨), 매번 대상 경로를 먼저 지워서 "존재하지 않는 경로"로 만들어둔 다음에
    # move해야 폴더 자체가 그 이름으로 바뀌치기됨.
    script = f"""@echo off
chcp 65001 >nul
:wait
tasklist /fi "PID eq {pid}" 2>nul | find "{pid}" >nul
if not errorlevel 1 (
    ping -n 2 127.0.0.1 >nul
    goto wait
)

rmdir /s /q "{backup_dir}" >nul 2>nul
set RETRY=0
:retry_backup
move /y "{install_dir}" "{backup_dir}" >nul 2>nul
if not exist "{backup_dir}" (
    set /a RETRY+=1
    if %RETRY% LSS 8 (
        ping -n 2 127.0.0.1 >nul
        goto retry_backup
    )
)

rem 백업(원래 설치 폴더를 .bak로 옮기는 것) 자체가 끝내 실패했다면, 그건 install_dir가
rem 아직 잠겨있다는 뜻임 - 이 상태에서 그냥 다음 단계로 넘어가 rmdir로 install_dir를
rem 지워버리면, 백업도 없고 새 파일 이동도 실패할 경우 원본이 통째로 사라짐(실제로
rem 이렇게 GUI.exe가 사라지는 사고가 났음). 백업이 안 됐으면 절대 원본을 건드리지 않고
rem 이번 업데이트만 포기함 - 다음 실행 때 다시 시도됨
if not exist "{backup_dir}" goto abort_keep_current

set RETRY=0
:retry_move
rmdir /s /q "{install_dir}" >nul 2>nul
move /y "{extract_dir}" "{install_dir}" >nul 2>nul
if not exist "{new_exe_path}" (
    set /a RETRY+=1
    if %RETRY% LSS 8 (
        ping -n 2 127.0.0.1 >nul
        goto retry_move
    )
)

rem 새로 옮긴 exe가 정상 크기인지 확인 - 백신 등이 옮기는 도중 내용을 손상시켰으면
rem 너무 작게 나오므로, 그 경우 방금 만든 백업으로 되돌려서 최소한 예전 버전은 계속 쓰게 함
if not exist "{new_exe_path}" goto rollback
for %%A in ("{new_exe_path}") do if %%~zA LSS {MIN_VALID_EXE_BYTES} goto rollback

rmdir /s /q "{backup_dir}" >nul 2>nul
rem onedir 배포라 매 실행마다 압축을 새로 푸는 구조는 아니지만, 방금 막 새로 옮겨진
rem exe/DLL들을 백신이 처음 보고 스캔하는 순간에 곧바로 실행하면 여전히 잠깐 걸릴 수
rem 있어서 짧게 여유를 둠
ping -n 5 127.0.0.1 >nul
start "" "{current_exe}"
del "%~f0"
exit /b

:rollback
rmdir /s /q "{install_dir}" >nul 2>nul
set RETRY=0
:retry_rollback
move /y "{backup_dir}" "{install_dir}" >nul 2>nul
if not exist "{new_exe_path}" (
    set /a RETRY+=1
    if %RETRY% LSS 8 (
        ping -n 2 127.0.0.1 >nul
        goto retry_rollback
    )
)
start "" "{current_exe}"
del "%~f0"
exit /b

:abort_keep_current
start "" "{current_exe}"
del "%~f0"
"""
    with open(bat_path, "w", encoding="utf-8-sig") as f:
        f.write(script)
    subprocess.Popen(["cmd.exe", "/c", bat_path], creationflags=subprocess.CREATE_NO_WINDOW)
    sys.exit(0)
