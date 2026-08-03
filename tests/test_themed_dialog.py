import os as _os
import sys as _sys

_HERE = _os.path.dirname(_os.path.abspath(__file__))
_REPO = _os.path.dirname(_HERE)
import os, sys
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, _REPO)
from PySide6.QtWidgets import QApplication, QPushButton, QLabel
from PySide6.QtCore import Qt
import gui_client as g

app = QApplication(sys.argv)
app.setStyleSheet(g.STYLE_SHEET)

checks = []

# ---- ThemedDialog 기본: 프레임 없음(Windows), 타이틀바 텍스트, 버튼 반환값 ----
dlg = g.ThemedDialog("채널 나가기", "'#test' 채널에서 나갈까요?", [("아니오", False), ("예", True)], default_value=False)
checks.append(("프레임 없는 창으로 설정됨(Windows에서)",
               bool(dlg.windowFlags() & Qt.WindowType.FramelessWindowHint) == g.IS_WINDOWS))
checks.append(("닫기 전 기본값은 False", dlg.result_value is False))

buttons = {b.text(): b for b in dlg.findChildren(QPushButton)}
checks.append(("예/아니오 버튼이 둘 다 있음", "예" in buttons and "아니오" in buttons))
buttons["예"].click()
checks.append(("예 버튼 클릭 시 result_value가 True로 바뀜", dlg.result_value is True))

# ---- 미니 타이틀바: 제목 라벨 + 닫기 버튼 ----
titlebars = dlg.findChildren(g._MiniTitleBar)
checks.append(("미니 타이틀바가 하나 있음", len(titlebars) == 1))
if titlebars:
    tb = titlebars[0]
    title_labels = [l for l in tb.findChildren(QLabel) if l.text() == "채널 나가기"]
    checks.append(("타이틀바에 다이얼로그 제목이 표시됨", len(title_labels) == 1))
    close_btns = [b for b in tb.findChildren(QPushButton) if b.objectName() == "titleBarCloseBtn"]
    checks.append(("타이틀바에 닫기 버튼이 있음", len(close_btns) == 1))
    if close_btns:
        dlg2 = g.ThemedDialog("취소 테스트", "닫기 버튼으로 취소", [("아니오", False), ("예", True)], default_value=False)
        tb2 = dlg2.findChildren(g._MiniTitleBar)[0]
        close_btn2 = [b for b in tb2.findChildren(QPushButton) if b.objectName() == "titleBarCloseBtn"][0]
        close_btn2.click()
        checks.append(("닫기 버튼 클릭 시 취소되어 기본값 유지", dlg2.result_value is False))

# ---- themed_warning: 확인 버튼 하나만 ----
warn_dlg = g.ThemedDialog("오류", "테스트 경고 메시지", [("확인", None)])
ok_btns = [b for b in warn_dlg.findChildren(QPushButton) if b.text() == "확인"]
checks.append(("경고창엔 확인 버튼 하나만 있음", len(ok_btns) == 1))

print("\n=== 검증 결과 (테마 맞춘 확인/경고창) ===")
all_ok = True
for name, ok in checks:
    print(f"[{'OK' if ok else 'FAIL'}] {name}")
    all_ok = all_ok and ok
print("전체 통과:", all_ok)
