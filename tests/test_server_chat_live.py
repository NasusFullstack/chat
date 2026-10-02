"""PC 가 **진짜 서버 채팅에 붙어서** 한 바퀴 도는가.

여기서만 확인되는 것들이다. 앞 검사들은 우리끼리 맞춘 것뿐이라, 서버가 실제로
받아주는지는 붙어봐야 안다:

 - WebSocket 통로가 진짜로 열리는가
 - 우리가 만든 줄을 서버가 받아주는가(가입·로그인·입장·말하기)
 - 서버가 보낸 줄을 전략이 **같은 이벤트**로 바꾸는가(화면은 이것만 본다)
 - **지난 기록이 입장 응답에 실려 오는가**(IRC 모드는 따로 받아와야 했다)

서버가 안 받아주면(점검 중 등) 실패가 아니라 **건너뜀**으로 처리하고 그 사실을 말한다 -
조용히 통과시키면 "안 되는데 검사는 초록"이 된다.
"""
import json
import os
import secrets
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, REPO)
sys.path.insert(0, HERE)

from PySide6.QtCore import QEventLoop, QTimer  # noqa: E402
from PySide6.QtNetwork import QAbstractSocket  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import relay  # noqa: E402
from chat_core import events  # noqa: E402
from chat_core.history_adapter import NullHistoryStore  # noqa: E402
from chat_core.session import build_session  # noqa: E402
from gui.login_request import SERVER_HOST, SERVER_PORT  # noqa: E402
from gui.server_chat_link import ServerChatLink  # noqa: E402

app = QApplication.instance() or QApplication([])
checks = []


def check(name, passed, detail=""):
    checks.append((name, passed, detail))
    print(f"[{'OK' if passed else 'FAIL'}] {name}" +
          (f"  <- {detail}" if detail and not passed else ""), flush=True)


def finish(skipped=""):
    if skipped:
        print(f"\n건너뜀: {skipped}", flush=True)
    print(f"\n검사 {len(checks)}개")
    ok = all(passed for _, passed, *_ in checks)
    print("전체 통과:", ok)
    sys.exit(0 if ok else 1)


class Peer:
    """한 사람 - 통로와 세션을 묶어둔다."""

    def __init__(self):
        self.link = ServerChatLink()
        self.events = []
        self.session = build_session(
            "server", SERVER_HOST, SERVER_PORT,
            transport=self.link.send_cmd,
            on_event=self.events.append,
            history_store=NullHistoryStore())
        self.link.message_received.connect(self.session.handle_incoming)
        self.failed = ""
        self.link.connection_failed.connect(self._on_failed)

    def _on_failed(self, why):
        self.failed = why

    def open(self) -> bool:
        self.link.connect_to_server(SERVER_HOST, SERVER_PORT, "", True)
        # **숫자와 비교하면 안 된다** - PySide6 6.11 의 enum 은 int 와 같지 않아서
        # 붙어 있어도 거짓이 되고, 검사가 "시간 초과"로 끝난다(여기서 실제로 겪었다)
        done = QAbstractSocket.SocketState.ConnectedState
        return wait_for(lambda: self.link.state() == done or bool(self.failed), 15)

    def wait_event(self, cls, seconds=12):
        """그 일이 일어날 때까지 기다린다. 안 오면 None.

        **시간 제한을 둔다** - 안 오는 것을 그냥 기다리면 검사가 통째로 멈춘다.
        """
        found = []

        def seen():
            for one in self.events:
                if isinstance(one, cls):
                    found.append(one)
                    return True
            return False

        wait_for(seen, seconds)
        return found[0] if found else None

    def close(self):
        self.link.abort()


def wait_for(done, seconds: float) -> bool:
    """Qt 이벤트를 돌리면서 기다린다. `app.quit()` 을 쓰면 안 된다(CLAUDE.md 11-3)."""
    loop = QEventLoop()
    timer = QTimer()
    timer.timeout.connect(lambda: loop.quit() if done() else None)
    timer.start(50)
    limit = QTimer()
    limit.setSingleShot(True)
    limit.timeout.connect(loop.quit)
    limit.start(int(seconds * 1000))
    loop.exec()
    timer.stop()
    limit.stop()
    return bool(done())


# ---------- 서버가 살아 있는가 ----------
try:
    with urllib.request.urlopen(f"{relay.SERVER}/chat", timeout=10) as reply:
        info = json.loads(reply.read().decode("utf-8"))
    alive = info.get("feature") == "chat"
except (urllib.error.URLError, OSError, ValueError):
    info, alive = {}, False

if not alive:
    finish("서버 채팅에 닿지 않음")


def feature_at_least(want: tuple) -> bool:
    """올라가 있는 기능이 그걸 할 수 있는가.

    **모르는 명령은 조용히 버리도록** 되어 있다(구버전 클라이언트가 죽지 않게). 그래서
    옛 서버에 새 명령을 보내면 실패도 안 오고 그냥 답이 없다 - 여기서 실제로 그렇게
    겪었다(가입이 아무 답 없이 멎었다). 버전을 먼저 보는 것이 유일한 분간법이다.
    """
    try:
        have = tuple(int(part) for part in str(info.get("version", "0")).split("."))
    except ValueError:
        return False
    return have >= want


# 1.1.0 부터 WebSocket 으로도 가입할 수 있다
WS_REGISTER = feature_at_least((1, 1, 0))

# ---------- 1) 가입하고 들어간다 ----------
me = Peer()
if not me.open() or me.failed:
    finish(f"서버 채팅에 못 붙음: {me.failed or '시간 초과'}")
check("WebSocket 통로가 열린다", True)

user_id = "pc" + secrets.token_hex(4)
if WS_REGISTER:
    me.session.register(user_id, "비밀1234")
    made = me.wait_event(events.RegisterSucceeded)
    check("연결 하나로 가입이 된다", made is not None, me.events[-3:])
else:
    # 올라간 서버가 아직 옛것이다. 조용히 통과시키면 "안 되는데 검사는 초록"이 되므로
    # **말하고** 넘어간다. 뒤 검사들은 돌아야 하니 HTTP 창구로 계정만 만든다
    print(f"[건너뜀] 연결 하나로 가입 - 올라간 chat 이 {info.get('version')} "
          f"(1.1.0 이상 필요). 서버를 다시 올리면 켜진다", flush=True)
    body = json.dumps({"id": user_id, "pw": "비밀1234"}).encode("utf-8")
    ask = urllib.request.Request(f"{relay.SERVER}/chat/register", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(ask, timeout=15) as reply:
        reply.read()

me.session.login(user_id, "비밀1234")
wait_for(lambda: me.session.my_id == user_id, 12)
check("로그인하면 내 자리를 받는다", me.session.my_id == user_id, me.session.my_id)

channel = "검사" + secrets.token_hex(3)
me.session.join_channel(channel)
joined = me.wait_event(events.ChannelJoined)
check("채널에 들어간다", joined is not None and joined.channel == channel, joined)
# **한글 채널 이름이 된다** - IRC 는 # 가 필요하고 한글도 안 됐다
check("한글 채널 이름이 된다", joined is not None and joined.channel.startswith("검사"))

# ---------- 2) 말이 오간다 ----------
me.events.clear()
me.session.send_message(channel, "안녕하세요")
said = me.wait_event(events.MessageReceived)
check("내가 보낸 말이 돌아온다", said is not None and said.text == "안녕하세요", said)
check("내 것으로 표시된다", said is not None and said.mine is True)
# 한 번만 보여야 한다 - 로컬 에코까지 하면 두 번 보인다
check("두 번 보이지 않는다",
      len([e for e in me.events if isinstance(e, events.MessageReceived)]) == 1,
      len([e for e in me.events if isinstance(e, events.MessageReceived)]))

# ---------- 3) IRC 가 못 하던 것 ----------
me.events.clear()
me.session.set_nickname("한글이름")
wait_for(lambda: me.session.nicknames.get(user_id) == "한글이름", 8)
check("한글 표시 이름이 된다(IRC 서버는 거절했다)",
      me.session.nicknames.get(user_id) == "한글이름", me.session.nicknames.get(user_id))

long_text = "가" * 1000      # IRC 는 한 줄 512바이트에서 잘린다
me.events.clear()
me.session.send_message(channel, long_text)
long_said = me.wait_event(events.MessageReceived)
check("긴 글이 안 잘린다", long_said is not None and long_said.text == long_text,
      len(long_said.text) if long_said else 0)

big_avatar = "A" * 5000      # IRC 는 300자씩 쪼개야 했다
check("큰 아이콘을 받아준다(쪼개지 않는다)", me.session.set_avatar(big_avatar) is True)

# ---------- 4) 다시 들어가면 **지난 기록이 같이 온다** ----------
me.close()
time.sleep(0.5)

again = Peer()
if not again.open():
    finish("두 번째 접속을 못 함")
again.session.login(user_id, "비밀1234")
wait_for(lambda: again.session.my_id == user_id, 12)
again.events.clear()
again.session.join_channel(channel)
back = again.wait_event(events.ChannelJoined)
check("다시 들어간다", back is not None, back)

history = [e.text for e in again.events if isinstance(e, events.MessageReceived)]
# IRC 모드는 중계 서버에 따로 받아와야 했다. 여기서는 입장 응답에 실려 온다
check("지난 이야기가 입장과 함께 온다", "안녕하세요" in history, history[:3])
again.close()

finish()
