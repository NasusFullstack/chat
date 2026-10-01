"""이모티콘 창에서 **작은 빈 창이 깜빡이는** 것을 잡는다.

## 무슨 일이 있었나
"전체 버튼을 누르면 작은 공백창이 떴다 사라졌다 반복한다"는 제보가 있었다.

**아직 재현하지 못했다.** 실제 화면으로 재보니 떠돌이 창은 안 생기고 창 높이만
606 -> 704로 바뀐다(즐겨찾기 2줄 -> 전체 4줄). 제보한 환경에서만 나는 무언가가 있다.

그래서 이 검사는 "고쳤다"가 아니라 **"이 종류의 사고를 다시는 안 내겠다"**는 그물이다.
칸을 지우고 다시 그리는 길에서 화면에 뜨는 창이 늘어나면 실패한다.

지우는 쪽은 `widget.hide()`를 먼저 하게 해뒀다. Qt가 부모를 뗄 때 알아서 숨기기는
하지만, 그건 문서를 믿는 것이고 숨기고 떼면 믿을 필요가 없다.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, REPO)

from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])

import emoji_store  # noqa: E402
import gui_client as g  # noqa: E402
import relay  # noqa: E402
from gui.emoji_picker import EmojiPicker  # noqa: E402

app.setStyleSheet(g.STYLE_SHEET)

checks = []


def check(name, ok, detail=""):
    checks.append((name, ok, detail))


def windows():
    """지금 **화면에 보이는** 최상위 창.

    숨은 것까지 세면 안 된다. Qt는 부모를 뗀 위젯을 최상위로 분류하지만 동시에
    숨기기도 하므로(문서에 명시), 숨은 것을 세면 멀쩡한 코드도 실패한다.
    깜빡임은 '잠깐 보인' 것이므로 보이는 것만 센다.
    """
    return {w for w in app.topLevelWidgets() if w.isVisible()}


ITEMS = [{"url": f"{relay.SERVER}/files/{i:024x}/e{i}.png", "name": f"짤{i}"}
         for i in range(12)]


class _NoFetcher:
    """답을 안 주는 받아오기 담당 - 그림이 없어도 칸은 만들어진다."""

    def fetch(self, url, callback, limit=None):
        pass


# 즐겨찾기를 채워둔다(창을 열면 바로 칸이 그려지게)
real_store = emoji_store.EMOJI_STORE_FILE
emoji_store.EMOJI_STORE_FILE = os.path.join(
    os.environ.get("TEMP", "."), "test_flash_emojis.json")
if os.path.exists(emoji_store.EMOJI_STORE_FILE):
    os.remove(emoji_store.EMOJI_STORE_FILE)
for entry in ITEMS[:6]:
    emoji_store.add_emoji(entry["url"], entry["name"])

try:
    before = windows()
    picker = EmojiPicker(fetcher=_NoFetcher(), group="a" * 24)
    picker.show()
    for _ in range(4):
        app.processEvents()

    opened = windows() - before - {picker}
    check(f"창을 열 때 떠돌이 창이 안 생긴다({[w.objectName() or type(w).__name__ for w in opened]})",
          not opened, [type(w).__name__ for w in opened])

    # 여기가 제보된 자리 - 칸을 지우고 다시 그린다
    steady = windows()
    picker._shared._items = list(ITEMS)
    picker._switch(True)
    picker._on_shared(ITEMS)
    strays = windows() - steady
    check(f"'전체'로 넘어갈 때 떠돌이 창이 안 생긴다({len(strays)}개)",
          not strays, [type(w).__name__ for w in strays])

    # 여러 번 오가도 마찬가지여야 한다(깜빡임은 반복해서 났다)
    steady = windows()
    for _ in range(5):
        picker._switch(False)
        picker._switch(True)
        picker._on_shared(ITEMS)
    for _ in range(4):
        app.processEvents()
    strays = windows() - steady
    check(f"여러 번 오가도 안 생긴다({len(strays)}개)", not strays,
          [type(w).__name__ for w in strays])

    # 페이지를 넘길 때도 같은 길을 탄다
    steady = windows()
    picker._go(1)
    picker._go(0)
    strays = windows() - steady
    check(f"페이지를 넘길 때도 안 생긴다({len(strays)}개)", not strays,
          [type(w).__name__ for w in strays])

    # 이 검사가 진짜로 잡는지 확인한다 - 안 그러면 "통과"가 아무 뜻이 없다.
    # (참고: setParent(None) 으로는 안 잡힌다. Qt가 그때 위젯을 숨기기 때문이고,
    #  그래서 그게 제보된 깜빡임의 원인이 **아니라는** 것도 여기서 확인된다)
    from PySide6.QtWidgets import QLabel

    steady = windows()
    stray = QLabel("떠돌이")
    stray.show()
    app.processEvents()
    caught = windows() - steady
    check("검사가 실제로 떠돌이 창을 잡아낸다(헛돌지 않는지 확인)",
          bool(caught), [type(w).__name__ for w in caught])
    stray.close()
    stray.deleteLater()

    source = open(os.path.join(REPO, "gui/emoji_picker.py"), encoding="utf-8").read()
    render = source.split("def _render", 1)[1].split("def ", 1)[0]
    check("부모를 떼기 전에 숨긴다", "widget.hide()" in render, render[:200])

    picker.deleteLater()
finally:
    if os.path.exists(emoji_store.EMOJI_STORE_FILE):
        os.remove(emoji_store.EMOJI_STORE_FILE)
    emoji_store.EMOJI_STORE_FILE = real_store

print("=== 검증 결과 (이모티콘 창 깜빡임) ===")
all_ok = True
for name, ok, *detail in checks:
    extra = f"  <- {detail[0]}" if detail and detail[0] and not ok else ""
    print(f"[{'OK' if ok else 'FAIL'}] {name}{extra}")
    all_ok = all_ok and ok
print(f"\n검사 {len(checks)}개")
print("전체 통과:", all_ok)
sys.exit(0 if all_ok else 1)
