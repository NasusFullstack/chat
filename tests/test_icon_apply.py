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
icon_path = g._find_app_icon()
print("찾은 아이콘 경로:", icon_path)
checks = [
    ("icon.ico를 우선적으로 찾음", icon_path.endswith("icon.ico")),
]
from PySide6.QtGui import QIcon
icon = QIcon(icon_path)
checks.append(("아이콘이 비어있지 않음(정상 로드)", not icon.isNull()))
pm = icon.pixmap(32, 32)
checks.append(("32px pixmap 렌더링 가능", not pm.isNull() and pm.width() == 32))

window = g.MainWindow()
window.set_window_icon(icon)
app.processEvents()
checks.append(("MainWindow.set_window_icon 호출 시 windowIcon 반영됨", not window.windowIcon().isNull()))
if window._title_bar is not None:
    checks.append(("타이틀바 아이콘 라벨에도 픽스맵이 반영됨", not window._title_bar.icon_label.pixmap().isNull()))

print("\n=== 검증 결과 (아이콘 적용) ===")
all_ok = True
for name, ok in checks:
    print(f"[{'OK' if ok else 'FAIL'}] {name}")
    all_ok = all_ok and ok
print("전체 통과:", all_ok)
