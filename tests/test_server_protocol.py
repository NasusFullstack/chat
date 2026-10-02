"""서버 채팅 전략 - **IRC 때 하던 우회를 여기서도 하고 있지 않은가**.

이 프로토콜을 만든 이유가 "IRC 제약을 걷어내는 것"이라, 그 제약 때문에 생겼던 동작이
여기 남아 있으면 안 된다. 특히:

- IRC 는 보낸 말을 안 돌려줘서 **각자 자기 말을 화면에 올려야 했다**(로컬 에코).
  여기서는 서버가 돌려주므로 로컬 에코를 하면 **두 번 보인다**
- IRC 는 참여자 아이디만 줘서 아이콘·이름을 CTCP 로 따로 물어야 했다. 여기서는
  목록에 같이 오므로 **묻는 줄이 하나도 안 나가야** 한다
- 지난 기록을 중계 서버에서 따로 받아오던 것도, 여기서는 입장 응답에 실려 온다

Qt 도 소켓도 없이 돈다 - 코어는 그렇게 만들어져 있다(DIP).
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, REPO)
sys.path.insert(0, HERE)

from chat_core import events  # noqa: E402
from chat_core.session import build_session  # noqa: E402


class SpyHistory:
    """기록 창구를 들여다본다 - **읽었는가 / 적었는가**.

    서버가 기록을 들고 있는 쪽에서는 둘 다 일어나면 안 된다. 일어나면 다음에 들어갈
    때 로컬 기록과 서버 기록이 겹쳐서 같은 이야기가 두 번 보인다(실제로 그랬다).
    """

    def __init__(self):
        self.loaded = []
        self.appended = []

    def load_history(self, protocol, host, port, channel):
        self.loaded.append(channel)
        return [{"from": "유령", "text": "로컬에 남아 있던 줄", "ts": 0.5}]

    def append_message(self, protocol, host, port, channel, sender, text, ts):
        self.appended.append((channel, sender, text))

checks = []


def check(name, passed, detail=""):
    checks.append((name, passed, detail))
    print(f"[{'OK' if passed else 'FAIL'}] {name}" +
          (f"  <- {detail}" if detail and not passed else ""), flush=True)


class Fake:
    """세션 하나 - 보낸 줄과 일어난 일을 모아둔다."""

    def __init__(self):
        self.sent = []
        self.events = []
        self.history = SpyHistory()
        self.session = build_session(
            "server", "jsserv.pdlab.kr", 443,
            transport=self.sent.append,
            on_event=self.events.append,
            history_store=self.history)

    def feed(self, message):
        self.session.handle_incoming(message)

    def kinds(self, cls):
        return [e for e in self.events if isinstance(e, cls)]


# ---------- 1) 들어가기 ----------
f = Fake()
f.session.login("mong22", "비밀1234")
check("로그인을 보낸다", f.sent and f.sent[-1]["cmd"] == "login", f.sent[-1:])

f.feed({"type": "auth_result", "ok": True, "id": "mong22",
        "nick": "몽키", "avatar": "AAAA"})
check("내 자리를 받는다", f.session.my_id == "mong22")
# **서버가 들고 있던 내 이름·아이콘이 따라온다** - 기기를 바꿔도 그대로다
check("내 표시 이름이 따라온다", f.session.nicknames.get("mong22") == "몽키",
      f.session.nicknames)
check("내 아이콘도 따라온다", bool(f.session.avatars.get("mong22")))

f.session.join_channel("일반")
check("들어가기를 보낸다", f.sent[-1]["cmd"] == "join", f.sent[-1])

# ---------- 2) 입장 응답에 **지난 기록과 참여자**가 같이 온다 ----------
before = len(f.sent)
f.feed({"type": "channel_result", "ok": True, "channel": "일반",
        "history": [{"sender": "duri", "text": "어제 한 말", "ts": 1.0},
                    {"sender": "mong22", "text": "내가 한 말", "ts": 2.0}],
        "users": [{"id": "mong22", "nick": "몽키", "avatar": "AAAA"},
                  {"id": "duri", "nick": "두리", "avatar": "BBBB"}]})

joined = f.kinds(events.ChannelJoined)
check("채널에 들어간 것으로 본다", len(joined) == 1, joined)

# **지난 기록은 입장 이벤트에 실려 온다.** 한 줄씩 보통 메시지로 올리면 live 대화와
# 섞여서 어디까지가 지난 것인지 알 수 없다 - 화면이 쓰던 틀을 그대로 쓰게 둔다
check("지난 기록이 입장 이벤트에 실려 온다",
      [one["text"] for one in joined[0].history] == ["어제 한 말", "내가 한 말"],
      joined[0].history)
check("화면이 읽는 모양 그대로다(from/text/ts)",
      set(joined[0].history[0]) == {"from", "text", "ts"}, joined[0].history[0])
check("지난 기록을 보통 메시지로는 올리지 않는다", not f.kinds(events.MessageReceived),
      [m.text for m in f.kinds(events.MessageReceived)])

# **로컬 기록을 읽지 않는다.** 읽으면 서버가 준 것과 겹쳐서 두 벌이 된다
check("로컬 기록을 읽지 않는다", f.history.loaded == [], f.history.loaded)
check("로컬에 남아 있던 줄이 안 섞인다",
      all(one["from"] != "유령" for one in joined[0].history), joined[0].history)
check("참여자 목록이 채워진다", f.session.members.get("일반") == {"mong22", "duri"},
      f.session.members.get("일반"))
# **아이콘과 이름이 목록에 같이 온다** - IRC 는 CTCP 로 따로 물어야 했다
check("참여자 아이콘이 같이 온다", bool(f.session.avatars.get("duri")))
check("참여자 이름도 같이 온다", f.session.nicknames.get("duri") == "두리")
check("**아무에게도 묻지 않는다**", len(f.sent) == before,
      f"들어간 뒤 보낸 줄: {f.sent[before:]}")

# ---------- 3) 말하기 - 로컬 에코를 하지 않는다 ----------
f.events.clear()
f.session.send_message("일반", "안녕")
check("보낼 때는 화면에 안 올린다(서버가 돌려준다)",
      not f.kinds(events.MessageReceived),
      "로컬 에코를 하면 서버가 돌려줄 때 두 번 보인다")
check("보낸 줄은 msg 하나", f.sent[-1]["cmd"] == "msg" and f.sent[-1]["text"] == "안녕",
      f.sent[-1])

f.feed({"type": "chat", "channel": "일반", "id": "x1", "ts": 3.0,
        "sender": "mong22", "text": "안녕"})
echoed = f.kinds(events.MessageReceived)
check("서버가 돌려준 뒤에야 한 번 보인다", len(echoed) == 1, len(echoed))
check("내가 보낸 것으로 표시된다", echoed[0].mine is True)

# **로컬에 적지 않는다.** 적으면 다음에 들어갈 때 서버 기록과 겹친다
check("오간 말을 로컬 기록에 적지 않는다", f.history.appended == [], f.history.appended)
check("'서버가 기록을 들고 있다'를 전략이 알린다",
      f.session.protocol.keeps_history is True)

# ---------- 4) IRC 에서 못 하던 것 ----------
f.events.clear()
f.feed({"type": "whisper", "id": "w1", "ts": 4.0,
        "sender": "duri", "to": "mong22", "text": "둘만 아는 얘기"})
whispered = f.kinds(events.MessageReceived)
check("귓속말이 화면에 뜬다", len(whispered) == 1 and "귓속말" in whispered[0].sender,
      whispered and whispered[0].sender)

f.sent.clear()
f.session.set_nickname("한글이름")
check("한글 이름을 그대로 보낸다(IRC 는 거절당했다)",
      f.sent[-1]["cmd"] == "set_nickname" and f.sent[-1]["nick"] == "한글이름", f.sent[-1])

f.sent.clear()
f.session.set_avatar("A" * 5000)
check("아이콘을 **쪼개지 않고** 한 줄로 보낸다(IRC 는 300자씩 나눴다)",
      len(f.sent) == 1 and len(f.sent[0]["avatar"]) == 5000, len(f.sent))

# ---------- 5) 남이 바꾼 것이 따라온다 ----------
f.feed({"type": "member_nickname", "channel": "일반", "id": "duri", "nick": "두리새이름"})
check("남의 이름 바뀜을 반영한다", f.session.nicknames.get("duri") == "두리새이름")
f.feed({"type": "member_avatar", "channel": "일반", "id": "duri", "avatar": "CCCC"})
check("남의 아이콘 바뀜을 반영한다", f.session.avatars.get("duri") == "CCCC")

# ---------- 6) 전투 방 알림은 **채팅으로 새면 안 된다** ----------
import battle_protocol as bp  # noqa: E402

f.events.clear()
room = bp.new_room()
f.feed({"type": "chat", "channel": "일반", "id": "x2", "ts": 5.0,
        "sender": "duri", "text": bp.format_room_notice(room)})
check("전투 방 알림이 글자로 안 보인다", not f.kinds(events.MessageReceived),
      [e.text for e in f.kinds(events.MessageReceived)])
opened = f.kinds(events.BattleRoomOpened)
check("전투 방이 열린 것으로 읽는다", len(opened) == 1 and opened[0].room == room, opened)

# ---------- 6-1) 조용해도 끊기지 않게 ----------
# **이게 없으면 조용한 연결을 우리가 죽은 것으로 보고 끊는다.** IRC 는 서버가 90초마다
# PING 을 보내줘서 대화가 없어도 뭔가 오는데, 서버 채팅은 아무도 안 보낸다 -
# 비워뒀더니 170초마다 끊고 다시 붙었다(실측 2026-10-02, 소켓은 멀쩡했다)
f.sent.clear()
f.events.clear()
f.session.keepalive()
check("조용하면 살아 있는지 물어본다", f.sent == [{"cmd": "ping"}], f.sent)

f.feed({"type": "pong", "ts": 9.0})
check("답(pong)은 화면에 아무 것도 안 띄운다", not f.events, f.events)

# ---------- 7) 코어에 프로토콜 분기가 없어야 한다 ----------
with open(os.path.join(REPO, "chat_core", "session.py"), encoding="utf-8") as fp:
    source = fp.read()
check("세션에 'server' 이름을 비교하는 분기가 없다",
      'protocol.name == "server"' not in source and "== 'server'" not in source,
      "프로토콜 차이는 전략이 갖는다(OCP)")

print(f"\n검사 {len(checks)}개")
all_ok = all(passed for _, passed, *_ in checks)
print("전체 통과:", all_ok)
sys.exit(0 if all_ok else 1)
