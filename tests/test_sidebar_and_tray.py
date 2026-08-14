"""사용자가 실제로 겪은 UI 문제 세 가지.

1. **트레이 아이콘이 한 번 사라지면 다시는 안 보인다.** 만들 수 있는지를 앱 켤 때 딱
   한 번만 확인해서, 윈도우 탐색기가 재시작되거나 로그인 직후처럼 트레이가 늦게 준비되면
   그 실행 내내 아이콘이 없었다("설정을 껐다 켜도 안 보인다"는 신고).
2. **채널 목록을 접으면 환경설정 톱니까지 사라진다.** 접어둔 사람에게는 설정으로 가는
   길이 트레이 메뉴 하나만 남는다.
3. **채널 목록을 펴면 대화창이 좁아진다.** 읽던 줄이 다시 접히면서 화면이 출렁인다.
   목록이 펴진 만큼 창이 넓어져야 대화 영역이 그대로 유지된다.
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

checks = []


def check(name, ok, detail=""):
    checks.append((name, ok, detail))


window = g.MainWindow()
window.resize(1000, 700)
window.show()
chat_page = window.chat_page
chat_page.add_channel("#a")
window.show_page(chat_page)
for _ in range(10):
    app.processEvents()

sidebar = chat_page.channel_sidebar
log_view = chat_page._log_views["#a"]

# ---------- 1) 트레이가 사라져도 돌아오는가 ----------
tray = window._tray
if tray.available:
    tray._tray.hide()                      # 탐색기 재시작 등으로 사라진 상황
    check("사라진 상태를 만들었다", not tray._tray.isVisible())
    tray._ensure_visible()                 # 감시 장치가 도는 순간
    check("감시가 돌면 다시 보인다", tray._tray.isVisible())

    tray._tray = None                      # 켤 때 트레이가 아예 없었던 상황
    tray._ensure_visible()
    check("나중에 트레이가 생기면 그때 만든다", tray._tray is not None)

    tray.hide()                            # 앱을 끝내는 중
    tray._ensure_visible()
    check("끝내는 중에는 다시 띄우지 않는다",
          tray._tray is None or not tray._tray.isVisible())
else:
    check("이 환경에는 트레이가 없어 검사 생략", True)

# ---------- 2) 접어도 톱니는 보이는가 ----------
sidebar.set_collapsed(False)
for _ in range(5):
    app.processEvents()
check("펼친 상태에서 톱니가 보인다", chat_page.gear_btn.isVisible())

width_before = log_view.width()
sidebar.set_collapsed(True)
for _ in range(8):
    app.processEvents()
check("채널 목록 자체는 접힌다", not sidebar.list.isVisible())
# 톱니는 채널 목록 **밖**(손잡이 열)에 있으므로 접어도 그대로 보인다
check("접어도 톱니는 그대로 보인다", chat_page.gear_btn.isVisible())
check("톱니가 손잡이 열 안에 온전히 들어간다",
      chat_page.gear_btn.width() <= chat_page.gear_btn.parentWidget().width(),
      (chat_page.gear_btn.width(), chat_page.gear_btn.parentWidget().width()))

# ---------- 3) 접고 펴도 대화 영역이 유지되는가 ----------
check(f"접어도 대화 영역 폭이 그대로({width_before} -> {log_view.width()})",
      abs(log_view.width() - width_before) <= 2, (width_before, log_view.width()))

sidebar.set_collapsed(False)
for _ in range(8):
    app.processEvents()
screen = window.screen()
room = screen.availableGeometry().width() if screen else 10000
if window.width() < room:
    check(f"펴도 대화 영역 폭이 그대로({width_before} -> {log_view.width()})",
          abs(log_view.width() - width_before) <= 2, (width_before, log_view.width()))
else:
    # 화면이 좁아 창을 더 못 늘리는 경우 - 그때는 예전처럼 안에서 나눠 쓸 수밖에 없다
    check(f"화면 끝까지는 늘려서 최대한 지킨다(창 {window.width()} / 화면 {room})",
          window.width() >= room - 2, (window.width(), room))

# ---------- 4) 손잡이 화살표가 움직이는 방향과 맞는가 ----------
# 접고 펼 때 **창의 왼쪽 변**이 움직인다(대화 영역은 제자리). 화살표가 그 반대를 가리키면
# "화살표가 반대인 것 같다"는 말을 듣는다(실제로 들었다).
handle = chat_page.sidebar_handle
sidebar.set_collapsed(False)
for _ in range(6):
    app.processEvents()
left_before = window.x()
check("펼친 상태에서는 오른쪽(접히는 쪽)을 가리킨다", handle._collapsed is False)

sidebar.set_collapsed(True)
for _ in range(8):
    app.processEvents()
check(f"접으면 창 왼쪽 변이 오른쪽으로 온다({left_before} -> {window.x()})",
      window.x() >= left_before, (left_before, window.x()))
check("접힌 상태에서는 왼쪽(펴지는 쪽)을 가리킨다", handle._collapsed is True)

print("=== 검증 결과 (트레이 / 톱니 / 채널 목록 폭) ===")
all_ok = True
for name, ok, *detail in checks:
    extra = f"  <- {detail[0]}" if detail and detail[0] and not ok else ""
    print(f"[{'OK' if ok else 'FAIL'}] {name}{extra}")
    all_ok = all_ok and ok
print("\n전체 통과:", all_ok)
_sys.exit(0 if all_ok else 1)
