import os as _os
import sys as _sys

_HERE = _os.path.dirname(_os.path.abspath(__file__))
_REPO = _os.path.dirname(_HERE)
import os
import sys
import time

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, _REPO)

from PySide6.QtWidgets import QApplication, QLabel
from PySide6.QtCore import QTimer
import gui_client as g
from gui.components.message_text import MessageText


def pump(seconds):
    app = QApplication.instance()
    state = {"start": time.monotonic()}
    def poll():
        if time.monotonic() - state["start"] > seconds:
            app.quit()
    timer = QTimer()
    timer.timeout.connect(poll)
    timer.start(100)
    app.exec()
    timer.stop()


def channel_texts(window, channel):
    """그 채널에 보이는 모든 글자(메시지 + 시스템 안내)를 합쳐서 반환.

    메시지 본문은 텍스트 엔진 위젯(MessageText)이 그리고, 시스템 안내만 라벨이다.
    """
    view = window.chat_page._log_views.get(channel)
    if view is None:
        return ""
    texts = []
    for label in view.findChildren(QLabel):
        if label.objectName() == "timestampBadge":
            continue
        texts.append(label.text())
    for body in view.findChildren(MessageText):
        texts.append(body.text())
    return "\n".join(texts)
    texts = []
    for label in view.findChildren(QLabel):
        if label.objectName() == "timestampBadge":
            continue
        texts.append(label.text())
    return "\n".join(texts)


def run_custom_client(username, first_channel, create_first, port="17667"):
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyleSheet(g.STYLE_SHEET)
    window = g.MainWindow()
    window.show()
    app.processEvents()

    lp = window.login_page
    lp.protocol_combo.setCurrentIndex(lp.protocol_combo.findData("custom"))
    lp.host_input.setText("127.0.0.1")
    lp.port_input.setText(port)
    lp.ssl_checkbox.setChecked(False)
    lp.user_input.setText(username)
    lp.pw_input.setText("pw1234")
    window._handle_login_submit("register")

    state = {"phase": "register", "start": time.monotonic()}

    def poll():
        elapsed = time.monotonic() - state["start"]
        status = lp.status_label.text()
        if state["phase"] == "register":
            if "회원가입 완료" in status or "이미 존재하는" in status:
                state["phase"] = "login"
                state["start"] = time.monotonic()
                window._handle_login_submit("login")
            return
        if state["phase"] == "login" and window.stack.currentWidget() is window.channel_page:
            state["phase"] = "channel_action"
            window.channel_page.channel_input.setText(first_channel)
            window._handle_channel_submit("create" if create_first else "join")
            state["start"] = time.monotonic()
            return
        if state["phase"] == "channel_action" and create_first and "채널 생성 완료" in window.channel_page.status_label.text():
            state["phase"] = "join"
            window._handle_channel_submit("join")
            state["start"] = time.monotonic()
            return
        if state["phase"] in ("channel_action", "join") and window.stack.currentWidget() is window.chat_page:
            state["phase"] = "done"
            app.quit()
            return
        if elapsed > 12:
            state["phase"] = "timeout"
            app.quit()

    timer = QTimer()
    timer.timeout.connect(poll)
    timer.start(150)
    app.exec()
    return window, state["phase"]


def add_channel(window, channel, key=""):
    # gui_client._handle_add_channel()은 QInputDialog가 아니라 자체 themed_get_text()를
    # 쓰므로(프레임리스 다이얼로그 테마 통일 작업 이후) 그쪽을 몽키패치해야 함 -
    # 예전처럼 QInputDialog.getText를 패치하면 실제 모달이 떠서 응답 없이 무한 대기(exec()) 함
    orig = g.themed_get_text
    answers = iter([(channel, True), (key, True)])
    g.themed_get_text = lambda *a, **k: next(answers)
    window._handle_add_channel()
    g.themed_get_text = orig
    state = {"start": time.monotonic()}
    app = QApplication.instance()
    def poll():
        if channel in window.chat_page._log_views or time.monotonic() - state["start"] > 8:
            app.quit()
    timer = QTimer()
    timer.timeout.connect(poll)
    timer.start(150)
    app.exec()
    timer.stop()


def send_in(window, channel, text):
    window.chat_page.set_active_channel(channel)
    window._handle_send(channel, text)
    pump(1.0)


checks = []
ts = int(time.time())

# ===== 다중 채널 (커스텀 프로토콜) =====
winA, phaseA = run_custom_client(f"regA{ts}", "regchanA", True)
add_channel(winA, "regchanB")  # 존재 안 하는 채널이라 실패할 것 (아래에서 만든 뒤 재시도)

winB, phaseB = run_custom_client(f"regB{ts}", "regchanB", True)
pump(0.5)

add_channel(winA, "regchanB")
checks.append(("A: 다중 채널 재시도 후 두 채널 다 있음", "regchanA" in winA.chat_page._log_views and "regchanB" in winA.chat_page._log_views))

send_in(winA, "regchanA", "only in A msg")
send_in(winA, "regchanB", "shared B msg")
send_in(winB, "regchanB", "b says hi")
pump(1.0)

textA_a = channel_texts(winA, "regchanA")
textA_b = channel_texts(winA, "regchanB")
textB_b = channel_texts(winB, "regchanB")

checks.append(("A: regchanA 로그에 해당 메시지 있음", "only in A msg" in textA_a))
checks.append(("A: regchanB 로그에 격리된 메시지 없음", "only in A msg" not in textA_b))
checks.append(("B: regchanB에서 A의 메시지 수신", "shared B msg" in textB_b))
checks.append(("A: regchanB에서 B의 메시지 수신", "b says hi" in textA_b))

winA.client.abort()
winB.client.abort()
pump(0.3)

print("\n=== 검증 결과 (다중 채널, 새 위젯 기반) ===")
all_ok = True
for name, ok in checks:
    print(f"[{'OK' if ok else 'FAIL'}] {name}")
    all_ok = all_ok and ok
print("전체 통과:", all_ok)
