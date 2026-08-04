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
from PySide6.QtNetwork import QSslSocket
import gui_client as g

PORT = "16700"
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


def run_irc_client(nick, channel):
    app = QApplication.instance() or QApplication(sys.argv)
    window = g.MainWindow()
    window.show()
    app.processEvents()
    lp = window.login_page
    lp.protocol_combo.setCurrentIndex(lp.protocol_combo.findData("irc"))
    lp.host_input.setText("127.0.0.1")
    lp.port_input.setText(PORT)
    lp.ssl_checkbox.setChecked(False)
    lp.user_input.setText(nick)
    lp.pw_input.setText("")
    window._handle_login_submit("login")

    state = {"phase": "login", "start": time.monotonic()}

    def poll():
        elapsed = time.monotonic() - state["start"]
        if state["phase"] == "login" and window.stack.currentWidget() is window.channel_page:
            state["phase"] = "join"
            window.channel_page.channel_input.setText(channel)
            window._handle_channel_submit("join")
            state["start"] = time.monotonic()
            return
        if state["phase"] == "join" and window.stack.currentWidget() is window.chat_page:
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


channel = "#profnick"

winA, phaseA = run_irc_client("ircprofA", channel)
winB, phaseB = run_irc_client("ircprofB", channel)
checks.append(("A/B 둘 다 IRC 채팅방 진입", phaseA == "done" and phaseB == "done"))
pump(0.5)

# ---- A가 프로필 다이얼로그에서 새 닉네임으로 변경 -> NICK 전송 -> 서버 확정 후 my_id 갱신 ----
def fake_exec(self):
    self._nickname_input.setText("ircprofA_renamed")
    self._on_save()
    return QDialog.DialogCode.Accepted
orig_exec = g.ProfileDialog.exec
g.ProfileDialog.exec = fake_exec
winA._handle_set_avatar()
g.ProfileDialog.exec = orig_exec
pump(1.0)

checks.append(("IRC 닉네임 변경 성공 시 my_id가 갱신됨", winA.my_id == "ircprofA_renamed"))
checks.append(("chat_page.my_id도 함께 갱신됨", winA.chat_page.my_id == "ircprofA_renamed"))
checks.append(("_nick_change_pending 플래그가 확정 후 해제됨", winA.session.nick_change_pending is False))

# B 쪽에서도 상대 닉네임 변경을 참여자 목록에 반영했는지
# (멤버 추적은 이제 도메인 코어(session.members)가 담당 - 예전 MainWindow._irc_members는 없어짐)
b_members = winB.session.members.get(channel, set())
checks.append(("상대(B)의 참여자 목록에도 바뀐 닉네임이 반영됨", "ircprofA_renamed" in b_members and "ircprofA" not in b_members))

# 코어 상태뿐 아니라 실제 화면(참여자 목록 위젯)에도 반영됐는지까지 확인
b_visible = [winB.chat_page.member_panel.list.item(i).text() for i in range(winB.chat_page.member_panel.list.count())]
checks.append(("B의 화면 참여자 목록 위젯에도 바뀐 닉네임이 보임",
               "ircprofA_renamed" in b_visible and "ircprofA" not in b_visible))

# ---- 닉네임 충돌(이미 사용 중) 시 연결이 끊기지 않고 경고만 뜨는지 ----
warned = {"called": False}
orig_warning = g.themed_warning
def fake_warning(*a, **k):
    warned["called"] = True
g.themed_warning = fake_warning

def fake_exec_collision(self):
    self._nickname_input.setText("ircprofB")  # B가 이미 쓰고 있는 닉네임 - 충돌 유발
    self._on_save()
    return QDialog.DialogCode.Accepted
g.ProfileDialog.exec = fake_exec_collision
winA._handle_set_avatar()
g.ProfileDialog.exec = orig_exec
pump(1.0)
g.themed_warning = orig_warning

checks.append(("닉네임 충돌 시 경고 다이얼로그가 뜸", warned["called"]))
checks.append(("닉네임 충돌 시에도 연결이 끊기지 않음(여전히 채팅 화면)",
               winA.stack.currentWidget() is winA.chat_page))
checks.append(("충돌 후에도 소켓이 여전히 연결 상태", winA.client.state() == QSslSocket.SocketState.ConnectedState))
checks.append(("충돌한 닉네임으로는 my_id가 바뀌지 않음(기존 이름 유지)", winA.my_id == "ircprofA_renamed"))

winA.client.abort()
winB.client.abort()

print("\n=== 검증 결과 (IRC 프로필/닉네임 변경) ===")
all_ok = True
for name, ok in checks:
    print(f"[{'OK' if ok else 'FAIL'}] {name}")
    all_ok = all_ok and ok
print("전체 통과:", all_ok)
