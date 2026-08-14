"""로그인/접속 화면의 안내 문구가 잘리지 않는가.

실제 신고(2026-08-14): "로그인이랑 서버 접속창 경고/알림이 자꾸 잘려".

재보니 두 가지가 겹쳐 있었다.
1. 안내 칸의 높이가 고정이라, 두 줄이 넘어가면 **뒷줄이 그냥 안 보였다**
   (실측: 94px가 필요한데 칸은 67px). 하필 "왜 안 되는지" 설명하는 문장이 뒷줄이었다.
2. 문구 자체가 길었다. 접속 화면에서 네 줄짜리 설명을 읽는 사람은 없다.

지금은 칸이 글자에 맞춰 늘어나고, 문구도 한두 줄로 줄였다. 이 검사는 **앱이 실제로
띄우는 모든 안내**를 넣어보고 하나라도 잘리면 실패한다.
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
from chat_core import constants  # noqa: E402
from gui.network_probe import blocked_port_message  # noqa: E402

app.setStyleSheet(g.STYLE_SHEET)

checks = []


def check(name, ok, detail=""):
    checks.append((name, ok, detail))


window = g.MainWindow()
window.resize(900, 700)
window.show()
page = window.login_page
window.show_page(page)
for _ in range(10):
    app.processEvents()

label = page.status_label
check("안내 칸이 줄바꿈을 한다", label.wordWrap() is True)

# 앱이 실제로 띄우는 안내들(하나라도 빠뜨리면 그 문구만 잘린 채 나간다)
MESSAGES = {
    "연결 중": "연결 중... (IRC 서버)",
    "응답 없음": "서버가 응답하지 않습니다. 주소와 포트를 확인하세요.",
    "보안 막힘": "보안 접속이 막혀 일반 접속으로 다시 시도합니다...",
    "재접속": "다시 접속합니다...",
    "비밀번호 안내": constants.SASL_FAILED_HELP,
    "포트 막힘": blocked_port_message("home.pdlab.kr", 6697),
    "아주 긴 글": "가나다라마바사아자차카타파하" * 6,
}

for name, text in MESSAGES.items():
    page.show_status(text)
    for _ in range(4):
        app.processEvents()
    needed = label.heightForWidth(label.width())
    check(f"{name}: 잘리지 않는다(필요 {needed}px / 칸 {label.height()}px)",
          label.height() >= needed, (needed, label.height()))

# 접속 화면에서 읽을 수 있는 길이인가 - 길면 아무도 안 읽는다
for name, text in MESSAGES.items():
    if name == "아주 긴 글":
        continue
    check(f"{name}: 접속 화면에서 읽을 만한 길이({len(text)}자)", len(text) <= 90, len(text))

print("=== 검증 결과 (안내 문구가 잘리지 않는가) ===")
all_ok = True
for name, ok, *detail in checks:
    extra = f"  <- {detail[0]}" if detail and detail[0] and not ok else ""
    print(f"[{'OK' if ok else 'FAIL'}] {name}{extra}")
    all_ok = all_ok and ok
print("\n전체 통과:", all_ok)
_sys.exit(0 if all_ok else 1)
