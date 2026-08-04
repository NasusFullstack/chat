"""이모티콘 기능 - 저장/전송형식/렌더링/보관함 창/우클릭 저장.

특히 확인하는 것: 이모티콘이 붙어도 **채팅 아래에 빈 공간이 생기지 않아야 한다**.
그림이 나중에 도착하는 구조라 높이 계산이 어긋나기 쉬운 자리다(예전에 같은 뿌리의
사고가 두 번 났음 - CLAUDE.md 참고).
"""
import os as _os
import sys as _sys

_HERE = _os.path.dirname(_os.path.abspath(__file__))
_REPO = _os.path.dirname(_HERE)

_os.environ["QT_QPA_PLATFORM"] = "offscreen"
_sys.path.insert(0, _REPO)
_sys.path.insert(0, _HERE)

import json
import tempfile

from PySide6.QtWidgets import QApplication

import emoji_store
from chat_core.commands import EMOJI_OPEN, format_emoji, split_emoji_parts
from fixtures import sample_history

# 보관함 파일은 임시 위치로 돌려서 실제 내 보관함을 건드리지 않음
emoji_store.EMOJI_STORE_FILE = _os.path.join(tempfile.gettempdir(), "test_emojis.json")
if _os.path.exists(emoji_store.EMOJI_STORE_FILE):
    _os.remove(emoji_store.EMOJI_STORE_FILE)

app = QApplication.instance() or QApplication([])
import gui_client as g
from gui.emoji_picker import PER_PAGE, EmojiPicker
from gui.emoji_view import EMOJI_PX, EmojiRow

app.setStyleSheet(g.STYLE_SHEET)
checks = []

GIF = "https://example.com/emoji/dog.gif"
PNG = "https://example.com/emoji/cat.png"
BAD_LOCAL = "http://192.168.0.1/router.png"
NOT_IMAGE = "https://example.com/news/article"

# ---------- 1) 보관함 저장 ----------
ok, _ = emoji_store.add_emoji(GIF, "멍멍이")
checks.append(("이미지 주소를 보관함에 저장", ok))
ok2, _ = emoji_store.add_emoji(GIF, "또멍멍")
checks.append(("같은 주소는 두 번 안 들어감", not ok2))
bad, _ = emoji_store.add_emoji(BAD_LOCAL, "공유기")
checks.append(("사설망 주소는 거부", not bad))
bad2, _ = emoji_store.add_emoji(NOT_IMAGE, "뉴스")
checks.append(("이미지가 아닌 주소는 거부", not bad2))
emoji_store.add_emoji(PNG, "야옹이")
checks.append(("이름과 함께 저장됨",
               [e["name"] for e in emoji_store.load_emojis()] == ["멍멍이", "야옹이"]))
checks.append(("이름 바꾸기", emoji_store.rename_emoji(GIF, "댕댕이")
               and emoji_store.load_emojis()[0]["name"] == "댕댕이"))
saved_raw = json.load(open(emoji_store.EMOJI_STORE_FILE, encoding="utf-8"))
checks.append(("파일에는 주소만 저장(그림 데이터 없음)",
               all(set(item) <= {"url", "name"} for item in saved_raw)))

# ---------- 2) 전송 형식 ----------
message = "이거 봐 " + format_emoji(GIF) + " 귀엽지"
parts = split_emoji_parts(message)
checks.append(("글자와 이모티콘이 분리됨",
               parts == [("text", "이거 봐 "), ("emoji", GIF), ("text", " 귀엽지")]))
checks.append(("주소 문자열이 그대로 노출되지 않음", GIF not in "".join(
    v for k, v in parts if k == "text")))
checks.append(("표시가 없는 평범한 메시지는 그대로",
               split_emoji_parts("안녕") == [("text", "안녕")]))
checks.append(("짝이 안 맞는 표시는 글자로 취급(대화가 사라지지 않음)",
               split_emoji_parts("깨진 " + EMOJI_OPEN + "http://x")[0][0] == "text"))
checks.append(("메시지 한 줄이 IRC 한도(512바이트) 안에 들어감",
               len(message.encode("utf-8")) < 400))

# ---------- 3) 화면 렌더링 + 빈 공간 ----------
page = g.ChatPage(on_send=lambda c, t: None, on_add_channel=lambda: None,
                  on_leave_channel=lambda c: None, on_set_avatar=lambda: None)
page.resize(880, 700)
page.show()
page.my_id = "Mong"
page.add_channel("#test")
page.set_active_channel("#test")
for _ in range(6):
    app.processEvents()
page.load_history("#test", sample_history(60))
for _ in range(8):
    app.processEvents()

view = page._log_views["#test"]


def dead_space():
    for _ in range(6):
        app.processEvents()
    bar = view.verticalScrollBar()
    bar.setValue(bar.maximum())
    for _ in range(4):
        app.processEvents()
    content = view.widget()
    layout = content.layout()
    bottom = 0
    for i in range(layout.count()):
        w = layout.itemAt(i).widget()
        if w is not None and w.isVisible():
            bottom = max(bottom, w.geometry().bottom() + 1)
    return content.height() - bottom - layout.contentsMargins().bottom()


before = dead_space()
page.append_message("#test", "hjsong", "이거 봐 " + format_emoji(GIF), False, 1.0)
page.append_message("#test", "Mong", format_emoji(PNG), True, 2.0)
after = dead_space()
msg = view._messages[-2]
checks.append(("이모티콘이 있는 메시지에 이모티콘 칸이 생김", msg.emoji_area is not None))
checks.append(("이모티콘 주소가 글자로 안 보임", GIF not in msg._text_label.text()))
checks.append(("이모티콘만 보낸 메시지는 보낸사람만 표시",
               "Mong" in view._messages[-1]._text_label.text()))
checks.append((f"이모티콘이 붙어도 아래 빈 공간이 없음(전 {before} / 후 {after})",
               after <= max(12, before)))

# 그림이 나중에 도착해도 빈 공간이 안 생기는지 - 실제 도착 경로를 태움
row = msg.emoji_area


def make_png(width=200, height=140) -> bytes:
    """진짜 PNG 바이트 - 손으로 만든 가짜를 쓰면 로딩이 실패해서 '도착 경로'를 안 탄다."""
    from PySide6.QtCore import QBuffer, QIODevice
    from PySide6.QtGui import QColor, QImage

    image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(QColor("#6c5ce7"))
    # QBuffer(QByteArray())처럼 임시 객체를 넘기면 안 된다. Qt가 그 바이트배열을 가리키고만
    # 있는데 파이썬 쪽에서 곧바로 회수돼서, 이미 사라진 메모리를 건드려 프로세스가 통째로
    # 죽는다(실제로 접근 위반으로 죽는 것을 확인). 인자 없이 만들면 자기 버퍼를 쓴다.
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(buffer.data())


png_bytes = make_png()
for preview in row._previews:
    row._on_image(preview, png_bytes)
checks.append(("그림이 실제로 로딩됨(가짜 데이터가 아님)",
               row._previews[0].pixmap() is not None
               and not row._previews[0].pixmap().isNull()))
after_load = dead_space()
checks.append((f"그림이 도착한 뒤에도 빈 공간이 없음({after_load})", after_load <= 12))
checks.append(("이모티콘이 링크 미리보기(320px)보다 작게 그려짐",
               row._previews[0].width() <= EMOJI_PX))

# ---------- 4) 보관함 창 ----------
for i in range(20):
    emoji_store.add_emoji(f"https://example.com/e{i}.png", f"이름{i}")
picker = EmojiPicker(page, fetcher=None)
total = len(emoji_store.load_emojis())
checks.append((f"페이지가 나뉨(총 {total}개, 쪽당 {PER_PAGE})",
               picker.page_count() == (total + PER_PAGE - 1) // PER_PAGE))
checks.append(("첫 페이지에서는 이전 버튼이 꺼져 있음", not picker.prev_btn.isEnabled()))
picker._go(1)
checks.append(("다음 페이지로 넘어감", picker.page_label.text().startswith("2 /")))
picker.search_input.setText("이름3")
app.processEvents()
checks.append(("이름으로 검색됨", len(picker._items) == 1
               and picker._items[0]["name"] == "이름3"))
picker.search_input.setText("없는이름")
app.processEvents()
checks.append(("검색 결과가 없으면 빈 목록", picker._items == []))
picker.search_input.setText("")
app.processEvents()

# 고르면 입력창에 들어가는지
picked = []
picker.emoji_chosen.connect(picked.append)
picker._on_picked(GIF)
page._insert_emoji(GIF)
checks.append(("고른 이모티콘이 입력창에 들어감", format_emoji(GIF) in page.msg_input.text()))
checks.append(("입력창에 주소 글자가 그대로 보이지 않음(표시로 감싸짐)",
               page.msg_input.text().count(EMOJI_OPEN) == 1))

# ---------- 5) 보관함에서 빼기 ----------
checks.append(("보관함에서 빼기", emoji_store.remove_emoji(PNG)
               and not emoji_store.has_emoji(PNG)))

print("=== 검증 결과 (이모티콘) ===")
all_ok = True
for name, ok in checks:
    print(f"[{'OK' if ok else 'FAIL'}] {name}")
    all_ok = all_ok and ok
print("\n전체 통과:", all_ok)
_sys.exit(0 if all_ok else 1)
