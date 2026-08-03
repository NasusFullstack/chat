import os as _os
import sys as _sys

_HERE = _os.path.dirname(_os.path.abspath(__file__))
_REPO = _os.path.dirname(_HERE)
import os, sys, time
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, _REPO)

PREFS_FILE = _os.path.join(_REPO, "login_prefs.json")
if os.path.exists(PREFS_FILE):
    os.remove(PREFS_FILE)

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
import login_prefs
import gui_client as g

app = QApplication(sys.argv)
app.setStyleSheet(g.STYLE_SHEET)

checks = []
PORT = "17667"
ts = int(time.time())
username = f"autologin{ts}"


def pump(seconds):
    state = {"start": time.monotonic()}
    def poll():
        if time.monotonic() - state["start"] > seconds:
            app.quit()
    timer = QTimer()
    timer.timeout.connect(poll)
    timer.start(100)
    app.exec()
    timer.stop()


def run_login(username, password, protocol="custom", auto_login=False, mode="register_then_login"):
    window = g.MainWindow()
    window.show()
    app.processEvents()
    lp = window.login_page
    lp.protocol_combo.setCurrentIndex(lp.protocol_combo.findData(protocol))
    lp.host_input.setText("127.0.0.1")
    lp.port_input.setText(PORT)
    lp.ssl_checkbox.setChecked(False)
    lp.user_input.setText(username)
    lp.pw_input.setText(password)
    lp.auto_login_checkbox.setChecked(auto_login)

    state = {"phase": "register" if mode == "register_then_login" else "login", "start": time.monotonic()}
    if mode == "register_then_login":
        window._handle_login_submit("register")
    else:
        window._handle_login_submit("login")

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
    timer.stop()
    return window, state["phase"]


# ===== 1) login_prefs.py 기본 저장/로드 =====
login_prefs.save({"user_id": "x", "password": "y", "auto_login": True})
loaded = login_prefs.load()
checks.append(("login_prefs 기본 저장/로드", loaded.get("user_id") == "x" and loaded.get("password") == "y"))
if os.path.exists(PREFS_FILE):
    os.remove(PREFS_FILE)

# ===== 2) 자동로그인 체크 안 하고 로그인 성공 -> 비밀번호는 저장 안 되고 아이디만 기억 =====
winA, phaseA = run_login(username, "pw1234", auto_login=False)
checks.append(("A: 로그인 성공(체크박스 꺼짐)", phaseA == "done"))
prefsA = login_prefs.load()
checks.append(("A: 아이디는 기억됨", prefsA.get("user_id") == username))
checks.append(("A: 비밀번호는 저장 안 됨(체크 안 했으므로)", "password" not in prefsA))
checks.append(("A: auto_login 플래그가 False로 저장됨", prefsA.get("auto_login") is False))
winA.client.abort()
pump(0.3)

# ===== 3) 같은 계정으로 자동로그인 체크하고 다시 로그인 -> 이번엔 비밀번호까지 저장 =====
winB, phaseB = run_login(username, "pw1234", auto_login=True, mode="login_only")
checks.append(("B: 로그인 성공(체크박스 켜짐)", phaseB == "done"))
prefsB = login_prefs.load()
checks.append(("B: auto_login 플래그가 True로 저장됨", prefsB.get("auto_login") is True))
checks.append(("B: 비밀번호까지 저장됨", prefsB.get("password") == "pw1234"))
winB.client.abort()
pump(0.3)

# ===== 4) 새 창(=재시작 시뮬레이션)을 열면 로그인 화면에 아이디/비번이 미리 채워지고,
#          체크박스도 켜져 있어야 함 =====
winC = g.MainWindow()
winC.show()
app.processEvents()
lpC = winC.login_page
checks.append(("C(재시작 시뮬레이션): 아이디 미리 채워짐", lpC.user_input.text() == username))
checks.append(("C: 비밀번호도 미리 채워짐", lpC.pw_input.text() == "pw1234"))
checks.append(("C: 자동로그인 체크박스가 켜진 채로 시작함", lpC.auto_login_checkbox.isChecked()))

# ===== 5) _maybe_auto_login이 실제로 로그인을 자동 제출해서 채널 화면까지 도달하는지 =====
state = {"start": time.monotonic()}
def poll_auto():
    if winC.stack.currentWidget() is winC.channel_page:
        app.quit()
        return
    if time.monotonic() - state["start"] > 12:
        app.quit()
timer = QTimer()
timer.timeout.connect(poll_auto)
timer.start(150)
winC._maybe_auto_login()
app.exec()
timer.stop()
checks.append(("C: _maybe_auto_login 호출만으로 실제 로그인 성공(채널 화면 도달)",
               winC.stack.currentWidget() is winC.channel_page))
winC.client.abort()
pump(0.3)

# ===== 6) 저장된 게 없으면 _maybe_auto_login이 아무 일도 안 함(가만히 로그인 화면에 남아있음) =====
if os.path.exists(PREFS_FILE):
    os.remove(PREFS_FILE)
winD = g.MainWindow()
winD.show()
app.processEvents()
# 시작화면이 생기면서 앱은 startup_page에서 시작함 - 부팅 흐름이 로그인 화면으로
# 넘겨준 상태를 재현한 뒤에 자동로그인이 안 걸리는지 확인
winD._go_to_login()
app.processEvents()
checks.append(("D: 부팅 후 로그인 화면으로 넘어감", winD.stack.currentWidget() is winD.login_page))
winD._maybe_auto_login()
app.processEvents()
checks.append(("D: 저장된 자동로그인 정보 없으면 로그인 화면에 그대로 남아있음",
               winD.stack.currentWidget() is winD.login_page))

if os.path.exists(PREFS_FILE):
    os.remove(PREFS_FILE)

print("\n=== 검증 결과 (자동로그인 기능) ===")
all_ok = True
for name, ok in checks:
    print(f"[{'OK' if ok else 'FAIL'}] {name}")
    all_ok = all_ok and ok
print("전체 통과:", all_ok)
