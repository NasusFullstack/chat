"""서버가 죽었다 살아났을 때 자동 재접속이 실제로 되는지.

가짜 호출이 아니라 진짜 server.py를 띄웠다 죽였다 하면서, GUI가
(1) 끊긴 걸 화면에 알리는지 (2) 스스로 다시 붙는지 (3) 보던 채널로 돌아가는지
(4) 돌아가면서 지난 대화를 두 번 쌓지 않는지를 확인한다.
"""
import os as _os
import sys as _sys

_HERE = _os.path.dirname(_os.path.abspath(__file__))
_REPO = _os.path.dirname(_HERE)

import os
import subprocess
import sys
import time

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, _REPO)

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

import gui_client

CHAT_DIR = _REPO
PLAIN_PORT = "17667"
SSL_PORT = "17697"
CHANNEL = "recon_chan"
USER = "reconu" + str(int(time.time()))


def start_server():
    proc = subprocess.Popen(
        [sys.executable, "server.py", PLAIN_PORT, SSL_PORT],
        cwd=CHAT_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    time.sleep(1.5)
    # 예전 세션의 서버가 포트를 잡고 있으면 우리가 띄운 건 조용히 죽고, 테스트는
    # "안 죽는 서버"에 붙어서 엉뚱하게 통과/실패함(실제로 한 번 헤맴)
    if proc.poll() is not None:
        raise SystemExit(f"server.py가 즉시 종료됨(포트 {PLAIN_PORT} 사용 중일 가능성)")
    return proc


def pump(app, seconds, until=None):
    """이벤트 루프를 실제로 돌림. until()이 참이 되면 즉시 반환."""
    deadline = time.monotonic() + seconds
    state = {"done": False}

    def tick():
        if (until is not None and until()) or time.monotonic() > deadline:
            state["done"] = True
            app.quit()

    timer = QTimer()
    timer.timeout.connect(tick)
    timer.start(80)
    app.exec()
    timer.stop()
    return state["done"]


def channel_text(window, channel):
    view = window.chat_page._log_views[channel]
    parts = []
    for child in view.findChildren(object):
        text = getattr(child, "text", None)
        if callable(text):
            try:
                parts.append(text())
            except TypeError:
                pass
    return "\n".join(p for p in parts if isinstance(p, str))


app = QApplication.instance() or QApplication(sys.argv)
server = start_server()
window = gui_client.MainWindow()
window.show()
app.processEvents()

lp = window.login_page
lp.protocol_combo.setCurrentIndex(lp.protocol_combo.findData("custom"))
lp.host_input.setText("127.0.0.1")
lp.port_input.setText(PLAIN_PORT)
lp.ssl_checkbox.setChecked(False)
lp.user_input.setText(USER)
lp.pw_input.setText("pw1234")
window._handle_login_submit("register")
pump(app, 10, lambda: "회원가입 완료" in lp.status_label.text() or "이미 존재" in lp.status_label.text())
print("register 상태:", lp.status_label.text())

window._handle_login_submit("login")
pump(app, 10, lambda: window.stack.currentWidget() is window.channel_page)
print("login 상태:", lp.status_label.text(), "/ 화면:", window.stack.currentWidget().objectName() or type(window.stack.currentWidget()).__name__)

window.channel_page.channel_input.setText(CHANNEL)
window._handle_channel_submit("create")
pump(app, 6, lambda: "생성 완료" in window.channel_page.status_label.text()
     or "이미 존재" in window.channel_page.status_label.text())
print("채널 생성 상태:", window.channel_page.status_label.text())
window._handle_channel_submit("join")
pump(app, 10, lambda: window.stack.currentWidget() is window.chat_page)
print("입장 상태:", window.channel_page.status_label.text(), "/ 열린 채널:", window.chat_page.open_channels())

window._handle_send(CHANNEL, "재접속 전 메시지")
pump(app, 1.5)

before = channel_text(window, CHANNEL)
print("로그인/입장 완료. 채널:", window.chat_page.open_channels())

# ---- 1) 서버를 죽인다 ----
server.terminate()
server.wait(timeout=10)
pump(app, 3, lambda: window._reconnect.active)

notified = channel_text(window, CHANNEL)
dropped_shown = "연결이 끊어졌습니다" in notified
retry_shown = "다시 연결 시도" in notified
print(f"끊김 감지: reconnecting={window._reconnect.active} attempt={window._reconnect.attempt}")
print(f"기억해둔 채널: {window._reconnect.pending_channels}")

# 서버가 없는 동안 재시도가 실제로 반복되는지(간격이 늘어나는지)
pump(app, 9)
attempts_while_down = window._reconnect.attempt
print("서버 죽어있는 동안 시도 횟수:", attempts_while_down)

# ---- 2) 서버를 다시 띄운다 ----
server = start_server()
reconnected = pump(app, 45, lambda: not window._reconnect.active and bool(window.session.my_id))
pump(app, 3)

after = channel_text(window, CHANNEL)
rejoined = CHANNEL in window.session.joined_channels
back_shown = "다시 연결되었습니다" in after

# 재입장하면서 지난 기록을 또 쌓지 않았는지 - 같은 문구가 두 번 나오면 실패
history_dupes = after.count("이전 대화 기록")
msg_count = after.count("재접속 전 메시지")
before_msg_count = before.count("재접속 전 메시지")
print(f"'이전 대화 기록' 표시 {history_dupes}회 / '재접속 전 메시지' 끊기기 전 {before_msg_count}회"
      f" -> 재접속 후 {msg_count}회")
print(f"입장 안내 '{CHANNEL}' 관련 줄 수: {after.count('입장했습니다')}")

# ---- 3) 다시 붙은 뒤 실제로 메시지가 오가는지 ----
window._handle_send(CHANNEL, "재접속 후 메시지")
pump(app, 2.5)
final = channel_text(window, CHANNEL)
can_chat = "재접속 후 메시지" in final

# ---- 4) 일부러 끊는 경우엔 재접속하지 않아야 함 ----
window._handle_back_to_login()
pump(app, 2.5)
no_reconnect_on_logout = not window._reconnect.active and not window._reconnect._timer.isActive()

window.client.abort()
server.terminate()

checks = [
    ("끊기면 채팅창에 끊김 안내가 뜬다", dropped_shown),
    ("재시도 안내가 뜬다", retry_shown),
    ("끊긴 채널을 기억해둔다", CHANNEL in (window._reconnect.pending_channels or [CHANNEL]) or rejoined),
    ("서버가 없는 동안 계속 재시도한다(2회 이상)", attempts_while_down >= 2),
    ("서버가 살아나면 스스로 다시 붙는다", reconnected),
    ("다시 연결됐다는 안내가 뜬다", back_shown),
    ("보던 채널로 다시 들어간다", rejoined),
    ("지난 대화를 두 번 쌓지 않는다(끊기기 전과 같은 개수)",
     history_dupes <= 1 and msg_count == before_msg_count),
    ("재접속 후 채팅이 실제로 된다", can_chat),
    ("로그아웃은 재접속을 유발하지 않는다", no_reconnect_on_logout),
]

print("\n=== 검증 결과 (자동 재접속) ===")
all_ok = True
for name, ok in checks:
    print(f"[{'OK' if ok else 'FAIL'}] {name}")
    all_ok = all_ok and ok
print("\n전체 통과:", all_ok)
sys.exit(0 if all_ok else 1)
