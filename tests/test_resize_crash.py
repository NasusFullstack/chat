"""창 가로를 줄일 때 앱이 죽지 않는가.

실제 신고(2026-09-29): "채널 목록이 열려 있을 때 창 가로를 줄이면 프로그램이 터져."
실측 결과 **스택 오버플로**였다(파이썬 예외가 아니라 프로세스가 그냥 사라진다).

원인: v2.2.5에서 `_ChatLogContent.minimumSizeHint()`가 '마지막 실측값'을 답하게 했다.
Qt는 크기 힌트가 한 배치 안에서 변하지 않는다고 보는데, 그 값은 배치의 **결과**로 바뀐다.
배치 -> 힌트 변화 -> 다시 배치가 끝없이 돌다 Qt 내부(C++) 재귀로 스택이 넘쳤다.

크래시 자체는 폭이 경계에 딱 걸릴 때만 나서(실측: 같은 스크립트 3번 중 1번) 검사로
삼기에 불안정하다. 그래서 여기서는 **크래시를 만든 성질**을 본다:

  크기 힌트는 배치를 돌려도 같은 값이어야 한다.

이건 매번 결정적으로 확인되고, 위 구조로 되돌리면 반드시 걸린다.
마지막에 실제로 창을 줄이는 스트레스도 따로 돌린다(죽으면 프로세스가 사라지므로
별도 프로세스로 띄워 종료 코드를 본다).
"""
import os as _os
import sys as _sys

_HERE = _os.path.dirname(_os.path.abspath(__file__))
_REPO = _os.path.dirname(_HERE)

_os.environ["QT_QPA_PLATFORM"] = "offscreen"
_sys.path.insert(0, _REPO)

import subprocess  # noqa: E402
import time  # noqa: E402

from PySide6.QtCore import QBuffer, QTimer  # noqa: E402
from PySide6.QtGui import QPixmap  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])
import gui_client as g  # noqa: E402
from chat_core.commands import EMOJI_CLOSE, EMOJI_OPEN  # noqa: E402
from gui.components.message_log import ChannelLogView  # noqa: E402
from gui.emoji_view import EmojiRow  # noqa: E402

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
    SIZES = ((600, 400), (200, 200), (800, 200), (300, 900), (64, 64))

    def __init__(self):
        self.count = 0

    def fetch(self, url, on_done, limit=0):
        width, height = self.SIZES[self.count % len(self.SIZES)]
        self.count += 1
        data = png(width, height)
        QTimer.singleShot(30 + 40 * (self.count % 4), lambda: on_done(data))


def pump(seconds):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.003)


emoji = "".join(f"{EMOJI_OPEN}https://example.com/e{i}.png{EMOJI_CLOSE}" for i in range(6))
view = ChannelLogView("#t", image_fetcher=LateFetcher())
view.resize(700, 500)
view.show()
view.set_container_width(700)
pump(0.1)
for _ in range(4):
    view.append_message("Mong", emoji, False, time.time(), QPixmap(28, 28))
    pump(0.03)
pump(1.2)

content = view.widget()

# ---------- 1) 크기 힌트가 배치를 돌려도 안 변하는가(크래시의 뿌리) ----------
before = (content.minimumSizeHint(), content.sizeHint())
content.measured_height()          # 배치를 한 번 확정시킨다
after = (content.minimumSizeHint(), content.sizeHint())
check(f"재도 최소 크기가 그대로({before[0].height()} -> {after[0].height()})",
      before[0] == after[0], (before[0], after[0]))
check(f"재도 자연 크기가 그대로({before[1].height()} -> {after[1].height()})",
      before[1] == after[1], (before[1], after[1]))

view.sync_content_height()
pump(0.1)
again = (content.minimumSizeHint(), content.sizeHint())
check(f"높이를 맞춘 뒤에도 그대로({after[0].height()} -> {again[0].height()})",
      after[0] == again[0], (after[0], again[0]))

# ---------- 2) 이모티콘 칸이 자기 크기를 정직하게 답하는가 ----------
# 여기가 부풀면 그 값이 메시지 -> 대화 목록으로 전파되어, 그걸 위에서 덮으려다
# 크래시가 났다. 힌트는 덮는 게 아니라 만드는 쪽에서 맞춰야 한다
for index, row in enumerate(view.findChildren(EmojiRow)):
    needed = row.layout().heightForWidth(row.width())
    hinted = row.sizeHint().height()
    # sizeHint는 '한 줄에 다 늘어놓았을 때'의 자연 크기라 실제보다 작을 수는 있다.
    # 실제보다 **크면** 그만큼이 최소 크기로 전파되어 위쪽에서 못 줄인다(=빈 공간)
    check(f"이모티콘 {index}: 실제보다 큰 높이를 요구하지 않는다"
          f"(요구 {hinted} <= 필요 {needed})",
          needed > 0 and hinted <= needed, (hinted, needed))
    check(f"이모티콘 {index}: 눌려서 잘리지 않는다(실제 {row.height()} >= 필요 {needed})",
          row.height() >= needed - 2, (row.height(), needed))

# ---------- 3) 실제로 창을 줄여도 살아남는가 ----------
# 스택 오버플로는 예외가 아니라 프로세스를 죽이므로 따로 띄워 종료 코드를 본다
STRESS = r'''
import faulthandler, os, sys, time
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, %(repo)r)
faulthandler.enable()
from PySide6.QtCore import QBuffer, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication
app = QApplication.instance() or QApplication([])
import gui_client as g
from chat_core.commands import EMOJI_OPEN, EMOJI_CLOSE
app.setStyleSheet(g.STYLE_SHEET)

def png(w, h):
    pm = QPixmap(w, h); pm.fill()
    buf = QBuffer(); buf.open(QBuffer.OpenModeFlag.WriteOnly); pm.save(buf, "PNG")
    return bytes(buf.data())

class F:
    SIZES = ((600, 400), (200, 200), (800, 200), (300, 900), (64, 64))
    n = 0
    def fetch(self, url, on_done, limit=0):
        w, h = self.SIZES[self.n %% len(self.SIZES)]; self.n += 1
        QTimer.singleShot(20 + 30 * (self.n %% 4), lambda: on_done(png(w, h)))

def pump(sec):
    end = time.time() + sec
    while time.time() < end:
        app.processEvents(); time.sleep(0.002)

win = g.MainWindow(); win.resize(1100, 700); win.show()
chat = win.chat_page; chat._image_fetcher = F()
chat.add_channel("#room"); chat._log_views["#room"]._image_fetcher = chat._image_fetcher
win.show_page(chat); pump(0.5)
emoji = "".join(EMOJI_OPEN + "https://example.com/e%%d.png" %% i + EMOJI_CLOSE for i in range(6))
for i in range(6):
    chat.append_message("#room", "Ming", "긴 대화 " + "가나다라마바사아자차카타파하" * 12,
                        False, time.time(), preview=False)
    chat.append_message("#room", "Gil", emoji, False, time.time())
    chat.append_message("#room", "Gil", "https://example.com/pic%%d.png" %% i, False, time.time())
pump(2.0)
bar = chat.channel_sidebar
bar.set_collapsed(False); pump(0.4)
for width in range(1100, 320, -1):
    win.resize(width, 700); pump(0.008)
for i in range(10):
    bar.set_collapsed(i %% 2 == 0); pump(0.1)
    for width in range(900, 380, -3):
        win.resize(width, 700); pump(0.006)
print("ok")
''' % {"repo": _REPO}

script = _os.path.join(_os.environ.get("TEMP", _HERE), "_chup_resize_stress.py")
with open(script, "w", encoding="utf-8") as fp:
    fp.write(STRESS)
result = subprocess.run([_sys.executable, script], capture_output=True, text=True, timeout=900)
_os.remove(script)
check(f"창을 끝까지 줄여도 앱이 안 죽는다(종료 코드 {result.returncode})",
      result.returncode == 0,
      (result.returncode, (result.stdout or "")[-200:], (result.stderr or "")[-400:]))

print("=== 검증 결과 (창 크기 조절 중 크래시) ===")
all_ok = True
for name, ok, *detail in checks:
    extra = f"  <- {detail[0]}" if detail and detail[0] and not ok else ""
    print(f"[{'OK' if ok else 'FAIL'}] {name}{extra}")
    all_ok = all_ok and ok
print("\n전체 통과:", all_ok)
_sys.exit(0 if all_ok else 1)
