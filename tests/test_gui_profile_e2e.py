import os as _os
import sys as _sys

_HERE = _os.path.dirname(_os.path.abspath(__file__))
_REPO = _os.path.dirname(_HERE)
import os
import sys
import time

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, _REPO)

from PySide6.QtWidgets import QApplication, QDialog, QMessageBox
from PySide6.QtCore import QTimer
import gui_client as g

PORT_PLAIN = 17667
IRC_PORT = "16700"

checks = []


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


def run_custom_login(user_id):
    app = QApplication.instance() or QApplication(sys.argv)
    window = g.MainWindow()
    window.show()
    app.processEvents()
    lp = window.login_page
    lp.protocol_combo.setCurrentIndex(lp.protocol_combo.findData("custom"))
    lp.host_input.setText("127.0.0.1")
    lp.port_input.setText(str(PORT_PLAIN))
    lp.ssl_checkbox.setChecked(False)
    lp.user_input.setText(user_id)
    lp.pw_input.setText("pw1234")
    window._handle_login_submit("register")

    result = {"phase": "register", "start": time.monotonic()}

    def poll():
        elapsed = time.monotonic() - result["start"]
        status = lp.status_label.text()
        if result["phase"] == "register" and "회원가입 완료" in status:
            result["phase"] = "login"
            result["start"] = time.monotonic()
            window._handle_login_submit("login")
            return
        if window.stack.currentWidget() is window.channel_page or elapsed > 6:
            result["done"] = window.stack.currentWidget() is window.channel_page
            app.quit()

    timer = QTimer()
    timer.timeout.connect(poll)
    timer.start(150)
    app.exec()
    timer.stop()
    return window, result.get("done", False)


suffix = str(int(time.time()))
channel = f"#profe2e{suffix}"

winA, okA = run_custom_login(f"profA{suffix}")
checks.append(("커스텀 프로토콜 로그인 성공(A)", okA))
winA.channel_page.channel_input.setText(channel)
winA._handle_channel_submit("create")
pump(0.5)
winA._handle_channel_submit("join")
pump(0.5)
checks.append(("A가 채팅방 진입", winA.stack.currentWidget() is winA.chat_page))

# ---- 프로필 변경 다이얼로그를 흉내내서 _handle_set_avatar 경로 전체를 검증 (닉네임+아이콘 함께 전송) ----
orig_exec = g.ProfileDialog.exec
def fake_exec(self):
    self._nickname_input.setText("에이변경닉")
    self._on_save()
    return QDialog.DialogCode.Accepted
g.ProfileDialog.exec = fake_exec
winA._handle_set_avatar()
g.ProfileDialog.exec = orig_exec
pump(0.5)

checks.append(("프로필 변경 후 로컬(A)에 닉네임 낙관적 반영", winA.chat_page.member_panel._nicknames.get(winA.my_id) == "에이변경닉"))

winB, okB = run_custom_login(f"profB{suffix}")
checks.append(("커스텀 프로토콜 로그인 성공(B)", okB))
winB.channel_page.channel_input.setText(channel)
winB._handle_channel_submit("join")
pump(1.0)
checks.append(("B가 채팅방 진입 후 A의 변경된 닉네임을 캐치업으로 받음",
               winB.chat_page.member_panel._nicknames.get(winA.my_id) == "에이변경닉"))

winA.client.abort()
winB.client.abort()

print("\n=== 검증 결과 (커스텀 프로토콜 프로필 변경 E2E) ===")
all_ok = True
for name, ok in checks:
    print(f"[{'OK' if ok else 'FAIL'}] {name}")
    all_ok = all_ok and ok
print("전체 통과:", all_ok)
