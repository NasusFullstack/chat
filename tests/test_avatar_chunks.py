"""IRC 아이콘 조각 전송 - 512바이트 제한 아래에서 실제로 살아남는지 검증"""
import os as _os
import sys as _sys

_HERE = _os.path.dirname(_os.path.abspath(__file__))
_REPO = _os.path.dirname(_HERE)

import os, sys, socket, threading, time
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, _REPO)

import irc_protocol
from chat_core import events
from chat_core.constants import AVATAR_MAX_B64_CHARS
from chat_core.history_adapter import NullHistoryStore
from chat_core.session import build_session

fails = []


def check(label, cond, extra=""):
    print(("  OK   " if cond else "  FAIL ") + label + ("" if cond else f"  <- {extra}"))
    if not cond:
        fails.append(label)


LIMIT = irc_protocol.IRC_LINE_LIMIT
# 서버가 붙이는 프리픽스 최악의 경우를 흉내
WORST_PREFIX = ":" + "n" * 30 + "!" + "u" * 10 + "@" + "h" * 60 + " "


def new_session():
    sent, evs = [], []
    s = build_session("irc", "h", 1, sent.append, evs.append, history_store=NullHistoryStore())
    s.my_id = "me"
    s.joined_channels.add("#chan")
    s.active_channel = "#chan"
    return s, sent, evs


print("[1] 보내는 모든 줄이 512바이트 안에 들어가는가")
for size, label in ((144, "단색(실측)"), (188, "보통 아이콘(실측)"),
                    (1372, "최악 랜덤(실측)"), (AVATAR_MAX_B64_CHARS, "상한 2000자")):
    lines = irc_protocol.format_ctcp_avatar("#somewhatlongchannelname", "A" * size)
    worst = max(len(WORST_PREFIX + ln) + 2 for ln in lines)
    check(f"{label:20s} {len(lines)}조각, 최대 {worst}바이트", worst <= LIMIT, worst)

print("\n[2] 실제 아이콘 크기는 조각이 몇 개인가")
for size, label in ((144, "단색"), (188, "보통 아이콘")):
    n = len(irc_protocol.format_ctcp_avatar("#chan", "A" * size))
    check(f"{label} 은 한 조각으로 끝남", n == 1, n)

print("\n[3] 조각을 순서대로 받으면 원본이 복원되는가")
s, sent, evs = new_session()
original = "".join(chr(65 + i % 26) for i in range(1372))
s.publish_avatar_lines = None  # noqa - 존재 확인용 아님
from chat_core.protocols.irc import IrcProtocol
IrcProtocol()._send_avatar(s, "#chan", original)
check(f"여러 줄로 나가짐({len(sent)}줄)", len(sent) > 1, len(sent))

evs.clear()
for line in sent:
    # 서버가 중계하는 형태로 되돌려줌
    s.handle_incoming(irc_protocol.parse_line(f":friend!u@h {line}"))
avatars = [e for e in evs if isinstance(e, events.AvatarUpdated)]
check("다 모인 뒤에 한 번만 반영됨", len(avatars) == 1, len(avatars))
check("원본과 정확히 일치", avatars and avatars[0].avatar_b64 == original,
      (len(avatars[0].avatar_b64) if avatars else None, len(original)))

print("\n[4] 조각이 뒤섞여 도착해도 되는가")
s, sent, evs = new_session()
IrcProtocol()._send_avatar(s, "#chan", original)
lines = list(sent)
evs.clear()
for line in reversed(lines):
    s.handle_incoming(irc_protocol.parse_line(f":friend!u@h {line}"))
avatars = [e for e in evs if isinstance(e, events.AvatarUpdated)]
check("역순으로 와도 복원됨", len(avatars) == 1 and avatars[0].avatar_b64 == original,
      len(avatars))

print("\n[5] 조각이 하나 빠지면 - 아무 일도 안 일어나야 함")
s, sent, evs = new_session()
IrcProtocol()._send_avatar(s, "#chan", original)
lines = list(sent)
evs.clear()
for line in lines[:-1]:  # 마지막 조각 유실
    s.handle_incoming(irc_protocol.parse_line(f":friend!u@h {line}"))
check("아이콘 반영 안 됨", not [e for e in evs if isinstance(e, events.AvatarUpdated)], evs)
check("채팅으로도 안 샘", not [e for e in evs if isinstance(e, events.MessageReceived)], evs)

print("\n[6] 서버가 512에서 잘라버린 경우 - 채팅으로 새면 안 됨 (원래 버그)")
s, sent, evs = new_session()
old_style = irc_protocol.format_privmsg(
    "#chan", f"\x01{irc_protocol.AVATAR_CTCP_TAG} {'A' * 2000}\x01")
relayed = f":friend!u@h {old_style}"
truncated = relayed[:LIMIT - 2]
evs.clear()
s.handle_incoming(irc_protocol.parse_line(truncated))
msgs = [e for e in evs if isinstance(e, events.MessageReceived)]
check("잘린 쓰레기가 채팅에 안 뜸", len(msgs) == 0,
      f"{len(msgs)}건 샘: {msgs[0].text[:40] if msgs else ''}")
check("아이콘도 당연히 반영 안 됨",
      not [e for e in evs if isinstance(e, events.AvatarUpdated)], evs)

print("\n[7] 구버전 클라이언트가 보낸 옛 형식도 받아주는가")
s, sent, evs = new_session()
legacy = irc_protocol.format_privmsg("#chan", f"\x01{irc_protocol.AVATAR_CTCP_TAG} SGVsbG8=\x01")
evs.clear()
s.handle_incoming(irc_protocol.parse_line(f":oldfriend!u@h {legacy}"))
avatars = [e for e in evs if isinstance(e, events.AvatarUpdated)]
check("옛 형식 아이콘도 반영됨", len(avatars) == 1 and avatars[0].avatar_b64 == "SGVsbG8=",
      [(e.user_id, e.avatar_b64) for e in avatars])

print("\n[8] 미완성 전송이 쌓여도 메모리가 무한정 늘지 않는가")
s, sent, evs = new_session()
from chat_core.protocols.irc import MAX_PENDING_AVATARS
for i in range(MAX_PENDING_AVATARS + 20):
    # 항상 첫 조각만 보내서 영영 완성되지 않는 전송을 잔뜩 만듦
    line = f"\x01{irc_protocol.AVATAR_CTCP_TAG} id{i:03d} 1/3 XXXX\x01"
    s.handle_incoming(irc_protocol.parse_line(
        f":spam{i}!u@h " + irc_protocol.format_privmsg("#chan", line)))
check(f"미완성 버퍼가 {MAX_PENDING_AVATARS}건 근처로 제한됨",
      len(s.irc_avatar_chunks) <= MAX_PENDING_AVATARS + 1, len(s.irc_avatar_chunks))

print("\n[9] 엄격한 서버(512에서 자름)와 실제 왕복")


class StrictServer(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.sock = socket.socket()
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(5)
        self.port = self.sock.getsockname()[1]
        self.privmsgs = []
        self.running = True

    def run(self):
        try:
            conn, _ = self.sock.accept()
        except OSError:
            return
        conn.settimeout(8)
        buf = b""
        try:
            while self.running:
                data = conn.recv(4096)
                if not data:
                    return
                buf += data
                while b"\n" in buf:
                    raw, buf = buf.split(b"\n", 1)
                    raw = raw.rstrip(b"\r")
                    if len(raw) + 2 > LIMIT:      # 실제 서버처럼 잘라냄
                        raw = raw[:LIMIT - 2]
                    line = raw.decode("utf-8", "replace")
                    if line.startswith("PRIVMSG "):
                        self.privmsgs.append(line)
        except (OSError, socket.timeout):
            return

    def stop(self):
        self.running = False
        try:
            self.sock.close()
        except OSError:
            pass


srv = StrictServer()
srv.start()
sock = socket.create_connection(("127.0.0.1", srv.port), timeout=5)
s, sent, evs = new_session()
IrcProtocol()._send_avatar(s, "#chan", original)
for line in sent:
    sock.sendall((line + "\r\n").encode("utf-8"))
time.sleep(0.8)
sock.close()

check("서버가 모든 조각을 안 자르고 받음", len(srv.privmsgs) == len(sent),
      (len(srv.privmsgs), len(sent)))
check("받은 줄이 보낸 줄과 완전히 동일(잘림 없음)", srv.privmsgs == sent,
      "일부가 잘림")

# 받은 그대로 다시 파싱해서 복원되는지
s2, _, evs2 = new_session()
for line in srv.privmsgs:
    s2.handle_incoming(irc_protocol.parse_line(f":friend!u@h {line}"))
restored = [e for e in evs2 if isinstance(e, events.AvatarUpdated)]
check("엄격한 서버를 거쳐도 아이콘이 원본 그대로 복원됨",
      len(restored) == 1 and restored[0].avatar_b64 == original,
      len(restored))
srv.stop()

print()
if fails:
    print(f"실패 {len(fails)}건: {fails}")
    sys.exit(1)
print("전부 통과")
