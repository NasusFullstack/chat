"""당분간 막아둔 것들이 **정말 막혔는가** - 그리고 막힌 걸 사람이 알 수 있는가.

사용자 요청(2026-10-08):
- 로그인 화면의 주소·포트를 **비워서 시작한다.** 채워지는 것은 이 기기에 저장해둔 것뿐
- 춥채팅 서버·친구 채팅 서버(커스텀)는 **보이되 못 고른다** - IRC 만 된다
- 사진·파일 올리기는 **pdlab IRC 의 #pdlab 채널에서만** 된다

막는 것은 말없이 하면 안 된다. "눌렀는데 아무 일도 안 일어난다"는 고장으로 보인다 -
그래서 막힐 때마다 **왜인지가 보이는지**도 같이 본다.
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)

os.environ["QT_QPA_PLATFORM"] = "offscreen"
# 러너가 검사용으로 막기를 풀어두는데(CHUPCHAT_OPEN_ALL), **여기서는 진짜로 막혔는지**
# 를 봐야 하므로 끈다
os.environ.pop("CHUPCHAT_OPEN_ALL", None)
# 사람이 쓰던 진짜 설정을 건드리지 않게(CLAUDE.md 11-2)
os.environ.setdefault("CHUPCHAT_DATA_DIR", tempfile.mkdtemp(prefix="avail_"))
sys.path.insert(0, REPO)
sys.path.insert(0, HERE)

from gui import availability  # noqa: E402

checks = []


def check(name, passed, detail=""):
    checks.append((name, passed, detail))
    print(f"[{'OK' if passed else 'FAIL'}] {name}" +
          (f"  <- {detail}" if detail and not passed else ""), flush=True)


# ---------- 1) 표 ----------
check("IRC 는 고를 수 있다", availability.protocol_enabled("irc"))
check("춥채팅 서버는 막혀 있다", not availability.protocol_enabled("server"))
check("친구 채팅 서버(커스텀)도 막혀 있다", not availability.protocol_enabled("custom"))

check("pdlab IRC 의 #pdlab 에서는 올릴 수 있다",
      availability.upload_allowed("irc", "home.pdlab.kr", "#pdlab"))
# IRC 는 채널 이름도 서버 주소도 대소문자를 안 가린다 - 가리면 같은 방인데 될 때와
# 안 될 때가 갈린다
check("채널 대소문자를 안 가린다", availability.upload_allowed("irc", "home.pdlab.kr", "#PDLab"))
check("주소 대소문자도 안 가린다", availability.upload_allowed("irc", "HOME.pdlab.KR", "#pdlab"))
check("다른 채널에서는 못 올린다",
      not availability.upload_allowed("irc", "home.pdlab.kr", "#general"))
check("다른 서버의 #pdlab 은 안 된다(이름만 같은 남의 방)",
      not availability.upload_allowed("irc", "irc.libera.chat", "#pdlab"))
check("서버 채팅의 pdlab 방도 안 된다",
      not availability.upload_allowed("server", "chupchat", "pdlab"))

# ---------- 2) 로그인 검사 - 막힌 쪽은 여기서 걸린다(자동 로그인도 이 길이다) ----------
from gui.login_request import parse_login_values  # noqa: E402

req, why = parse_login_values(
    {"protocol": "server", "user_id": "mong22", "password": "비밀1234"})
check("서버 채팅으로는 못 들어간다", req is None, req)
check("왜인지 말한다", why == availability.PROTOCOL_BLOCKED_TEXT, why)

req, why = parse_login_values(
    {"protocol": "custom", "host": "1.2.3.4", "port": "7000",
     "user_id": "a", "password": "b"})
check("커스텀 서버로도 못 들어간다", req is None and "IRC" in why, why)

req, why = parse_login_values({"protocol": "irc", "host": "", "port": "",
                               "user_id": "mong"})
# **몰래 기본값을 쓰지 않는다** - 빈칸이면 채우라고 말한다
check("주소·포트가 비면 채우라고 한다(기본값을 몰래 안 쓴다)",
      req is None and "포트" in why, why)

req, why = parse_login_values({"protocol": "irc", "host": "home.pdlab.kr",
                               "port": "6697", "user_id": "mong", "use_ssl": True})
check("IRC 는 그대로 된다", req is not None, why)

# ---------- 3) 로그인 화면 ----------
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])

import login_prefs  # noqa: E402
import server_registry  # noqa: E402
from gui.pages.login_page import LoginPage  # noqa: E402

login_prefs.save({})
page = LoginPage(lambda mode: None, lambda: None)
check("주소 칸이 비어서 시작한다", page.host_input.text() == "", page.host_input.text())
check("포트 칸이 비어서 시작한다", page.port_input.text() == "", page.port_input.text())
check("인증서 칸도 비어서 시작한다", page.cert_input.text() == "", page.cert_input.text())
check("처음 골라져 있는 것은 IRC", page.protocol_combo.currentData() == "irc",
      page.protocol_combo.currentData())

model = page.protocol_combo.model()
items = {page.protocol_combo.itemData(i): model.item(i)
         for i in range(page.protocol_combo.count())}
check("세 쪽 다 **보인다**(빼버리지 않았다)", set(items) == {"server", "irc", "custom"},
      set(items))
check("춥채팅 서버는 흐리다(못 고른다)", not items["server"].isEnabled())
check("친구 채팅 서버도 흐리다", not items["custom"].isEnabled())
check("IRC 는 고를 수 있다", items["irc"].isEnabled())
check("흐린 항목에 왜인지가 달려 있다",
      items["server"].toolTip() == availability.PROTOCOL_BLOCKED_TEXT, items["server"].toolTip())

# 코드로 막힌 쪽을 골라도 IRC 로 되돌아온다(저장한 서버 고르기 같은 다른 길이 있다)
page.protocol_combo.setCurrentIndex(page.protocol_combo.findData("server"))
check("막힌 쪽으로 넘어가도 IRC 로 되돌아온다", page.protocol_combo.currentData() == "irc",
      page.protocol_combo.currentData())
check("그때 왜인지 말한다", availability.PROTOCOL_BLOCKED_TEXT in page.status_label.text(),
      page.status_label.text())

# SSL 을 켜고 끌 때 빈 포트를 채우지 않는다
page.port_input.setText("")
page.ssl_checkbox.setChecked(False)
page.ssl_checkbox.setChecked(True)
check("SSL 을 켜고 꺼도 빈 포트는 빈 채로", page.port_input.text() == "",
      page.port_input.text())
page.port_input.setText("6697")
page.ssl_checkbox.setChecked(False)
check("표준 포트끼리는 바꿔준다(6697 -> 6667)", page.port_input.text() == "6667",
      page.port_input.text())

# ---------- 4) 저장해둔 것은 채운다 - 막힌 쪽 것만 빼고 ----------
login_prefs.save({"protocol": "irc", "host": "irc.example.net", "port": 6697,
                  "ssl": True, "user_id": "mong", "auto_login": False})
page = LoginPage(lambda mode: None, lambda: None)
check("저장해둔 IRC 주소는 채운다", page.host_input.text() == "irc.example.net",
      page.host_input.text())
check("저장해둔 이름도 채운다", page.user_input.text() == "mong", page.user_input.text())

login_prefs.save({"protocol": "server", "host": "chupchat", "port": 0,
                  "user_id": "mong22", "auto_login": True, "password": "x"})
page = LoginPage(lambda mode: None, lambda: None)
# 그대로 채우면 서버 채팅의 고정 자리(chupchat:0)가 IRC 주소 칸에 들어간다
check("지난번이 서버 채팅이면 주소를 안 채운다", page.host_input.text() == "",
      page.host_input.text())
check("그쪽 아이디도 안 채운다(IRC 닉네임으로 엉뚱하게 붙는다)",
      page.user_input.text() == "", page.user_input.text())
check("자동 로그인도 안 건다", not page.auto_login_checkbox.isChecked())
check("고른 쪽은 IRC", page.protocol_combo.currentData() == "irc")

# 커스텀으로 저장해둔 서버를 골라도 채우지 않는다
login_prefs.save({})
server_registry.save_servers([])
server_registry.add_server("친구네", "10.0.0.5", 7000, "", ssl=False, protocol="custom")
page = LoginPage(lambda mode: None, lambda: None)
page.server_combo.setCurrentIndex(1)
check("막힌 쪽으로 저장한 서버는 고르지 않은 것으로 되돌린다",
      page.server_combo.currentIndex() == 0 and page.host_input.text() == "",
      (page.server_combo.currentIndex(), page.host_input.text()))
server_registry.save_servers([])

# ---------- 5) 채팅 화면 - 올리기 ----------
import gui_client as g  # noqa: E402

chat = g.ChatPage(on_send=lambda a, b: None, on_add_channel=lambda: None,
                  on_leave_channel=lambda c: None, on_set_avatar=lambda: None)
chat.show()
chat.add_channel("#pdlab")
chat.add_channel("#general")
chat.set_upload_check(
    lambda channel: availability.upload_allowed("irc", "home.pdlab.kr", channel),
    availability.UPLOAD_BLOCKED_TEXT)

chat.add_channel("#general", activate=True)
app.processEvents()
btn = chat.message_input.photo_btn
check("막힌 방에서는 사진 버튼이 흐리다", not btn.isEnabled())
check("파일 버튼도 흐리다", not chat.message_input.file_btn.isEnabled())
check("왜인지 말풍선이 있다", btn.toolTip() == availability.UPLOAD_BLOCKED_TEXT, btn.toolTip())

# 끌어다 놓기는 버튼을 안 거친다 - 거기서도 막혀야 한다
started = []
chat._begin_upload = lambda path: started.append(path)
from PySide6.QtCore import QMimeData, QPointF, Qt, QUrl  # noqa: E402
from PySide6.QtGui import QDropEvent  # noqa: E402

here = os.path.abspath(__file__)
mime = QMimeData()
mime.setUrls([QUrl.fromLocalFile(here)])
drop = QDropEvent(QPointF(5, 5), Qt.DropAction.CopyAction, mime,
                  Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
chat.dropEvent(drop)
check("막힌 방에 끌어다 놓아도 안 올라간다", started == [], started)

chat.add_channel("#pdlab", activate=True)
app.processEvents()
check("#pdlab 으로 가면 버튼이 살아난다", chat.message_input.photo_btn.isEnabled())
chat.dropEvent(QDropEvent(QPointF(5, 5), Qt.DropAction.CopyAction, mime,
                          Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier))
# Qt 는 경로를 / 로 돌려준다 - 같은 파일인지는 정규화해서 본다
check("#pdlab 에서는 끌어다 놓으면 올라간다",
      [os.path.normcase(os.path.normpath(p)) for p in started]
      == [os.path.normcase(os.path.normpath(here))], started)

# ---------- 6) 폰과 같은 표인가 ----------
# 한쪽만 고치면 PC 와 폰이 다르게 막는다
with open(os.path.join(REPO, "mobile", "lib", "core", "availability.dart"),
          encoding="utf-8") as fp:
    dart = fp.read()
for protocol, host, channel in availability.UPLOAD_ROOMS:
    check(f"폰도 같은 방을 연다({protocol} {host} {channel})",
          f"'{protocol}'" in dart and f"'{host}'" in dart and f"'{channel}'" in dart)
for protocol in availability.ENABLED_PROTOCOLS:
    check(f"폰도 같은 쪽을 연다({protocol})", f"ChatKind.{protocol}" in dart)

print(f"\n검사 {len(checks)}개")
all_ok = all(passed for _, passed, *_ in checks)
print("전체 통과:", all_ok)
sys.exit(0 if all_ok else 1)
