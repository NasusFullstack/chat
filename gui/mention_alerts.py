"""@호출 알림 (작업표시줄 깜빡임 + 창 흔들림).

_flash_taskbar_icon/_shake_window는 테스트가 g._flash_taskbar_icon = fake처럼 직접
몽키패치하는 대상임 - 이 둘을 호출하는 다른 모듈(pages.py)은 반드시 `import gui_client`
후 `gui_client._flash_taskbar_icon(...)`처럼 모듈 속성으로 조회해서 호출해야 몽키패치가
실제로 먹힘. 자세한 이유는 gui_client.py 상단 주석 참고.
"""
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QWidget

from gui.theme import IS_WINDOWS

if IS_WINDOWS:
    import ctypes  # 작업표시줄 아이콘 그룹핑(AppUserModelID) + @호출 시 작업표시줄 깜빡임에 사용

    class _FLASHWINFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", ctypes.c_uint),
            ("hwnd", ctypes.c_void_p),
            ("dwFlags", ctypes.c_uint),
            ("uCount", ctypes.c_uint),
            ("dwTimeout", ctypes.c_uint),
        ]

    _FLASHW_TRAY = 0x00000002


def _flash_taskbar_icon(window: QWidget, count: int = 6):
    """@호출을 받으면 작업표시줄 아이콘을 깜빡임. Windows 전용 API라 다른 OS에서는 아무것도 안 함"""
    if not IS_WINDOWS:
        return
    info = _FLASHWINFO(
        cbSize=ctypes.sizeof(_FLASHWINFO),
        hwnd=int(window.winId()),
        dwFlags=_FLASHW_TRAY,
        uCount=count,
        dwTimeout=0,
    )
    ctypes.windll.user32.FlashWindowEx(ctypes.byref(info))


def _shake_window(window: QWidget, duration_ms: int = 1000, amplitude: int = 6, interval_ms: int = 40):
    """@호출을 받으면 채팅창 전체를 1초간 좌우로 흔듦"""
    if window.isMinimized():
        return  # 최소화 상태면 흔들어도 안 보이므로 생략 - 작업표시줄 깜빡임만으로 충분
    origin = window.pos()
    steps = max(1, duration_ms // interval_ms)
    state = {"i": 0}
    timer = QTimer(window)

    def tick():
        state["i"] += 1
        if state["i"] > steps:
            window.move(origin)
            timer.stop()
            timer.deleteLater()
            return
        dx = amplitude if state["i"] % 2 == 0 else -amplitude
        window.move(origin.x() + dx, origin.y())

    timer.timeout.connect(tick)
    timer.start(interval_ms)
