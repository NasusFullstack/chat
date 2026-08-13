"""실제 사용에 가깝게: 메시지 많은 창을 창 크기 바꿔가며 흔들어 본다.

"멈추더니 꺼진다"는 파이썬 예외가 아니라 네이티브 크래시(스택 오버플로 등)의 증상이다.
그래서 이 스크립트는 예외를 잡는 게 아니라 **프로세스가 죽는지**를 본다.
"""
import os, sys, time
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PySide6.QtWidgets import QApplication
app = QApplication([])
import gui_client as g
app.setStyleSheet(g.STYLE_SHEET)

w = g.MainWindow()
w.resize(900, 700)
w.show()
cp = w.chat_page
cp.my_id = "me"
cp.add_channel("#stress")
avatar = g._hashed_avatar_pixmap("t")

long_text = "긴 문장을 넣어 줄바꿈이 여러 번 일어나게 만든다 " * 6
for i in range(200):
    text = long_text if i % 3 else f"짧은 메시지 {i}"
    if i % 7 == 0:
        text += " https://example.com/image_%d.png" % i
    cp.append_message("#stress", "bob" if i % 2 else "me", text, i % 2 == 0, time.time())
app.processEvents()
print("메시지 200개 채움", flush=True)

widths = [900, 620, 1200, 480, 1000, 520, 1400, 700]
for round_no in range(6):
    for width in widths:
        w.resize(width, 700)
        app.processEvents()
        app.processEvents()
    print(f"  {round_no + 1}번째 크기 변경 통과", flush=True)

print("살아남음")
