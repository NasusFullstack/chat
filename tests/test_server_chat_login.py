"""서버 채팅을 **고르면 실제로 그쪽으로 붙는가**, 그리고 IRC 와 안 섞이는가.

사용자가 바란 것이 "IRC 와 서버 채팅을 따로 쓴다"라서, 여기서 보는 것은 둘이 서로
안 건드리는지다:

- 서버 채팅을 고르면 통로가 **WebSocket** 으로 바뀌는가
- IRC 로 되돌리면 통로도 되돌아오는가 (안 되돌아오면 IRC 가 통째로 안 된다)
- 기록·이모티콘·프로필이 **다른 자리**에 쌓이는가
- 주소·포트·인증서 칸이 서버 채팅에서는 안 보이는가(적을 것이 없다)
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, REPO)
sys.path.insert(0, HERE)

import relay  # noqa: E402
from gui import availability  # noqa: E402

# **지금은 서버 채팅과 커스텀을 막아뒀다**(gui/availability.py, 2026-10-08). 그래도
# 길 자체는 시험한다 - 막아둔 동안 아무도 안 돌려보면, 다시 열 때 깨진 걸 모른다.
# 여기서만 잠깐 연다(기본이 막혀 있는지는 tests/test_availability.py 가 본다)
availability.ENABLED_PROTOCOLS = frozenset({"irc", "server", "custom"})
from gui.login_request import SERVER_HOST, SERVER_PORT, parse_login_values  # noqa: E402
from gui.network import ChatClient  # noqa: E402
from gui.server_chat_link import ServerChatLink  # noqa: E402

checks = []


def check(name, passed, detail=""):
    checks.append((name, passed, detail))
    print(f"[{'OK' if passed else 'FAIL'}] {name}" +
          (f"  <- {detail}" if detail and not passed else ""), flush=True)


# ---------- 1) 입력 검사 ----------
req, why = parse_login_values(
    {"protocol": "server", "user_id": "mong22", "password": "비밀1234"})
check("주소를 안 적어도 들어갈 수 있다", req is not None, why)
check("늘 암호화된다(wss)", req.use_ssl is True)
check("자리는 고정값으로 정해진다", (req.host, req.port) == (SERVER_HOST, SERVER_PORT),
      (req.host, req.port))

_, why = parse_login_values({"protocol": "server", "user_id": "mong22"})
check("비밀번호가 없으면 안 된다", "비밀번호" in why, why)

irc, _ = parse_login_values(
    {"protocol": "irc", "host": "home.pdlab.kr", "port": "6697", "user_id": "mong"})
check("IRC 는 적은 주소를 그대로 쓴다", (irc.host, irc.port) == ("home.pdlab.kr", 6697),
      (irc.host, irc.port))

# ---------- 2) 쌓이는 자리가 갈린다 ----------
# 이게 섞이면 IRC 방 기록이 서버 방에 보이거나 그 반대가 된다
server_room = relay.room_id("server", SERVER_HOST, SERVER_PORT, "일반")
irc_room = relay.room_id("irc", "home.pdlab.kr", 6697, "#일반")
check("같은 이름이어도 자리가 다르다", server_room != irc_room, (server_room, irc_room))
check("서버 채팅 자리는 늘 같다",
      relay.room_id("server", SERVER_HOST, SERVER_PORT, "일반") == server_room)

# ---------- 3) 통로가 바뀌는가 ----------
# **앱 객체를 먼저 만든다.** 없이 위젯을 만들면 Qt 가 프로세스를 그냥 죽인다
# (파이썬 트레이스백도 안 남아서 원인을 찾기 어렵다 - 다른 검사들도 이렇게 한다)
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])

import gui_client as g  # noqa: E402

win = g.MainWindow()
check("처음에는 TLS 소켓", isinstance(win.client, ChatClient), type(win.client).__name__)

win._use_link_for("server")
check("서버 채팅을 고르면 WebSocket 으로 바뀐다",
      isinstance(win.client, ServerChatLink), type(win.client).__name__)

win._use_link_for("irc")
check("IRC 로 되돌리면 통로도 되돌아온다",
      isinstance(win.client, ChatClient), type(win.client).__name__)

# 같은 것을 두 번 고르면 아무 일도 안 한다(쓸데없이 끊지 않게)
same = win.client
win._use_link_for("irc")
check("같은 프로토콜이면 통로를 안 건드린다", win.client is same)

# ---------- 4) 창이 쓰는 창구가 양쪽에 다 있는가 ----------
# 하나라도 빠지면 그 모드에서만 터진다 - 눈으로 보면 놓치기 쉬운 자리다
link = ServerChatLink()
for name in ("set_mode", "connect_to_server", "send_cmd", "send_irc",
             "flush_pending", "recent_lines", "abort", "state"):
    check(f"WebSocket 통로에 {name} 가 있다", hasattr(link, name))
for name in ("connected", "encrypted", "disconnected", "message_received",
             "irc_line_received", "connection_failed", "certificate_untrusted"):
    check(f"WebSocket 통로가 {name} 를 낸다", hasattr(link, name))
check("last_rx_at 를 들고 있다(조용한지 재는 데 쓴다)", hasattr(link, "last_rx_at"))

# ---------- 5) 로그인 화면 ----------
page = win.login_page
names = [page.protocol_combo.itemData(i) for i in range(page.protocol_combo.count())]
check("고를 수 있는 것에 서버 채팅이 있다", "server" in names, names)
check("IRC 도 그대로 있다", "irc" in names, names)

page.protocol_combo.setCurrentIndex(page.protocol_combo.findData("server"))
check("서버 채팅에서는 주소 칸을 숨긴다", not page.host_input.isVisibleTo(page))
check("포트 칸도 숨긴다", not page.port_input.isVisibleTo(page))
check("인증서 칸도 숨긴다", not page.cert_input.isVisibleTo(page))

page.protocol_combo.setCurrentIndex(page.protocol_combo.findData("irc"))
check("IRC 로 바꾸면 주소 칸이 다시 보인다", page.host_input.isVisibleTo(page))

print(f"\n검사 {len(checks)}개")
all_ok = all(passed for _, passed, *_ in checks)
print("전체 통과:", all_ok)
sys.exit(0 if all_ok else 1)
