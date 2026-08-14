"""`_`가 붙었다가 원래 이름으로 돌아오는지 실제 서버에서 확인한다.

만드는 상황:
1. 다른 접속이 그 이름을 먼저 쥐고 있다(회선이 끊긴 유령과 서버 입장에서는 같다)
2. 우리 앱이 같은 이름으로 접속 -> 이름이 밀려 `이름_`이 된다
3. 먼저 있던 쪽이 사라진다(유령이라면 서버가 180초 뒤 정리하는 그 순간)
4. **우리 앱이 스스로 원래 이름을 되찾는가**, 그리고 몇 초 걸리는가
"""
import os
import socket
import sys
import time

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PySide6.QtWidgets import QApplication

app = QApplication([])
import gui_client as g

HOST, PORT, NICK = "home.pdlab.kr", 6667, "chupname"


def pump(seconds):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.01)


# 1) 먼저 그 이름을 쥔다(다른 프로그램인 척)
holder = socket.create_connection((HOST, PORT), timeout=10)
holder.settimeout(0.5)
holder.sendall(f"NICK {NICK}\r\nUSER {NICK} 0 * :{NICK}\r\n".encode())


def drain(sock, seconds):
    end = time.time() + seconds
    buf = b""
    while time.time() < end:
        try:
            chunk = sock.recv(4096)
            if not chunk:
                return
            buf += chunk
        except socket.timeout:
            continue
        while b"\r\n" in buf:
            raw, buf = buf.split(b"\r\n", 1)
            text = raw.decode("utf-8", "replace")
            if text.startswith("PING"):
                sock.sendall(("PONG :" + text.split(":", 1)[-1] + "\r\n").encode())


drain(holder, 4)
print(f"1) 다른 접속이 '{NICK}'을 쥐고 있음")

# 2) 우리 앱으로 같은 이름 접속
window = g.MainWindow()
window.show()
page = window.login_page
page.protocol_combo.setCurrentIndex(page.protocol_combo.findData("irc"))
page.host_input.setText(HOST)
page.port_input.setText(str(PORT))
page.ssl_checkbox.setChecked(False)
page.user_input.setText(NICK)
page.pw_input.setText("")
window._handle_login_submit("login")
pump(6)
print(f"2) 우리 앱이 접속한 이름: {window.session.my_id}"
      f"  (원하는 이름: {window.session.wanted_nick})")

# 3) 먼저 있던 쪽이 사라진다
holder.sendall("QUIT :자리 비켜줌\r\n".encode())
time.sleep(0.3)
holder.close()
print("3) 먼저 있던 접속이 사라짐 - 이제 되찾아야 한다")

# 4) 언제 되찾는지 잰다
started = time.time()
while time.time() - started < 90:
    app.processEvents()
    time.sleep(0.02)
    if window.session.my_id == NICK:
        break
    # 창이 떠 있는 동안 도는 타이머를 흉내(15초마다 확인)
    if int(time.time() - started) % 15 == 0:
        window._check_connection_alive()
        time.sleep(0.05)

took = time.time() - started
if window.session.my_id == NICK:
    print(f"4) 되찾음: '{window.session.my_id}'  ({took:.0f}초 걸림)")
else:
    print(f"4) 90초 동안 못 되찾음(지금 이름: {window.session.my_id})")
    print(f"   시도 횟수: {window.session.nick_reclaim_attempts}")

window._say_goodbye("진단 끝")
pump(1)
