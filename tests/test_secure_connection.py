"""보안 접속(TLS)이 기본이고, 자체 서명 인증서 서버에도 붙을 수 있는가.

무엇이 문제였나: 앱이 IRC 모드에서 **무조건 정식 CA 검증**을 요구해서, 개인이 돌리는
서버의 보안 포트에 아예 못 붙었다(실측: home.pdlab.kr:6697은 TLS 1.3이 열려 있는데
"The host name did not match any of the valid hosts for this certificate"로 끊겼다).
그래서 다들 평문(6667)으로 붙고 있었고, 비밀번호와 대화가 그대로 오갔다.

지금은 다른 IRC 클라이언트처럼 **한 번 묻고 기억한다**:
- 검증에 실패하면 지문을 보여주고 신뢰할지 묻는다
- 신뢰하면 그 지문을 적어두고 다음부터는 조용히 붙는다
- **지문이 바뀌면 다시 묻는다**(서버가 바뀌었거나 누가 중간에 낀 것이므로)
"""
import os as _os
import sys as _sys

_HERE = _os.path.dirname(_os.path.abspath(__file__))
_REPO = _os.path.dirname(_HERE)

_os.environ["QT_QPA_PLATFORM"] = "offscreen"
_sys.path.insert(0, _REPO)

import io  # noqa: E402
import tempfile  # noqa: E402

from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])

import login_prefs  # noqa: E402
import trusted_certs  # noqa: E402
import gui_client as g  # noqa: E402

checks = []


def check(name, ok, detail=""):
    checks.append((name, ok, detail))


# ---------- 1) 기본이 보안 접속인가 ----------
window = g.MainWindow()
page = window.login_page
check(f"기본으로 보안 접속을 켠다({page.ssl_checkbox.isChecked()})",
      page.ssl_checkbox.isChecked() is True, page.ssl_checkbox.isChecked())
check(f"기본 포트가 보안 포트({page.port_input.text()})",
      page.port_input.text() == g.DEFAULT_SSL_PORT, page.port_input.text())

# ---------- 2) 예전에 평문으로 쓰던 사람도 옮겨준다 ----------
check("평문으로 저장된 접속은 보안 접속으로 올린다",
      login_prefs.upgrade_to_secure({"host": "home.pdlab.kr", "port": "6667", "ssl": False})
      == {"host": "home.pdlab.kr", "port": "6697", "ssl": True})
check("이미 보안 접속이면 그대로 둔다",
      login_prefs.upgrade_to_secure({"host": "h", "port": "6697", "ssl": True})
      == {"host": "h", "port": "6697", "ssl": True})
check("직접 넣은 포트는 건드리지 않는다",
      login_prefs.upgrade_to_secure({"host": "h", "port": "7777", "ssl": False})
      == {"host": "h", "port": "7777", "ssl": False})

# ---------- 3) 신뢰한 인증서를 기억하는가 ----------
trusted_certs.STORE_FILE = _os.path.join(tempfile.gettempdir(), "chup_trust_test.json")
if _os.path.exists(trusted_certs.STORE_FILE):
    _os.remove(trusted_certs.STORE_FILE)

check("처음에는 아는 인증서가 없다", trusted_certs.fingerprint_of("h", 6697) == "")
trusted_certs.trust("h", 6697, "abcdef123456")
check("신뢰하면 기억한다", trusted_certs.fingerprint_of("h", 6697) == "abcdef123456")
check("포트가 다르면 다른 서버로 본다", trusted_certs.fingerprint_of("h", 6667) == "")
check(f"사람이 눈으로 볼 수 있게 보여준다({trusted_certs.readable('abcdef123456')})",
      trusted_certs.readable("abcdef123456") == "AB:CD:EF:12:34:56")
trusted_certs.forget("h", 6697)
check("잊을 수도 있다", trusted_certs.fingerprint_of("h", 6697) == "")
if _os.path.exists(trusted_certs.STORE_FILE):
    _os.remove(trusted_certs.STORE_FILE)

# ---------- 4) 창이 물어볼 준비가 돼 있는가 ----------
check("소켓이 '확인할 수 없는 인증서'를 알릴 수 있다",
      hasattr(window.client, "certificate_untrusted"))
check("창이 그 신호를 받아 물어본다", hasattr(window, "_on_certificate_untrusted"))

asked = {}
import gui_client  # noqa: E402

real_question = gui_client.themed_question
gui_client.themed_question = lambda parent, title, text: (
    asked.update(title=title, text=text), False)[1]
window._on_certificate_untrusted("home.pdlab.kr", 6697, "aabbcc", "자체 서명")
gui_client.themed_question = real_question
# 물음은 짧아야 한다 - 지문과 오류 원문을 늘어놓으면 아무도 안 읽고 그냥 누른다
message = asked.get("text", "")
check(f"어느 서버인지 알려준다({message.splitlines()[0] if message else ''})",
      "home.pdlab.kr" in message, message)
check("자체 서명이라는 것과 무엇을 묻는지가 분명하다",
      "자체 서명" in message and "신뢰" in message, message)
check(f"세 줄을 넘지 않는다({len([x for x in message.splitlines() if x.strip()])}줄)",
      len([x for x in message.splitlines() if x.strip()]) <= 3, message)
check("거절하면 신뢰 목록에 남지 않는다",
      trusted_certs.fingerprint_of("home.pdlab.kr", 6697) == "")

# ---------- 5) 보안 포트가 막힌 곳 대비 ----------
check("보안 접속이 막히면 평문으로 한 번 물러난다", hasattr(window, "_try_plain_fallback"))
window._plain_fallback_tried = False
page.ssl_checkbox.setChecked(True)
page.port_input.setText(g.DEFAULT_SSL_PORT)
check("한 번은 물러난다", window._try_plain_fallback() is True)
check("물러난 뒤에는 평문 포트로 바뀐다", page.port_input.text() == g.DEFAULT_PLAIN_PORT,
      page.port_input.text())
check("두 번은 물러나지 않는다(무한 반복 방지)", window._try_plain_fallback() is False)


# ---------- 6) 저장하는 비밀번호를 그대로 두지 않는가 ----------
import json  # noqa: E402

import secret_store  # noqa: E402

sealed = secret_store.protect("0990")
check(f"저장 형태가 원문과 다르다({sealed[:14]}...)", "0990" not in sealed, sealed[:30])
check("다시 읽으면 원래 비밀번호", secret_store.unprotect(sealed) == "0990")
check("예전에 그대로 저장된 값도 읽힌다", secret_store.unprotect("옛날비번") == "옛날비번")
check("빈 값은 그대로 둔다", secret_store.protect("") == "" and secret_store.unprotect("") == "")
check("한글 비밀번호도 오간다", secret_store.unprotect(secret_store.protect("비밀번호가")) == "비밀번호가")

work = tempfile.mkdtemp(prefix="chup_prefs_")
real_file = login_prefs.LOGIN_PREFS_FILE
login_prefs.LOGIN_PREFS_FILE = _os.path.join(work, "login_prefs.json")
try:
    login_prefs.save({"user_id": "Mong", "password": "0990", "auto_login": True})
    on_disk = io.open(login_prefs.LOGIN_PREFS_FILE, encoding="utf-8").read()
    check("파일에 비밀번호가 그대로 적히지 않는다", "0990" not in on_disk, on_disk[:80])
    check("앱이 읽을 때는 원래 비밀번호가 나온다",
          login_prefs.load().get("password") == "0990")
finally:
    login_prefs.LOGIN_PREFS_FILE = real_file

print("=== 검증 결과 (보안 접속) ===")
all_ok = True
for name, ok, *detail in checks:
    extra = f"  <- {detail[0]}" if detail and detail[0] and not ok else ""
    print(f"[{'OK' if ok else 'FAIL'}] {name}{extra}")
    all_ok = all_ok and ok
print("\n전체 통과:", all_ok)
_sys.exit(0 if all_ok else 1)
