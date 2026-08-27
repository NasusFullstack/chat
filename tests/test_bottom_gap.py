"""채팅 맨 아래에 빈 공간이 남지 않는가 - 늦게 도착하는 내용까지 포함해서.

실제 신고(2026-08-27): "이미지를 여러 개 넣어서 그런가 채팅창 아래 공백이 생겼어."

재보니 **이모티콘을 여러 개 넣은 메시지**에서만 났다(링크 미리보기는 멀쩡했다).
원인은 `_ChatLogContent`가 자기 **최소 크기를 답하지 않은** 것이었다. 그러면 Qt가
대신 레이아웃의 `totalMinimumSize()`를 쓰는데, 그 값은 '창을 최대한 좁혔을 때'를
가정하고 계산된다 - 글자는 줄이 늘고 이모티콘은 한 줄에 하나씩 내려가므로 실제보다
훨씬 크게 나온다. 스크롤 영역(widgetResizable)은 안쪽 위젯을 그 최소치 아래로는
못 줄이므로, 실측으로 맞춰놔도 곧바로 되돌려졌다.

실측(이모티콘 6개 x 4줄, 폭 700): 실제 필요 3039px인데 최소치 4223px -> 공백 1184px.

이 검사는 **공식이 아니라 결과**를 본다(CLAUDE.md 11-5) - "내용 위젯 높이"와 "마지막
위젯의 아랫끝"이 같은지만 확인하므로, 나중에 계산 방식이 바뀌어도 그대로 유효하다.
"""
import os as _os
import sys as _sys

_HERE = _os.path.dirname(_os.path.abspath(__file__))
_REPO = _os.path.dirname(_HERE)

_os.environ["QT_QPA_PLATFORM"] = "offscreen"
_sys.path.insert(0, _REPO)

import time  # noqa: E402

from PySide6.QtCore import QBuffer, QTimer  # noqa: E402
from PySide6.QtGui import QPixmap  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])
import gui_client as g  # noqa: E402
from chat_core.commands import EMOJI_CLOSE, EMOJI_OPEN  # noqa: E402
from gui.components.message_log import ChannelLogView  # noqa: E402

app.setStyleSheet(g.STYLE_SHEET)

checks = []


def check(name, ok, detail=""):
    checks.append((name, ok, detail))


def png(width, height):
    pixmap = QPixmap(width, height)
    pixmap.fill()
    buffer = QBuffer()
    buffer.open(QBuffer.OpenModeFlag.WriteOnly)
    pixmap.save(buffer, "PNG")
    return bytes(buffer.data())


class LateFetcher:
    """네트워크처럼 **나중에** 답한다. 크기도 제각각이라 자리를 잡아둔 값과 달라진다.

    도착 전 자리(192x192)와 실제 크기가 같으면 이 버그가 안 난다 - 그래서 세로로 긴
    그림과 가로로 긴 그림을 섞는다.
    """

    SIZES = ((600, 400), (200, 200), (800, 200), (300, 900), (64, 64))

    def __init__(self):
        self.count = 0

    def fetch(self, url, on_done, limit=0):
        width, height = self.SIZES[self.count % len(self.SIZES)]
        self.count += 1
        data = png(width, height)
        QTimer.singleShot(40 + 50 * (self.count % 4), lambda: on_done(data))


def pump(seconds):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.003)


def bottom_gap(view):
    """내용 위젯이 실제 내용보다 얼마나 더 큰가(= 맨 아래 빈 공간)."""
    content = view.widget()
    layout = content.layout()
    bottom = 0
    for i in range(layout.count()):
        widget = layout.itemAt(i).widget()
        if widget is not None and not widget.isHidden():
            bottom = max(bottom, widget.geometry().bottom() + 1)
    real = bottom + layout.contentsMargins().bottom() if bottom else 0
    # 내용이 화면보다 짧으면 화면 높이만큼 채우는 게 정상(배경이 끊겨 보이지 않게)
    return max(0, content.height() - max(real, view.viewport().height()))


def build(message_text, rows, width=700):
    view = ChannelLogView("#t", image_fetcher=LateFetcher())
    view.resize(width, 500)
    view.show()
    view.set_container_width(width)
    pump(0.1)
    for _ in range(rows):
        view.append_message("Mong", message_text, False, time.time(), QPixmap(28, 28))
        pump(0.03)
    pump(1.2)                       # 그림들이 다 도착할 시간
    return view


def emoji_message(count):
    return "".join(f"{EMOJI_OPEN}https://example.com/e{i}.png{EMOJI_CLOSE}"
                   for i in range(count))


# ---------- 1) 이모티콘(신고가 들어온 경우) ----------
for label, per_message, rows, width in (
    ("이모티콘 1개 x 4줄", 1, 4, 700),
    ("이모티콘 3개 x 4줄", 3, 4, 700),
    ("이모티콘 6개 x 4줄", 6, 4, 700),
    ("이모티콘 6개 x 4줄(좁은 창)", 6, 4, 500),
    ("이모티콘 10개 x 2줄", 10, 2, 700),
):
    view = build(emoji_message(per_message), rows, width)
    gap = bottom_gap(view)
    check(f"{label}: 아래 빈 공간 없음({gap}px)", gap <= 4, gap)
    view.deleteLater()
    pump(0.05)

# ---------- 2) 링크 미리보기(예전에 고쳐둔 경로 - 같이 지킨다) ----------
LONG_URL = ("https://encrypted-tbn0.gstatic.com/images?"
            "q=tbn:ANd9GcQ6-edgBcVcH2OYfU7KckpjTCDxfveJrdPUT4jnxXTQHA&s=10")
for label, rows, width in (("그림 링크 6줄", 6, 700), ("그림 링크 12줄", 12, 700)):
    view = build(LONG_URL, rows, width)
    gap = bottom_gap(view)
    check(f"{label}: 아래 빈 공간 없음({gap}px)", gap <= 4, gap)
    view.deleteLater()
    pump(0.05)

# ---------- 3) 글만 있는 평범한 대화도 그대로 ----------
view = ChannelLogView("#t")
view.resize(700, 500)
view.show()
view.set_container_width(700)
for i in range(30):
    view.append_message("Ming", f"평범한 대화 {i}번째 줄입니다", False, time.time(),
                        QPixmap(28, 28), preview=False)
pump(0.4)
gap = bottom_gap(view)
check(f"글만 있는 대화: 아래 빈 공간 없음({gap}px)", gap <= 4, gap)

# 대화가 화면보다 짧을 때는 화면을 채우는 게 정상(빈 화면에 배경이 끊기면 안 됨)
short = ChannelLogView("#s")
short.resize(700, 500)
short.show()
short.set_container_width(700)
short.append_message("Ming", "한 줄", False, time.time(), QPixmap(28, 28), preview=False)
pump(0.2)
check(f"대화가 짧으면 화면 높이만큼은 채운다({short.widget().height()}"
      f" >= {short.viewport().height()})",
      short.widget().height() >= short.viewport().height(),
      (short.widget().height(), short.viewport().height()))

print("=== 검증 결과 (채팅 맨 아래 빈 공간) ===")
all_ok = True
for name, ok, *detail in checks:
    extra = f"  <- {detail[0]}" if detail and detail[0] and not ok else ""
    print(f"[{'OK' if ok else 'FAIL'}] {name}{extra}")
    all_ok = all_ok and ok
print("\n전체 통과:", all_ok)
_sys.exit(0 if all_ok else 1)
