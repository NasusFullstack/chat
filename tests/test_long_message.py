"""장문이 접히고, 끝까지 보이는가.

실제 신고(2026-08-13): "장문 쓰면 줄바꿈 안 되고 팅기고 안 보이고 종합적 오류".
재보니 두 가지가 겹쳐 있었다.

1. **Qt는 공백 없는 덩어리를 아예 안 접는다.** 접을 자리가 없다고 보기 때문이다.
   한글/중국어는 띄어쓰기 없이 길게 쓰는 일이 흔해서 그런 메시지가 한 줄로 굳었다.
   실측(폭 400에 1400자): PlainText 12px / RichText 14px / CSS word-wrap도 14px /
   **폭 0인 공백(U+200B)을 끼우면 392px**. 그래서 화면에 그릴 때만 그 공백을 넣는다.

2. **높이를 재는 쪽이 '눌린 상태'를 재고 있었다.** 안쪽 위젯이 필요한 높이(1313px)보다
   작은 상태(498px = 뷰포트 높이)에서 배치를 확정하면 줄들이 눌려 놓이고, 그 눌린
   결과를 "필요한 높이"라고 답한다. 스크롤 영역이 그 값을 그대로 쓰므로 다음에도 같은
   답이 나와 영영 안 늘어난다. 세로 스크롤도 안 생겨서 글 대부분이 영영 안 보였다.
"""
import os as _os
import sys as _sys

_HERE = _os.path.dirname(_os.path.abspath(__file__))
_REPO = _os.path.dirname(_HERE)

_os.environ["QT_QPA_PLATFORM"] = "offscreen"
_sys.path.insert(0, _REPO)

from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])

import gui_client as g  # noqa: E402
from gui.soft_break import ZERO_WIDTH_SPACE, add_break_hints  # noqa: E402

app.setStyleSheet(g.STYLE_SHEET)

checks = []


def check(name, ok, detail=""):
    checks.append((name, ok, detail))


# ---------- 1) 접을 자리를 만드는 규칙 ----------
check("평범한 문장은 손대지 않는다",
      add_break_hints("안녕하세요 오늘 날씨가 좋네요") == "안녕하세요 오늘 날씨가 좋네요")
long_run = add_break_hints("가" * 100)
check(f"공백 없이 길면 접을 자리를 넣는다({long_run.count(ZERO_WIDTH_SPACE)}군데)",
      long_run.count(ZERO_WIDTH_SPACE) >= 3)
check("넣어도 글자 자체는 그대로다",
      long_run.replace(ZERO_WIDTH_SPACE, "") == "가" * 100)

linked = add_break_hints(
    '<a href="https://example.com/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa">'
    'https://example.com/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa</a>')
check("주소(href)는 절대 건드리지 않는다",
      'href="https://example.com/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"' in linked, linked[:120])
check("화면에 보이는 주소에는 접을 자리가 들어간다",
      ZERO_WIDTH_SPACE in linked.split("</a>")[0].split(">", 1)[1], linked[:160])
entity = add_break_hints("&lt;" * 40)
check("&lt; 같은 표기를 쪼개지 않는다", "&lt;" * 2 in entity.replace(ZERO_WIDTH_SPACE, ""),
      entity[:80])

# ---------- 2) 실제 화면에서 끝까지 보이는가 ----------
view = g.ChannelLogView("#t")
view.resize(700, 500)
view.show()
avatar = g._hashed_avatar_pixmap("t")
view.append_message("bob", "가나다라마바사아자차카타파하" * 143, False, 0, avatar)
for _ in range(20):
    app.processEvents()

message = None
for i in range(view._layout.count()):
    item = view._layout.itemAt(i)
    if item is not None and item.widget() is not None and hasattr(item.widget(), "_text_label"):
        message = item.widget()
label = message._text_label
needed = label.heightForWidth(label.maximumWidth())

check(f"긴 글이 여러 줄로 접힌다(높이 {needed}px)", needed > 200, needed)
check(f"라벨이 접힌 높이를 실제로 받는다({label.height()} >= {needed})",
      label.height() >= needed, (label.height(), needed))

content = view.widget()
check(f"목록도 그만큼 커진다({content.height()} >= {needed})",
      content.height() >= needed, (content.height(), needed))
check(f"세로 스크롤이 생겨 끝까지 볼 수 있다(스크롤 {view.verticalScrollBar().maximum()})",
      view.verticalScrollBar().maximum() > 0, view.verticalScrollBar().maximum())
check("가로로는 삐져나가지 않는다", view.horizontalScrollBar().maximum() == 0,
      view.horizontalScrollBar().maximum())

# 짧은 메시지는 예전처럼 한 줄이어야 한다(과하게 늘어나면 그것도 버그다)
view2 = g.ChannelLogView("#s")
view2.resize(700, 500)
view2.show()
view2.append_message("bob", "안녕", False, 0, avatar)
for _ in range(10):
    app.processEvents()
short = None
for i in range(view2._layout.count()):
    item = view2._layout.itemAt(i)
    if item is not None and item.widget() is not None and hasattr(item.widget(), "_text_label"):
        short = item.widget()
check(f"짧은 메시지는 여전히 한 줄({short.height()}px)", short.height() < 80, short.height())

print("=== 검증 결과 (장문 줄바꿈/표시) ===")
all_ok = True
for name, ok, *detail in checks:
    extra = f"  <- {detail[0]}" if detail and detail[0] and not ok else ""
    print(f"[{'OK' if ok else 'FAIL'}] {name}{extra}")
    all_ok = all_ok and ok
print("\n전체 통과:", all_ok)
_sys.exit(0 if all_ok else 1)
