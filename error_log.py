"""예상 못 한 오류를 파일로 남긴다.

왜 필요한가: PySide6 6.11에서는 신호 처리(슬롯) 안에서 예외가 나도 **앱이 죽지 않는다**.
파이썬이 stderr에 트레이스백을 찍고 그냥 넘어간다. 그런데 배포된 앱은 `--windowed`라
콘솔이 없어서 그 stderr가 어디에도 안 남는다. 결과적으로:

- 화면 갱신 도중에 예외가 나면 그 뒤 코드가 안 돌아서 **채팅/참여자 목록이 빈 채로 남고**
- 앱은 멀쩡히 살아 있으며
- 다음 이벤트가 오면 저절로 다시 채워져서 "됐다 안 됐다" 하는 것처럼 보이고
- 무엇이 터졌는지 알 방법이 전혀 없다

그래서 트레이스백을 파일에 남긴다. 재현이 안 되는 증상은 기록이 없으면 영영 못 고친다.

로그는 앱 데이터(history.json/avatars.json)와 같은 폴더에 둔다. 시스템 임시 폴더는 쓰지
않는다 - 압축 프로그램 같은 게 TEMP 경로를 자기 폴더로 바꿔놓는 경우가 있어서(실제로
`...\ESTsoft\CreatorTemp\`로 잡혀 있었다) 남의 폴더에 우리 기록이 쌓이고 찾기도 어렵다.
(업데이트 배치 로그는 예외로 TEMP에 둔다 - 인스톨러가 설치 폴더를 갈아엎는 중에 쓰므로.)
"""
import datetime
import os
import sys

import app_paths
import tempfile
import threading
import traceback

MAX_BYTES = 512 * 1024  # 이만큼 넘으면 새로 시작 - 무한정 커지지 않게
_installed = False
_lock = threading.Lock()


def _app_dir() -> str:
    """앱 데이터가 모여 있는 폴더(설치 폴더 / 소스 실행 시 저장소 루트)."""
    return app_paths.data_dir()


def error_log_path() -> str:
    try:
        path = os.path.join(_app_dir(), "friendchat_error.log")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        return path
    except OSError:
        # 설치 폴더에 못 쓰는 환경(권한 등)이면 기록 자체를 포기하지 말고 임시 폴더로
        return os.path.join(tempfile.gettempdir(), "friendchat_error.log")


def log_text(text: str, tag: str = "오류"):
    """한 건을 파일에 덧붙임. 로그를 남기다 또 터지는 일이 없게 전부 감싼다."""
    try:
        path = error_log_path()
        with _lock:
            try:
                if os.path.exists(path) and os.path.getsize(path) > MAX_BYTES:
                    os.remove(path)
            except OSError:
                pass
            stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open(path, "a", encoding="utf-8") as fp:
                fp.write(f"\n===== {stamp} [{tag}] v{_version()} =====\n{text}\n")
    except Exception:  # noqa: BLE001 - 기록 실패가 앱을 죽이면 안 됨
        pass


def _version() -> str:
    try:
        from version import APP_VERSION
        return APP_VERSION
    except Exception:  # noqa: BLE001
        return "?"


def _exception_text(exc_type, exc, tb) -> str:
    return "".join(traceback.format_exception(exc_type, exc, tb))


def install():
    """앱 시작 때 한 번 호출. 이후 잡히지 않은 예외는 전부 파일에 남는다."""
    global _installed
    if _installed:
        return
    _installed = True

    previous = sys.excepthook

    def hook(exc_type, exc, tb):
        log_text(_exception_text(exc_type, exc, tb))
        # 원래 동작(stderr 출력)도 유지 - 소스로 실행할 때는 콘솔에서 바로 보이는 게 편함
        previous(exc_type, exc, tb)

    sys.excepthook = hook

    def thread_hook(args):
        log_text(_exception_text(args.exc_type, args.exc_value, args.exc_traceback),
                 tag=f"스레드 {args.thread.name if args.thread else '?'}")

    threading.excepthook = thread_hook
