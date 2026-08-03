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

long_text = "이것은 정말정말 긴 채팅 메시지입니다 " * 10  # 매우 긴 한 줄짜리 텍스트

view = g.ChannelLogView("#test")
view.resize(300, 400)
view.show()
avatar = g._hashed_avatar_pixmap("tester")
view.append_message("tester", long_text, False, 0, avatar)
app.processEvents()
app.processEvents()

msg_widget = view._layout.itemAt(0).widget()
checks.append(("긴 메시지 위젯이 뷰포트 폭을 넘지 않음(가로 스크롤/잘림 없음)",
               msg_widget.width() <= view.viewport().width() + 2))
checks.append(("긴 메시지는 여러 줄로 줄바꿈되어 높이가 한 줄보다 훨씬 큼", msg_widget.height() > 60))

# 창을 더 좁게/넓게 리사이즈하면 줄바꿈 지점도 반응형으로 바뀌는지(높이가 달라짐)
height_narrow = msg_widget.height()
view.resize(600, 400)
app.processEvents()
app.processEvents()
msg_widget2 = view._layout.itemAt(0).widget()
checks.append(("창을 넓히면 같은 텍스트라도 줄 수가 줄어서 높이가 더 작아짐(반응형)",
               msg_widget2.height() < height_narrow))
checks.append(("넓힌 상태에서도 폭을 넘지 않음", msg_widget2.width() <= view.viewport().width() + 2))

print("\n=== 검증 결과 (긴 채팅 메시지 반응형 줄바꿈) ===")
all_ok = True
for name, ok in checks:
    print(f"[{'OK' if ok else 'FAIL'}] {name}")
    all_ok = all_ok and ok
print("전체 통과:", all_ok)
