"""장문이 접히고, 끝까지 보이는가.

실제 신고(2026-08-13): "장문 쓰면 줄바꿈 안 되고 팅기고 안 보이고".

**근본 원인**은 글자 배치를 우리가 추측한 것이었다. 예전에는 `QLabel`에 글을 넣고
"이 폭이면 높이가 얼마냐"를 Qt에게 물어 짜맞췄는데, 그 구조에서 같은 뿌리의 사고가
반복해서 났다: 공백 없는 글이 아예 안 접힘 / 라벨이 답하는 높이가 상황마다 다름 /
크기 정책을 새로 만들면 높이를 아예 안 물어봄 / 눌린 상태에서 잰 값을 필요한 높이로 답함.

지금은 배치와 높이를 **텍스트 엔진**이 정한다(gui/components/message_text.py).
줄바꿈 규칙을 "아무 데서나 접기"로 지정할 수 있고, 높이는 문서가 알려주는 값을 그대로
쓴다. 그래서 이 검사들은 "추측이 맞았는가"가 아니라 **결과가 보이는가**를 본다.
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

app.setStyleSheet(g.STYLE_SHEET)

checks = []


def check(name, ok, detail=""):
    checks.append((name, ok, detail))


def show(text, width=700, height=400):
    view = g.ChannelLogView("#t")
    view.resize(width, height)
    view.show()
    view.append_message("bob", text, False, 0, g._hashed_avatar_pixmap("t"))
    for _ in range(15):
        app.processEvents()
    message = None
    for i in range(view._layout.count()):
        item = view._layout.itemAt(i)
        if item is not None and item.widget() is not None \
                and hasattr(item.widget(), "_text_label"):
            message = item.widget()
    return view, message


NO_SPACE = "가나다라마바사아자차카타파하" * 143      # 띄어쓰기 없는 2000자
WITH_SPACE = "긴 문장을 여러 번 반복해서 넣는다 " * 60

# ---------- 1) 띄어쓰기가 없어도 접히는가(예전에는 한 줄로 굳었다) ----------
view, message = show(NO_SPACE)
label = message._text_label
check(f"띄어쓰기 없는 장문이 접힌다(높이 {label.height()}px)", label.height() > 300,
      label.height())
check("가로로 삐져나가지 않는다", view.horizontalScrollBar().maximum() == 0,
      view.horizontalScrollBar().maximum())
check(f"세로 스크롤이 생겨 끝까지 볼 수 있다({view.verticalScrollBar().maximum()})",
      view.verticalScrollBar().maximum() > 0, view.verticalScrollBar().maximum())

# ---------- 2) 띄어쓰기가 있는 장문도 그대로 ----------
view2, message2 = show(WITH_SPACE)
check(f"띄어쓰기 있는 장문도 접힌다(높이 {message2._text_label.height()}px)",
      message2._text_label.height() > 300, message2._text_label.height())

# ---------- 3) 짧은 메시지가 과하게 커지지 않는가 ----------
view3, message3 = show("안녕")
check(f"짧은 메시지는 한 줄({message3._text_label.height()}px)",
      message3._text_label.height() < 60, message3._text_label.height())

# ---------- 4) 창이 좁아도 넓어도 그 폭에 맞춘다 ----------
heights = {}
for width in (900, 600, 380):
    narrow_view, narrow_message = show(NO_SPACE, width=width)
    heights[width] = narrow_message._text_label.height()
    check(f"창 폭 {width}에서도 가로로 안 삐져나감",
          narrow_view.horizontalScrollBar().maximum() == 0,
          narrow_view.horizontalScrollBar().maximum())
check(f"좁을수록 더 여러 줄이 된다({heights})",
      heights[380] > heights[600] > heights[900], heights)

# ---------- 5) 글자가 잘리지 않는가(문서가 요구하는 높이를 그대로 받았는가) ----------
document = label.document()
document.setTextWidth(label.width())
needed = document.size().height()
check(f"문서가 요구하는 높이({needed:.0f})를 그대로 받았다({label.height()})",
      label.height() >= needed - 1, (label.height(), needed))

# ---------- 6) 링크는 여전히 눌리는가 ----------
view4, message4 = show("여기 봐 https://example.com/abc 링크")
html = message4._text_label.toHtml()
check("링크가 살아 있다", 'href="https://example.com/abc"' in html.replace("&amp;", "&"),
      html[-200:])

print("=== 검증 결과 (장문 줄바꿈/표시) ===")
all_ok = True
for name, ok, *detail in checks:
    extra = f"  <- {detail[0]}" if detail and detail[0] and not ok else ""
    print(f"[{'OK' if ok else 'FAIL'}] {name}{extra}")
    all_ok = all_ok and ok
print("\n전체 통과:", all_ok)
_sys.exit(0 if all_ok else 1)
