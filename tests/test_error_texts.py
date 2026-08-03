"""상황별 안내/오류 문구 전수 검증.

"로그인은 되는데 접속 안 된다고 뜬다"는 제보를 재현하려고, 로그인 전 과정에서 화면에
표시된 모든 상태 문구를 순서대로 기록해서 확인한다.
"""
import os as _os
import sys as _sys

_HERE = _os.path.dirname(_os.path.abspath(__file__))
_REPO = _os.path.dirname(_HERE)

import os
import sys
import time

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, _REPO)
os.chdir(_REPO)

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
import gui_client as g

app = QApplication(sys.argv)
app.setStyleSheet(g.STYLE_SHEET)
checks = []
TS = int(time.time())


def make_window():
    """상태 문구가 바뀔 때마다 전부 기록하는 창"""
    w = g.MainWindow()
    seen = []
    orig_login = w.login_page.show_status
    orig_channel = w.channel_page.show_status

    def rec_login(text, error=True):
        if text:
            seen.append(("login", text))
        orig_login(text)

    def rec_channel(text, error=True):
        if text:
            seen.append(("channel", text))
        orig_channel(text)

    w.login_page.show_status = rec_login
    w.channel_page.show_status = rec_channel
    w.show()
    w._go_to_login()
    app.processEvents()
    return w, seen


def run_until(w, cond, timeout=12.0):
    start = time.time()
    while time.time() - start < timeout:
        app.processEvents()
        if cond():
            return True
        time.sleep(0.02)
    return False


def fill(w, host, port, user, pw, ssl=False, protocol="custom"):
    lp = w.login_page
    lp.protocol_combo.setCurrentIndex(lp.protocol_combo.findData(protocol))
    lp.host_input.setText(host)
    lp.port_input.setText(str(port))
    lp.ssl_checkbox.setChecked(ssl)
    lp.user_input.setText(user)
    lp.pw_input.setText(pw)
    lp.auto_login_checkbox.setChecked(False)


def err_texts(seen):
    """'실패/오류' 계열 문구만.

    "연결 중... (언제든 '연결 취소' 가능)"처럼 안내문에 들어있는 '취소'는 오류가 아니므로
    제외해야 함 - 처음에 '취소'를 오류 단어로 넣었다가 정상 로그인이 실패로 잡혔었음."""
    bad_words = ("실패", "오류", "초과", "일치하지", "존재하지")
    return [t for _, t in seen if any(b in t for b in bad_words)]


# ===== 1) 평문 정상 로그인: 성공했는데 실패 문구가 뜨면 안 됨 =====
w, seen = make_window()
fill(w, "127.0.0.1", 17667, f"errA{TS}", "pw1234")
w._handle_login_submit("register")
run_until(w, lambda: any("회원가입" in t for _, t in seen))
w._handle_login_submit("login")
ok = run_until(w, lambda: w.stack.currentWidget() is w.channel_page)
checks.append(("평문 정상 로그인 성공", ok))
bad = err_texts(seen)
checks.append((f"성공 로그인 중 실패/오류 문구 안 뜸 (관측: {bad})", not bad))
w.client.abort()
app.processEvents()

# ===== 2) SSL 정상 로그인 (자체서명 인증서 - 여기서 오탐이 잘 남) =====
w2, seen2 = make_window()
fill(w2, "127.0.0.1", 17697, f"errB{TS}", "pw1234", ssl=True)
w2._handle_login_submit("register")
run_until(w2, lambda: any("회원가입" in t for _, t in seen2))
w2._handle_login_submit("login")
ok2 = run_until(w2, lambda: w2.stack.currentWidget() is w2.channel_page)
checks.append(("SSL 정상 로그인 성공", ok2))
bad2 = err_texts(seen2)
checks.append((f"SSL 성공 로그인 중 실패/오류 문구 안 뜸 (관측: {bad2})", not bad2))
w2.client.abort()
app.processEvents()

# ===== 3) 비밀번호 틀림 -> 서버가 준 문구가 그대로 =====
w3, seen3 = make_window()
fill(w3, "127.0.0.1", 17667, f"errC{TS}", "pw1234")
w3._handle_login_submit("register")
run_until(w3, lambda: any("회원가입" in t for _, t in seen3))
seen3.clear()
w3.login_page.pw_input.setText("WRONGPW")
w3._handle_login_submit("login")
run_until(w3, lambda: any("일치" in t or "실패" in t or "없" in t for _, t in seen3))
login_errs = [t for src, t in seen3 if src == "login"]
checks.append((f"틀린 비밀번호 안내가 표시됨 (관측: {login_errs[-1:]})",
               any(("비밀번호" in t or "일치" in t or "실패" in t) for t in login_errs)))
checks.append(("틀린 비밀번호일 때 로그인 화면에 머무름", w3.stack.currentWidget() is w3.login_page))
w3.client.abort()
app.processEvents()

# ===== 4) 없는 서버 -> 연결 실패 안내 =====
w4, seen4 = make_window()
fill(w4, "127.0.0.1", 59999, "nobody", "pw")
w4._handle_login_submit("login")
run_until(w4, lambda: any(("연결" in t and ("실패" in t or "초과" in t)) for _, t in seen4), timeout=14)
conn_errs = [t for _, t in seen4 if "연결" in t and ("실패" in t or "초과" in t)]
checks.append((f"연결 불가 시 안내 표시 (관측: {conn_errs[-1:]})", bool(conn_errs)))
w4.client.abort()
app.processEvents()

# ===== 5) 입력 누락 안내 =====
w5, seen5 = make_window()
fill(w5, "", "", "", "")
w5._handle_login_submit("login")
app.processEvents()
checks.append((f"항목 누락 시 안내 (관측: {[t for _, t in seen5][-1:]})",
               any("입력" in t for _, t in seen5)))

# ===== 6) 포트가 숫자가 아님 =====
w6, seen6 = make_window()
fill(w6, "127.0.0.1", "abc", "u", "p")
w6._handle_login_submit("login")
app.processEvents()
checks.append((f"포트 비숫자 안내 (관측: {[t for _, t in seen6][-1:]})",
               any("숫자" in t for _, t in seen6)))

# ===== 7) 로그아웃 후 이전 오류 문구가 남지 않아야 함 =====
w7, seen7 = make_window()
w7.login_page.show_status("연결 실패: 이전 오류")
app.processEvents()
w7._handle_back_to_login()
app.processEvents()
checks.append(("로그아웃하면 이전 오류 문구가 지워짐", w7.login_page.status_label.text() == ""))

print("\n=== 검증 결과 (상황별 안내/오류 문구) ===")
all_ok = True
for name, ok in checks:
    print(f"[{'OK' if ok else 'FAIL'}] {name}")
    all_ok = all_ok and ok
print("전체 통과:", all_ok)
