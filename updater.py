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
# 자동 업데이트는 인스톨러(FriendChat_Setup.exe)를 조용히 실행하는 방식이 기본임.
#
# 왜 zip 통째 교체가 아니라 인스톨러인가 (실측으로 확인한 근본 원인):
# 예전 방식은 설치 폴더를 통째로 move(rename)해서 바꿔치기했는데, 폴더 안 파일이 단
# 하나라도 다른 프로세스에 열려 있으면 move 전체가 "Access is denied"로 실패함. 백신
# 실시간 검사가 DLL 하나만 잡고 있어도 재시도가 전부 실패해서 패치가 영영 안 됐음
# ("설치는 되는데 업데이트만 계속 안 된다"는 증상의 정체). 같은 상황에서도 파일 단위
# 접근은 정상이라, 파일 단위로 처리하는 Inno Setup 인스톨러는 문제없이 성공함.
# 게다가 인스톨러가 zip보다 용량도 작음(압축률이 더 좋음).
INSTALLER_ASSET_NAME = "FriendChat_Setup.exe"
# 구버전 호환/대비용 - 인스톨러 자산이 없는 릴리즈에서만 zip 방식으로 물러남
ASSET_NAME = "FriendChat_GUI.zip"
CHECK_TIMEOUT_SEC = 4
DOWNLOAD_TIMEOUT_SEC = 120
# 다운로드가 이 값보다 작으면 잘렸거나(네트워크 오류) 엉뚱한 내용(HTML 오류 페이지 등)을
# 받은 것으로 보고 적용을 포기함 - PySide6를 담은 업데이트 패키지는 보통 수십MB는 나감
MIN_VALID_PACKAGE_BYTES = 20_000_000
# 교체 후 새 exe 파일 자체가 이 값보다 작으면(손상/잘림) 롤백함
MIN_VALID_EXE_BYTES = 1_000_000
# 같은 버전으로의 업데이트 "시도" 자체가 이 횟수만큼 연속되면(그 이후 성공했는지는 이
# 프로세스가 이미 종료돼서 알 수 없음 - apply_update_and_relaunch가 배치 스크립트를
# 띄우고 곧장 sys.exit함) 더 이상 자동으로 재시도하지 않음. 이게 없으면: 이 컴퓨터에서만
# 계속 실패하는 경우(백업/롤백이 뭔가에 막혀 안 되는 등) 매 실행마다 "적용 중입니다"
# 화면만 보이고 앱 자체를 절대 못 켜는 무한 루프에 갇힘 - 실제로 한 사용자가 이걸 겪음.
# 성공하면 다음 실행의 APP_VERSION이 이미 그 버전이라 더 비교할 신버전이 없어져서
# 이 카운터는 자연스럽게 의미가 없어짐(따로 성공을 감지해서 초기화할 필요가 없음)
MAX_UPDATE_ATTEMPTS = 3

# 업데이트 직후 자동으로 다시 실행될 때 붙는 인자. 방금 최신 버전으로 갈아탔으므로 새로
# 뜬 앱이 업데이트 확인(네트워크 왕복, 최대 CHECK_TIMEOUT_SEC초)을 또 할 이유가 없음 -
# 이게 없으면 "패치 끝났는데 앱이 늦게 뜨는" 체감 대기가 그만큼 길어짐
POST_UPDATE_FLAG = "--post-update"


def _update_state_path() -> str:
    exe_dir = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
    return os.path.join(exe_dir, "update_attempt_state.json")


def _load_update_state() -> dict:
    path = _update_state_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def record_update_attempt(version: str) -> None:
    """실제로 apply_update_and_relaunch를 시도하기 직전에 호출함(성공/실패 여부와 무관하게
    "시도했다"는 사실만 기록 - 이 프로세스는 곧 종료되므로 결과를 알 방법이 없음).
    같은 버전이면 횟수를 올리고, 그 사이 더 새 버전이 나왔으면 그 버전 기준으로 새로 셈"""
    state = _load_update_state()
    if state.get("version") == version:
        state["attempts"] = state.get("attempts", 0) + 1
    else:
        state = {"version": version, "attempts": 1}
    try:
        with open(_update_state_path(), "w", encoding="utf-8") as f:
            json.dump(state, f)
    except OSError:
        pass


def _should_skip_update(version: str) -> bool:
    state = _load_update_state()
    return state.get("version") == version and state.get("attempts", 0) >= MAX_UPDATE_ATTEMPTS


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

    if _should_skip_update(latest_tag):
        return None

    assets = {a.get("name"): a.get("browser_download_url") for a in data.get("assets", [])}

    # 인스톨러 방식이 기본(파일 잠금에 강함). 없으면 예전 zip 방식으로 물러남
    installer_url = assets.get(INSTALLER_ASSET_NAME)
    if installer_url:
        return {"version": latest_tag, "download_url": installer_url, "kind": "installer"}

    zip_url = assets.get(ASSET_NAME)
    if zip_url:
        return {"version": latest_tag, "download_url": zip_url, "kind": "zip"}

    return None


def download_update(download_url: str, progress_cb=None, suffix: str = ".zip") -> str:
    """새 버전 패키지를 임시 파일로 내려받고 그 경로를 반환. 크기가 이상하면 예외 발생."""
    fd, tmp_path = tempfile.mkstemp(suffix=suffix, prefix="FriendChat_GUI_new_")
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


def _write_batch(path: str, script: str) -> None:
    """배치 파일을 UTF-8 BOM으로 저장.

    BOM은 반드시 필요하다. 설치 경로에 한글("춥채팅")이 들어가는데, BOM 없이 저장하면
    cmd가 그 한글을 cp949로 잘못 읽어 경로가 깨진다(실측: '占�' is not recognized).
    대신 cmd는 BOM을 '첫 명령의 일부'로 읽어버려서 첫 줄이 반드시 하나 깨진다 - 그래서
    스크립트 첫 줄은 깨져도 되는 더미로 두고 진짜 명령은 둘째 줄부터 시작한다
    (build_installer_batch 참고).
    """
    with open(path, "w", encoding="utf-8-sig", newline="\r\n") as f:
        f.write(script)


def update_log_path() -> str:
    """업데이트 배치가 진행 상황을 적는 파일.

    이 배치는 창 없이 돌아서 무슨 일이 있었는지 볼 방법이 없다. "패치는 됐는데 앱이
    안 켜진다"를 추측으로 고치다 두 번 헛짚었기 때문에, 어디까지 갔는지 기록을 남긴다.
    """
    return os.path.join(tempfile.gettempdir(), "friendchat_update.log")


def build_installer_batch(installer_path: str, current_exe: str, pid: int,
                          log_path: str = "") -> str:
    """인스톨러 실행 + 앱 재시작을 담당하는 배치 스크립트 내용.

    실제로 돌려보고 검증할 수 있도록 apply_installer_and_relaunch()에서 분리해둠
    (여기 로직이 틀리면 "패치는 됐는데 앱이 안 켜지는" 증상이 나는데, 눈으로 읽어서는
    잘 안 보인다).

    첫 줄이 왜 의미 없는 `@rem`인가:
    파일을 BOM으로 저장하는데(한글 설치 경로 때문에 필수 - _write_batch 참고) cmd가 그
    BOM을 첫 명령의 일부로 읽어버려서 첫 줄은 무조건 하나 깨진다. 그 자리에 `@echo off`를
    두면 echo가 안 꺼져서 이후 모든 명령이 화면에 찍히므로, 깨져도 되는 더미를 앞에 세우고
    `@echo off`는 둘째 줄에 둔다.

    배치 안의 주석을 영어로 쓰는 이유: 스크립트에 비ASCII를 늘리지 않기 위함(왜 이렇게
    돼 있는지에 대한 설명은 이 파이썬 소스에 한글로 남긴다).

    - `start`를 인스톨러 실행에 쓰면 안 된다. `start`는 cmd 내장 명령이라 콘솔이 필요한데
      이 배치는 CREATE_NO_WINDOW로 돌기 때문에 멈춘다. 직접 호출하면 cmd가 원래 끝날
      때까지 기다리므로 `/wait` 없이도 순서가 보장된다.
    - 인스톨러 뒤의 `ping`(대기)은 군더더기가 아니다. 리턴 후에도 파일 잠금 해제가 덜 끝나
      있을 수 있어서, 이걸 지웠더니 "패치는 됐는데 앱이 안 켜지는" 증상이 났다.
    - 지연에 `timeout /t`를 쓰면 안 된다. 콘솔 없는 환경에서 즉시 실패한다.
    """
    log_path = log_path or update_log_path()
    return f"""@rem BOM guard - this line is expected to be eaten by the UTF-8 BOM
@echo off
chcp 65001 >nul
set LOG="{log_path}"
echo [start] %DATE% %TIME%> %LOG%
:wait
tasklist /fi "PID eq {pid}" 2>nul | find "{pid}" >nul
if not errorlevel 1 (
    ping -n 2 127.0.0.1 >nul
    goto wait
)
echo [app closed] %TIME%>> %LOG%

rem Run the installer directly (no "start"): cmd waits for it to finish.
"{installer_path}" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART
echo [installer done] exit=%errorlevel% %TIME%>> %LOG%

rem Settle time: the installer can return before file locks are released.
ping -n 4 127.0.0.1 >nul

rem Relaunch, retrying until the exe is in place.
set RETRY=0
:launch
if exist "{current_exe}" goto doLaunch
set /a RETRY+=1
echo [waiting for exe] try=%RETRY% %TIME%>> %LOG%
if %RETRY% LSS 10 (
    ping -n 3 127.0.0.1 >nul
    goto launch
)
echo [FAILED] exe never appeared: {current_exe}>> %LOG%
goto launched

:doLaunch
echo [launching] {current_exe}>> %LOG%
start "" "{current_exe}" {POST_UPDATE_FLAG}
echo [launched] errorlevel=%errorlevel% %TIME%>> %LOG%

:launched
del "{installer_path}" >nul 2>nul
del "%~f0"
"""


def apply_installer_and_relaunch(installer_path: str):
    """받아둔 인스톨러를 조용히 실행해서 업데이트하고 앱을 다시 띄움.

    폴더 통째 move 방식과 달리 Inno Setup은 파일 단위로 처리하므로, 백신이 특정 파일을
    잠시 잡고 있어도 정상적으로 덮어쓸 수 있음(그게 "설치는 되는데 패치는 안 되던" 문제의
    해법). 인스톨러는 PrivilegesRequired=lowest로 만들어져 있어 UAC 창도 안 뜸.

    현재 프로세스가 살아있는 동안에는 자기 자신의 파일을 덮어쓸 수 없으므로, 여기서도
    "PID가 끝나길 기다렸다가 실행하는 배치"를 쓴다(기존 방식과 동일한 검증된 패턴).
    """
    bat_fd, bat_path = tempfile.mkstemp(suffix=".bat", prefix="friendchat_setup_")
    os.close(bat_fd)
    script = build_installer_batch(installer_path, sys.executable, os.getpid())
    _write_batch(bat_path, script)
    subprocess.Popen(["cmd.exe", "/c", bat_path], creationflags=subprocess.CREATE_NO_WINDOW)
    sys.exit(0)


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
    backup_exe_path = os.path.join(backup_dir, exe_name)
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
    rem 원래 8회(16초)였는데, 같은 사용자 환경에서 같은 원인으로 두 번 실패한 걸 보면
    rem 일시적인 백신 스캔보다 더 오래 잠기는 뭔가(백신 딥스캔, 인덱싱 등)가 있는 것
    rem 같아서 20회(약 40초)로 늘림
    if %RETRY% LSS 20 (
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
    if %RETRY% LSS 20 (
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
    if %RETRY% LSS 20 (
        ping -n 2 127.0.0.1 >nul
        goto retry_rollback
    )
)

rem 롤백(백업 -> install_dir로 되돌리기)까지 실패하면 install_dir는 비어있는데
rem backup_dir({backup_dir})에는 예전 정상 버전이 멀쩡히 남아있는 상태임. 이때 그냥
rem 존재하지도 않는 install_dir의 exe를 실행하려 들면 앱이 그냥 안 뜨고 "사라진"
rem 것처럼 보임 - backup_dir에서라도 직접 실행해서 최소한 앱은 계속 쓸 수 있게 함
rem (다음 업데이트 때 install_dir가 다시 채워지길 기대함)
if exist "{new_exe_path}" (
    start "" "{current_exe}"
) else (
    start "" "{backup_exe_path}"
)
del "%~f0"
exit /b

:abort_keep_current
start "" "{current_exe}"
del "%~f0"
"""
    _write_batch(bat_path, script)
    subprocess.Popen(["cmd.exe", "/c", bat_path], creationflags=subprocess.CREATE_NO_WINDOW)
    sys.exit(0)
