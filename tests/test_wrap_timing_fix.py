import os as _os
import sys as _sys

_HERE = _os.path.dirname(_os.path.abspath(__file__))
_REPO = _os.path.dirname(_HERE)
import os, sys
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, _REPO)
from PySide6.QtWidgets import QApplication
import gui_client as g

app = QApplication(sys.argv)
app.setStyleSheet(g.STYLE_SHEET)

checks = []
avatar = g._hashed_avatar_pixmap("t")

# ---- 메시지를 추가하는 즉시(이벤트 루프 처리 전) maximumWidth가 뷰포트에 맞게 설정되는지 ----
view = g.ChannelLogView("#test")
view.resize(300, 400)
view.show()
view.append_message("bob", "매우 긴 텍스트를 넣어서 줄바꿈이 필요한 메시지를 시험합니다 " * 5, False, 0, avatar)
# app.processEvents()를 아예 호출하지 않은 상태 - 비동기로 막 도착한 메시지가
# 레이아웃이 안정되기 전에 추가되는 상황을 재현
w = view._layout.itemAt(0).widget()
checks.append(("processEvents 없이도(레이아웃이 아직 안 도는 상황) maximumWidth가 즉시 설정됨",
               w._text_label.maximumWidth() < 10000))
expected = max(40, view.viewport().width() - g.AVATAR_MSG_PX - 24)
checks.append(("maximumWidth가 뷰포트 폭 기준으로 정확히 계산됨", w._text_label.maximumWidth() == expected))

app.processEvents()
app.processEvents()
checks.append(("실제 렌더링 후에도 뷰포트 폭을 넘지 않음", w.width() <= view.viewport().width() + 2))

# ---- 창 크기를 바꾸면 기존 메시지들의 wrap 너비도 갱신되는지 ----
view.resize(600, 400)
app.processEvents()
app.processEvents()
new_expected = max(40, view.viewport().width() - g.AVATAR_MSG_PX - 24)
checks.append(("리사이즈하면 기존 메시지의 maximumWidth도 새 뷰포트에 맞게 갱신됨",
               w._text_label.maximumWidth() == new_expected))

# ---- '내가 보낸' 메시지와 '남이 보낸' 메시지 둘 다 동일하게 wrap 너비가 설정되는지 ----
view2 = g.ChannelLogView("#test2")
view2.resize(300, 400)
view2.show()
long_text = "동일한 긴 텍스트라서 두 경우 다 같은 폭으로 줄바꿈되어야 함 " * 5
view2.append_message("me", long_text, True, 0, avatar)   # 내가 보낸 것
view2.append_message("other", long_text, False, 0, avatar)  # 남이 보낸 것
w_mine = view2._layout.itemAt(0).widget()
w_other = view2._layout.itemAt(1).widget()
checks.append(("내가 보낸 메시지와 남이 보낸 메시지의 wrap 너비가 동일함",
               w_mine._text_label.maximumWidth() == w_other._text_label.maximumWidth()))

print("\n=== 검증 결과 (비동기 메시지 줄바꿈 타이밍 버그 수정) ===")
all_ok = True
for name, ok in checks:
    print(f"[{'OK' if ok else 'FAIL'}] {name}")
    all_ok = all_ok and ok
print("전체 통과:", all_ok)
