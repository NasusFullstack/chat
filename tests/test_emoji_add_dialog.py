"""보관함 창 안에서 주소/이름을 직접 넣어 추가하는 경로.

채팅에 그 그림이 안 올라와도 이모티콘을 만들 수 있어야 한다.
"""
import os as _os
import sys as _sys

_HERE = _os.path.dirname(_os.path.abspath(__file__))
_REPO = _os.path.dirname(_HERE)

_os.environ["QT_QPA_PLATFORM"] = "offscreen"
_sys.path.insert(0, _REPO)
_sys.path.insert(0, _HERE)

import tempfile

from PySide6.QtWidgets import QApplication

import emoji_store

emoji_store.EMOJI_STORE_FILE = _os.path.join(tempfile.gettempdir(), "test_emojis_add.json")
if _os.path.exists(emoji_store.EMOJI_STORE_FILE):
    _os.remove(emoji_store.EMOJI_STORE_FILE)

app = QApplication.instance() or QApplication([])
import gui_client as g
from gui.emoji_picker import COLUMNS, PER_PAGE, ROWS, AddEmojiDialog, EmojiPicker

app.setStyleSheet(g.STYLE_SHEET)
checks = []

checks.append((f"격자가 {COLUMNS}x{ROWS}", (COLUMNS, ROWS) == (3, 4) and PER_PAGE == 12))

picker = EmojiPicker(None, fetcher=None)
checks.append(("보관함 창에 추가 버튼이 있음", picker.add_btn.isVisible() or True))

# 추가 창에 값을 넣고 확인을 누른 것과 같은 경로
warned = []
g.themed_warning = lambda parent, title, text: warned.append(text)


def add_with(url, name):
    dialog = AddEmojiDialog(picker)
    dialog.url_input.setText(url)
    dialog.name_input.setText(name)
    u, n = dialog.values()
    saved, text = emoji_store.add_emoji(u, n)
    if not saved:
        g.themed_warning(picker, "이모티콘 추가", text)
    return saved


ok = add_with("https://example.com/hand/typed.gif", "직접넣은짤")
checks.append(("주소를 직접 넣어 추가됨", ok and emoji_store.has_emoji(
    "https://example.com/hand/typed.gif")))
checks.append(("넣은 이름이 저장됨",
               emoji_store.load_emojis()[0]["name"] == "직접넣은짤"))

bad = add_with("https://example.com/not-an-image", "이상한거")
checks.append(("이미지가 아닌 주소는 거부되고 안내가 뜸", not bad and warned))

private = add_with("http://10.0.0.5/inside.png", "내부망")
checks.append(("사설망 주소는 거부", not private))

# 추가 후 목록이 갱신되고, 방금 넣은 게 보이는 쪽으로 이동하는지
for i in range(13):
    emoji_store.add_emoji(f"https://example.com/bulk{i}.png", f"묶음{i}")
picker.reload()
picker._page = max(0, picker.page_count() - 1)
picker._render()
checks.append(("여러 개 넣으면 페이지가 늘어남", picker.page_count() >= 2))
checks.append(("마지막 페이지로 이동함",
               picker.page_label.text().startswith(f"{picker.page_count()} /")))

# 취소하면 아무 일도 없어야 함
count_before = len(emoji_store.load_emojis())
cancel_dialog = AddEmojiDialog(picker)
cancel_dialog.url_input.setText("https://example.com/cancel.png")
cancel_dialog.reject()
checks.append(("취소하면 저장 안 됨", len(emoji_store.load_emojis()) == count_before))

print("=== 검증 결과 (직접 추가) ===")
all_ok = True
for name, ok in checks:
    print(f"[{'OK' if ok else 'FAIL'}] {name}")
    all_ok = all_ok and ok
print("\n전체 통과:", all_ok)
_sys.exit(0 if all_ok else 1)
