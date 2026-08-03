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
window = g.MainWindow()
window.show()
app.processEvents()
app.processEvents()

checks = []
tb_h = window._title_bar.height()
content_h = window.height() - tb_h
checks.append(("시작 시 로그인 화면에 줄 수 있는 공간이 sizeHint 이상", content_h >= window.login_page.sizeHint().height()))

min_content_h = window.minimumHeight() - tb_h
checks.append(("최소 창 크기로 줄여도 로그인 화면 최소 요구 높이 이상 확보됨",
               min_content_h >= window.login_page.minimumSizeHint().height()))

print("\n=== 검증 결과 (시작 화면 크기, 타이틀바 반영) ===")
all_ok = True
for name, ok in checks:
    print(f"[{'OK' if ok else 'FAIL'}] {name}")
    all_ok = all_ok and ok
print("전체 통과:", all_ok)
