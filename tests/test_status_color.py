"""로그인 화면 상태 문구가 오류/안내에 따라 색이 갈리는지 검증.

계기: IRC 서버가 접속 중 보내는 안내("hostname을 못 찾아 IP 주소를 대신 씁니다")가
빨간 오류색으로 떠서, 아무 문제 없는데 오류가 난 것처럼 보였음.
"""
import os as _os
import sys as _sys

_HERE = _os.path.dirname(_os.path.abspath(__file__))
_REPO = _os.path.dirname(_HERE)

import os, sys
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, _REPO)

from PySide6.QtWidgets import QApplication
import gui_client as g
from chat_core import events as domain_events

app = QApplication.instance() or QApplication([])
app.setStyleSheet(g.STYLE_SHEET)
fails = []


def check(label, cond, extra=""):
    print(("  OK   " if cond else "  FAIL ") + label + ("" if cond else f"  <- {extra}"))
    if not cond:
        fails.append(label)


def color_of(label):
    """실제로 화면에 칠해지는 글자색"""
    return label.palette().color(label.foregroundRole()).name()


page = g.LoginPage(on_submit=lambda m: None, on_cancel=lambda: None)
page.show()
app.processEvents()
lbl = page.status_label

print("[1] 오류/안내에 따라 objectName이 갈리는가")
page.show_status("뭔가 잘못됨")
check("기본은 오류색", lbl.objectName() == "status_err", lbl.objectName())
err_color = color_of(lbl)
page.show_status("연결 중...", error=False)
check("error=False면 안내색", lbl.objectName() == "status_info", lbl.objectName())
info_color = color_of(lbl)
print(f"  오류색 {err_color} / 안내색 {info_color}")
check("두 색이 실제로 다름", err_color != info_color, (err_color, info_color))
check("오류색은 빨강 계열", err_color.lower().startswith("#ff"), err_color)

print("\n[2] 오류로 되돌아오는가(한 번 안내색이 되면 계속 회색이면 안 됨)")
page.show_status("진짜 오류")
check("다시 오류색", lbl.objectName() == "status_err" and color_of(lbl) == err_color,
      (lbl.objectName(), color_of(lbl)))

print("\n[3] 실제 이벤트 경로 - 서버 안내는 안내색, 인증 실패는 오류색")
win = g.MainWindow()
win.show()
app.processEvents()
win.stack.setCurrentWidget(win.login_page)
app.processEvents()
sl = win.login_page.status_label

# IRC 서버가 접속 중 보내는 안내(채널 없음 = 로그인 전)
win._on_domain_event(domain_events.SystemNotice(
    "", "*** Could not resolve your hostname; using your IP address instead"))
app.processEvents()
check("서버 접속 안내는 안내색",
      sl.objectName() == "status_info", sl.objectName())
check("문구는 그대로 보임", "IP address" in sl.text(), sl.text())

win._on_domain_event(domain_events.AuthFailed("비밀번호가 일치하지 않습니다."))
app.processEvents()
check("인증 실패는 오류색", sl.objectName() == "status_err", sl.objectName())
check("실패 문구 보임", "비밀번호" in sl.text(), sl.text())

win._on_domain_event(domain_events.NicknameRetrying("nick_"))
app.processEvents()
check("닉네임 재시도 안내는 안내색", sl.objectName() == "status_info", sl.objectName())

print("\n[4] 채널 화면도 같은 규칙")
cp = win.channel_page
cp.show_status("채널명을 입력하세요.")
check("채널 화면 오류색", cp.status_label.objectName() == "status_err")
cp.show_status("채널 생성 완료!", error=False)
check("채널 화면 안내색", cp.status_label.objectName() == "status_info")

print()
if fails:
    print(f"실패 {len(fails)}건: {fails}")
    sys.exit(1)
print("전부 통과")
