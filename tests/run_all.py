"""회귀 테스트 일괄 실행.

필요한 서버(커스텀 채팅 서버 / IRC 테스트 데몬)를 직접 띄우고, 끝나면 정리한다.
예전에는 서버를 사람이 미리 띄워야 해서 안 띄우고 돌리면 절반이 타임아웃으로 나왔다.

    python tests/run_all.py            전부 실행
    python tests/run_all.py wrap link  이름에 그 단어가 든 것만 실행
"""
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
PY = sys.executable

# 테스트가 아니라 '테스트가 붙을 서버'인 파일들
DAEMONS = {"test_irc_daemon.py", "test_irc_ssl_daemon.py"}
# 서버 포트 규약 - 테스트들이 이 값을 전제로 함
PLAIN_PORT, SSL_PORT, IRC_PORT = "17667", "17697", "16700"
# 실행하면서 쌓이는 로컬 상태 - 테스트 사이에 지워야 "이미 존재하는 아이디"로 어긋나지 않음
STALE = ("server_data.json", "history.json")
TIMEOUT_SEC = 200


def clean_state():
    for name in STALE:
        path = os.path.join(REPO, name)
        if os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass


def start_servers():
    procs = []
    clean_state()
    procs.append(subprocess.Popen(
        [PY, os.path.join(REPO, "server.py"), PLAIN_PORT, SSL_PORT],
        cwd=REPO, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
    procs.append(subprocess.Popen(
        [PY, os.path.join(HERE, "test_irc_daemon.py"), IRC_PORT],
        cwd=REPO, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
    time.sleep(2.0)
    return procs


def main():
    filters = [a.lower() for a in sys.argv[1:]]
    names = sorted(
        f for f in os.listdir(HERE)
        if f.startswith("test_") and f.endswith(".py") and f not in DAEMONS
    )
    if filters:
        names = [n for n in names if any(f in n.lower() for f in filters)]
    if not names:
        print("실행할 테스트가 없음")
        return 0

    servers = start_servers()
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen", PYTHONIOENCODING="utf-8")
    failures = []
    try:
        for name in names:
            # 자동 재접속 테스트는 서버를 직접 죽였다 살리므로 우리 서버와 부딪힘
            needs_own_server = name == "test_reconnect.py"
            if needs_own_server:
                servers[0].terminate()
                time.sleep(1.0)
            clean_state()
            started = time.time()
            try:
                proc = subprocess.run([PY, os.path.join(HERE, name)], cwd=REPO,
                                      env=env, capture_output=True, timeout=TIMEOUT_SEC)
                code = proc.returncode
                tail = (proc.stdout + proc.stderr).decode("utf-8", "replace")
                tail = tail.strip().splitlines()[-5:]
            except subprocess.TimeoutExpired:
                code, tail = "TIMEOUT", []
            print(f"{name:38s} {code}  ({round(time.time() - started, 1)}s)", flush=True)
            if code != 0:
                failures.append((name, code, tail))
            if needs_own_server:
                servers[0] = subprocess.Popen(
                    [PY, os.path.join(REPO, "server.py"), PLAIN_PORT, SSL_PORT],
                    cwd=REPO, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                time.sleep(1.5)
    finally:
        for proc in servers:
            try:
                proc.terminate()
            except Exception:  # noqa: BLE001
                pass
        clean_state()

    print(f"\n총 {len(names)}개 / 실패 {len(failures)}개")
    for name, code, tail in failures:
        print(f"\n--- {name} (exit={code}) ---")
        for line in tail:
            print("   " + line)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
