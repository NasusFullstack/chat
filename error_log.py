r"""예상 못 한 오류를 파일로 남긴다.

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
import faulthandler
import os
import sys

import app_paths
import tempfile
import threading
import traceback

NL = chr(10)
MAX_BYTES = 512 * 1024  # 이만큼 넘으면 새로 시작 - 무한정 커지지 않게
_installed = False
# 죽는 순간에는 파일을 새로 못 여니 미리 열어둔 손잡이를 붙잡고 있는다
_crash_file = None
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


def _install_crash_dump():
    """파이썬 예외가 아니라 **프로세스가 통째로 죽는 경우**도 남긴다.

    "앱이 갑자기 멈추더니 꺼졌다"는 신고는 위의 excepthook으로는 아무 것도 안 남는다.
    파이썬 예외가 아니라 C 수준에서 죽는 것이라(스택 오버플로, 접근 위반 등) 인터프리터가
    끼어들 틈 없이 프로세스가 사라지기 때문이다. 실제로 예전에 무한 재귀로 스택이 넘쳐
    죽은 적이 있는데, 그때도 기록이 한 줄도 없어서 원인을 찾는 데 한참 걸렸다.

    faulthandler는 그 순간 파이썬 호출 스택을 파일에 직접 찍어준다 - 어디서 무한히
    돌다 죽었는지가 그대로 남는다. 파일 손잡이를 계속 열어둬야 하므로(죽는 순간에는
    새로 열 수 없다) 모듈 수준에서 붙잡아 둔다.
    """
    global _crash_file
    try:
        _crash_file = open(error_log_path(), "a", encoding="utf-8")
        stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        _crash_file.write(f"{NL}===== {stamp} [실행 시작] v{_version()} ====={NL}")
        _crash_file.flush()
        faulthandler.enable(file=_crash_file, all_threads=True)
    except Exception:  # noqa: BLE001 - 기록 장치 때문에 앱이 안 켜지면 본말전도
        pass


# UI가 이만큼 멈춰 있으면 "그때 어디에 있었는지"를 기록한다. 사람이 체감하는 멈춤보다
# 넉넉히 잡는다 - 큰 그림을 그리거나 기록을 불러오는 순간에도 잠깐씩은 멈추므로
FREEZE_SECONDS = 20


def arm_freeze_watchdog():
    """멈춤 감시를 다시 걸어둔다(살아 있으면 계속 갱신되므로 안 찍힌다).

    화면이 멈추면 이 갱신도 멈추고, 그러면 감시 장치가 시간이 넘었다고 판단해서
    **그 순간 모든 스레드의 파이썬 스택**을 기록에 남긴다. "멈추더니 꺼진다"는 신고는
    이 기록이 없으면 손을 댈 수가 없다 - 어디서 멈췄는지가 유일한 단서다.
    """
    if _crash_file is None:
        return
    try:
        faulthandler.cancel_dump_traceback_later()
        faulthandler.dump_traceback_later(FREEZE_SECONDS, repeat=False,
                                          file=_crash_file, exit=False)
    except Exception:  # noqa: BLE001
        pass


def stop_freeze_watchdog():
    try:
        faulthandler.cancel_dump_traceback_later()
    except Exception:  # noqa: BLE001
        pass


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
    _install_crash_dump()

    def thread_hook(args):
        log_text(_exception_text(args.exc_type, args.exc_value, args.exc_traceback),
                 tag=f"스레드 {args.thread.name if args.thread else '?'}")

    threading.excepthook = thread_hook
