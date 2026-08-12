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
# 빼야 할 폭을 상수로 어림잡던 검사였는데(-24), 그 어림값이 실제 여백과 안 맞아
# 좁은 창에서 그림이 삐져나가는 문제가 있었다. 지금 코드는 실제 레이아웃 값에서
# 계산한다. 그래서 여기서도 공식을 베끼지 않고 **결과**를 본다:
# 아이콘+여백까지 합쳐 뷰포트 안에 들어오면 된다(가로 스크롤이 안 생기는 조건)
row = w.layout()
margins = row.contentsMargins()
overhead = g.AVATAR_MSG_PX + margins.left() + margins.right() + row.spacing()
used = w._text_label.maximumWidth() + overhead
checks.append((f"글자 폭 + 아이콘 + 여백이 뷰포트 안에 들어옴({used} <= {view.viewport().width()})",
               used <= view.viewport().width()))
checks.append(("쓸 수 있는 폭을 지나치게 버리지 않음(뷰포트의 90% 이상 사용)",
               used >= view.viewport().width() * 0.9))

app.processEvents()
app.processEvents()
checks.append(("실제 렌더링 후에도 뷰포트 폭을 넘지 않음", w.width() <= view.viewport().width() + 2))

# ---- 창 크기를 바꾸면 기존 메시지들의 wrap 너비도 갱신되는지 ----
before_width = w._text_label.maximumWidth()
view.resize(600, 400)
app.processEvents()
app.processEvents()
# 창을 넓힌 만큼 글자 폭도 같이 넓어져야 한다(예전 폭에 굳으면 오른쪽이 텅 빈다)
grown = w._text_label.maximumWidth() - before_width
checks.append((f"창을 넓힌 만큼 글자 폭도 넓어짐(+{grown}px)", grown > 250))
checks.append(("넓힌 뒤에도 뷰포트를 넘지 않음",
               w._text_label.maximumWidth() + overhead <= view.viewport().width()))

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
