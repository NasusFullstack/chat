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
# 1.2.0 부터 ping 에 답하고 방 목록을 준다
KEEPALIVE = feature_at_least((1, 2, 0))
# 1.3.0 부터 아이디의 대소문자를 안 가린다
CASELESS = feature_at_least((1, 3, 0))

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

# ---------- 4) 조용해도 끊기지 않게 ----------
# **없으면 조용한 연결을 우리가 죽은 것으로 보고 끊는다** - 실측(2026-10-02): PC 가
# 170초마다 끊고 다시 붙었다. 소켓 자체는 5분 넘게 멀쩡했다
if KEEPALIVE:
    me.events.clear()
    before_rx = me.link.last_rx_at
    me.session.keepalive()
    wait_for(lambda: me.link.last_rx_at > before_rx, 8)
    check("살아 있는지 물으면 답이 온다", me.link.last_rx_at > before_rx)
    # **글자가 하나도 안 보여야 한다.** (아이콘을 올린 답 같은 것이 늦게 섞여 들어올
    # 수 있으므로 "이벤트가 0개"로 보면 안 된다 - 여기서 실제로 그렇게 헛걸렸다)
    noisy = [e for e in me.events if isinstance(
        e, (events.MessageReceived, events.SystemNotice, events.GenericError))]
    check("그 답은 화면에 글자를 안 띄운다", not noisy, noisy[:2])
else:
    print(f"[건너뜀] 살아 있는지 묻기 - 올라간 chat 이 {info.get('version')} "
          f"(1.2.0 이상 필요)", flush=True)

# ---------- 5) 서버에 어떤 방이 있는지 보고 고른다 ----------
if KEEPALIVE:
    me.events.clear()
    me.session.request_room_list()
    listed = me.wait_event(events.RoomListReceived)
    check("방 목록을 받는다", listed is not None, me.events[:2])
    if listed is not None:
        names = [room.name for room in listed.rooms]
        check("방금 만든 방이 목록에 있다", channel in names, names[:5])
        mine_room = next((r for r in listed.rooms if r.name == channel), None)
        check("몇 명 있는지 같이 온다", mine_room is not None and mine_room.users >= 1,
              mine_room)
else:
    print(f"[건너뜀] 방 목록 - 올라간 chat 이 {info.get('version')} (1.2.0 이상 필요)",
          flush=True)

# ---------- 5-1) 아이디의 대소문자를 안 가린다 ----------
# IRC 는 이름의 대소문자를 안 가려서 사람들이 그 버릇으로 친다. 가렸더니 "있는
# 아이디인데 로그인이 안 된다"가 됐다(실측 2026-10-02)
if CASELESS:
    mixed = "Case" + secrets.token_hex(3).upper()
    body = json.dumps({"id": mixed, "pw": "비밀1234"}).encode("utf-8")
    ask = urllib.request.Request(f"{relay.SERVER}/chat/register", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(ask, timeout=15) as reply:
        reply.read()

    other = Peer()
    if other.open():
        other.session.login(mixed.lower(), "비밀1234")
        wait_for(lambda: other.session.my_id != "", 12)
        check("소문자로 쳐도 들어간다", other.session.my_id != "", other.session.my_id)
        # **처음 적은 그대로**를 돌려줘야 한다 - 안 그러면 같은 사람이 Mong 과 mong
        # 으로 갈려 보인다
        check("이름은 처음 적은 그대로다", other.session.my_id == mixed,
              other.session.my_id)
        other.close()
else:
    print(f"[건너뜀] 아이디 대소문자 - 올라간 chat 이 {info.get('version')} "
          f"(1.3.0 이상 필요)", flush=True)

# ---------- 6) 다시 들어가면 **지난 기록이 같이 온다** ----------
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

# **입장 이벤트에 실려 온다.** 보통 메시지로 한 줄씩 올리면 live 대화와 섞여서
# 어디까지가 지난 것인지 알 수 없다(실제로 그렇게 보였고, 거기에 로컬 기록과
# 중계 서버 기록까지 겹쳐 같은 이야기가 세 벌로 쌓였다)
history = [one.get("text") for one in (back.history if back else [])]
check("지난 이야기가 입장과 함께 온다", "안녕하세요" in history, history[:3])
check("지난 이야기를 보통 메시지로는 안 올린다",
      not [e for e in again.events if isinstance(e, events.MessageReceived)],
      [e.text for e in again.events if isinstance(e, events.MessageReceived)][:3])
again.close()

finish()
