"""창 가장자리 크기조절 처리가 스스로를 무한히 파고들지 않는가.

실제 사고(2026-08-13, 사용자 PC): 앱이 멈추더니 그냥 꺼졌다. 어제 넣어둔 크래시 기록이
원인을 그대로 찍어줬다.

    ===== 2026-08-13 11:51:10 [실행 시작] v2.0.15 =====
    Windows fatal exception: stack overflow
    Current thread:
      File "gui\\main_window.py", line 629 in eventFilter

이유: 프레임 없는 창이라 가장자리 크기조절을 우리가 직접 처리하는데, 그 필터가
**앱 전체(QApplication)**에 걸려 있고 마우스가 움직일 때마다 `setCursor()`를 불렀다.
커서를 바꾸면 Qt가 그 자리에 마우스 이벤트를 다시 흘리고, 그게 또 이 필터로 들어와
끝없이 파고든다. 파이썬 예외가 아니라 C 스택이 넘치는 것이라 앱이 그냥 사라진다.

여기서는 그 되돌이를 흉내 내서 **다시 들어와도 멈추는지** 확인한다.
"""
import os as _os
import sys as _sys

_HERE = _os.path.dirname(_os.path.abspath(__file__))
_REPO = _os.path.dirname(_HERE)

_os.environ["QT_QPA_PLATFORM"] = "offscreen"
_sys.path.insert(0, _REPO)

from PySide6.QtCore import QEvent, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QMouseEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])

import gui_client as g  # noqa: E402

checks = []


def check(name, ok, detail=""):
    checks.append((name, ok, detail))


window = g.MainWindow()
window.resize(900, 700)
window.show()
app.processEvents()

if not g.IS_WINDOWS:
    print("이 검사는 창 테두리를 직접 그리는 Windows에서만 의미가 있다")
    print("\n전체 통과: True")
    _sys.exit(0)


def mouse_move(x, y):
    point = QPointF(x, y)
    return QMouseEvent(QEvent.Type.MouseMove, point, window.mapToGlobal(point.toPoint()),
                       Qt.MouseButton.NoButton, Qt.MouseButton.NoButton,
                       Qt.KeyboardModifier.NoModifier)


# 커서를 바꾸면 Qt가 마우스 이벤트를 다시 흘리는 상황을 그대로 흉내 낸다
depth = {"now": 0, "max": 0}
real_set_cursor = window.setCursor


def set_cursor_that_feeds_back(shape):
    real_set_cursor(shape)
    depth["now"] += 1
    depth["max"] = max(depth["max"], depth["now"])
    try:
        if depth["now"] < 200:      # 안 멈추면 여기서 끊는다(진짜로 죽지 않게)
            window.eventFilter(window, mouse_move(2, 300))
    finally:
        depth["now"] -= 1


window.setCursor = set_cursor_that_feeds_back
window.eventFilter(window, mouse_move(2, 300))       # 왼쪽 가장자리(커서가 바뀌는 자리)
window.setCursor = real_set_cursor

check(f"되돌아 들어와도 멈춘다(가장 깊이 들어간 횟수 {depth['max']})",
      depth["max"] <= 2, depth["max"])

# 그러면서도 제 일은 해야 한다 - 가장자리에서는 크기조절 커서로 바뀌어야 한다
window.unsetCursor()
window.eventFilter(window, mouse_move(2, 300))
edge_shape = window.cursor().shape()
check(f"가장자리에서는 크기조절 커서로 바뀐다({edge_shape})",
      edge_shape in (Qt.CursorShape.SizeHorCursor, Qt.CursorShape.SizeVerCursor,
                     Qt.CursorShape.SizeFDiagCursor, Qt.CursorShape.SizeBDiagCursor),
      edge_shape)

window.eventFilter(window, mouse_move(400, 350))     # 창 한가운데
check(f"가운데에서는 평범한 커서로 돌아온다({window.cursor().shape()})",
      window.cursor().shape() == Qt.CursorShape.ArrowCursor, window.cursor().shape())

# 같은 자리에서 계속 움직여도 커서를 거듭 새로 설정하지 않아야 한다(되돌이의 출발점)
calls = {"n": 0}


def counting_set_cursor(shape):
    calls["n"] += 1
    real_set_cursor(shape)


window.setCursor = counting_set_cursor
for _ in range(20):
    window.eventFilter(window, mouse_move(400, 350))
window.setCursor = real_set_cursor
check(f"모양이 그대로면 커서를 다시 설정하지 않는다({calls['n']}번)", calls["n"] == 0,
      calls["n"])

print("=== 검증 결과 (가장자리 처리 무한 재귀) ===")
all_ok = True
for name, ok, *detail in checks:
    extra = f"  <- {detail[0]}" if detail and detail[0] and not ok else ""
    print(f"[{'OK' if ok else 'FAIL'}] {name}{extra}")
    all_ok = all_ok and ok
print("\n전체 통과:", all_ok)
_sys.exit(0 if all_ok else 1)
