"""화면을 그대로 캡처해서 리팩토링 전후가 **픽셀 단위로 같은지** 비교하는 도구.

리팩토링은 "겉모습이 하나도 안 바뀌어야" 성공이다. 그런데 기능 테스트는 배치가 몇 px
틀어지거나 여백이 달라진 것을 못 잡는다. 그래서 주요 화면을 그림으로 떠서 비교한다.

    python tests/ui_snapshot.py save 기준이름     # 지금 화면을 기준으로 저장
    python tests/ui_snapshot.py check 기준이름    # 지금 화면이 그 기준과 같은지 비교

저장 위치는 이 파일 옆의 _ui_snapshots/(git에는 안 올라감 - tests/*.png 무시 규칙).
"""
import os as _os
import sys as _sys

_HERE = _os.path.dirname(_os.path.abspath(__file__))
_REPO = _os.path.dirname(_HERE)

_os.environ["QT_QPA_PLATFORM"] = "offscreen"
_sys.path.insert(0, _REPO)
_sys.path.insert(0, _HERE)

import tempfile

from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

import emoji_store

# 보관함은 임시 파일로 돌려서 사람마다 다른 내 보관함이 그림에 안 들어가게 함
emoji_store.EMOJI_STORE_FILE = _os.path.join(tempfile.gettempdir(), "ui_snapshot_emojis.json")

SNAPSHOT_DIR = _os.path.join(_HERE, "_ui_snapshots")
WINDOW_SIZE = (980, 660)


def _build_screens(app):
    """비교할 화면들을 만들어 {이름: 위젯}으로 돌려줌.

    시간/네트워크처럼 실행할 때마다 달라지는 것은 넣지 않는다(그림이 매번 달라지면
    비교 자체가 무의미해짐). 메시지 시각도 고정값을 쓴다.
    """
    import gui_client as g
    from fixtures import sample_history

    app.setStyleSheet(g.STYLE_SHEET)
    screens = {}

    login = g.LoginPage(on_submit=lambda mode: None, on_cancel=lambda: None)
    login.resize(*WINDOW_SIZE)
    screens["login"] = login

    channel = g.ChannelPage(on_submit=lambda a: None, on_back=lambda: None)
    channel.resize(*WINDOW_SIZE)
    screens["channel"] = channel

    chat = g.ChatPage(on_send=lambda c, t: None, on_add_channel=lambda: None,
                      on_leave_channel=lambda c: None, on_set_avatar=lambda: None)
    chat.resize(*WINDOW_SIZE)
    chat.show()
    app.processEvents()
    chat.my_id = "Mong"
    for name in ("#pdlab", "#general", "#dev"):
        chat.add_channel(name)
    chat.set_active_channel("#pdlab")
    chat.update_userlist("#pdlab", ["Mong", "Ming", "hjsong", "MangMang2"])
    chat.load_history("#pdlab", sample_history(24))
    chat.append_message("#pdlab", "hjsong", "리팩토링 전후 비교용 메시지", False, 1_700_000_000)
    chat.append_system("#pdlab", "누군가 입장했습니다.")
    for _ in range(8):
        app.processEvents()
    screens["chat"] = chat
    return screens


def _capture(app) -> dict:
    images = {}
    for name, widget in _build_screens(app).items():
        widget.resize(*WINDOW_SIZE)
        for _ in range(6):
            app.processEvents()
        images[name] = widget.grab().toImage()
    return images


def _diff(a: QImage, b: QImage) -> tuple[int, int]:
    """(다른 픽셀 수, 전체 픽셀 수). 크기가 다르면 전부 다른 것으로 침."""
    if a.size() != b.size():
        return -1, a.width() * a.height()
    different = 0
    for y in range(a.height()):
        for x in range(a.width()):
            if a.pixel(x, y) != b.pixel(x, y):
                different += 1
    return different, a.width() * a.height()


def main():
    if len(_sys.argv) < 3:
        print(__doc__)
        return 2
    mode, label = _sys.argv[1], _sys.argv[2]
    folder = _os.path.join(SNAPSHOT_DIR, label)
    app = QApplication.instance() or QApplication([])
    images = _capture(app)

    if mode == "save":
        _os.makedirs(folder, exist_ok=True)
        for name, image in images.items():
            image.save(_os.path.join(folder, f"{name}.png"))
        print(f"기준 저장: {folder} ({', '.join(images)})")
        return 0

    if mode != "check":
        print(__doc__)
        return 2

    if not _os.path.isdir(folder):
        print(f"기준이 없음: {folder} (먼저 save 하세요)")
        return 2

    worst = 0
    for name, image in images.items():
        path = _os.path.join(folder, f"{name}.png")
        base = QImage(path)
        if base.isNull():
            print(f"[없음] {name}")
            worst = max(worst, 1)
            continue
        different, total = _diff(base, image)
        if different < 0:
            print(f"[FAIL] {name}: 크기가 다름 {base.size().toTuple()} -> {image.size().toTuple()}")
            worst = max(worst, 2)
            continue
        ratio = different / total * 100 if total else 0
        mark = "OK  " if different == 0 else "다름"
        print(f"[{mark}] {name}: 다른 픽셀 {different}/{total} ({ratio:.3f}%)")
        if different:
            image.save(_os.path.join(folder, f"{name}__현재.png"))
            worst = max(worst, 2)
    print("\n화면이 전과 완전히 같음" if worst == 0 else "\n화면이 달라졌음 - 위 목록 확인")
    return worst


if __name__ == "__main__":
    _sys.exit(main())
