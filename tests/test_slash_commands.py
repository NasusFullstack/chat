"""슬래시 명령 코어 단위 테스트 - Qt/소켓/파일 없이 순수하게 검증"""
import os as _os
import sys as _sys

_HERE = _os.path.dirname(_os.path.abspath(__file__))
_REPO = _os.path.dirname(_HERE)

import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, _REPO)

from chat_core import commands, events
from chat_core.constants import (
    CHEAT_BATTLECRUISER_DISMISS, CHEAT_BATTLECRUISER_SUMMON, CHEAT_RESOURCES, find_cheat,
)
from chat_core.history_adapter import NullHistoryStore
from chat_core.session import build_session

fails = []


def check(label, cond, extra=""):
    print(("  OK   " if cond else "  FAIL ") + label + ("" if cond else f"  <- {extra}"))
    if not cond:
        fails.append(label)


def new_session(mode="custom"):
    sent, evs = [], []
    s = build_session(mode, "h", 1, sent.append, evs.append, history_store=NullHistoryStore())
    s.my_id = "me"
    s.members["#a"] = {"me", "Mong", "몽키", "Monster"}
    s.active_channel = "#a"
    s.joined_channels.add("#a")
    return s, sent, evs


def kinds(evs):
    return [type(e).__name__ for e in evs]


print("\n[1] 파싱")
check("/me 분해", commands.parse_command("/me 춤춘다") == ("me", "춤춘다"))
check("대소문자 무시", commands.parse_command("/ME hi") == ("me", "hi"))
check("인자 없음", commands.parse_command("/help") == ("help", ""))
check("평문은 None", commands.parse_command("안녕") is None)
check("// 는 명령 아님", commands.parse_command("//공지") is None)
check("/ 뒤 공백은 명령 아님", commands.parse_command("/ 그냥") is None)
check("escape_literal", commands.escape_literal("//공지") == "/공지")

print("\n[2] 프레이밍 왕복")
framed = commands.format_action("춤춘다")
check("action 왕복", commands.classify_message(framed) == (commands.KIND_ACTION, "춤춘다"), framed)
framed_n = commands.format_notice("공지합니다")
check("notice 왕복", commands.classify_message(framed_n) == (commands.KIND_NOTICE, "공지합니다"))
check("평문은 chat", commands.classify_message("안녕") == (commands.KIND_CHAT, "안녕"))

print("\n[3] 커스텀 프로토콜 명령")
s, sent, evs = new_session("custom")
s.send_message("#a", "/help")
help_ev = [e for e in evs if isinstance(e, events.CommandHelp)]
check("/help 이벤트", len(help_ev) == 1)
check("/help 목록에 /me 포함", any("/me" in ln for ln in help_ev[0].lines), help_ev[0].lines)
check("/help 에 IRC전용 /whois 없음", not any("/whois" in ln for ln in help_ev[0].lines))

sent.clear(); evs.clear()
s.send_message("#a", "/me 춤춘다")
check("/me 전송됨", len(sent) == 1, sent)
check("/me 프레이밍", sent and sent[0].get("text") == commands.format_action("춤춘다"), sent)

sent.clear(); evs.clear()
s.send_message("#a", "/notice 공지")
check("/notice 프레이밍", sent and sent[0].get("text") == commands.format_notice("공지"), sent)

sent.clear(); evs.clear()
s.send_message("#a", "/whois Mong")
err = [e for e in evs if isinstance(e, events.CommandError)]
check("미지원 명령 안내", len(err) == 1 and "지원하지 않는" in err[0].text, evs)
check("미지원 명령은 전송 안 함", not sent, sent)

sent.clear(); evs.clear()
s.send_message("#a", "/me")
check("/me 인자 없으면 사용법", any(isinstance(e, events.CommandError) for e in evs))
check("/me 인자 없으면 전송 안 함", not sent)

sent.clear(); evs.clear()
s.send_message("#a", "//진짜 슬래시")
check("// 는 평문 전송", sent and sent[0].get("text") == "/진짜 슬래시", sent)

sent.clear(); evs.clear()
s.send_message("#a", "/nick 새닉")
check("/nick 반영", s.nicknames.get("me") == "새닉", s.nicknames)

sent.clear(); evs.clear()
s.send_message("#a", "/join #b 열쇠")
check("/join 전송", sent and sent[0].get("cmd") == "join" and sent[0].get("channel") == "#b", sent)

sent.clear(); evs.clear()
s.send_message("#a", "/part")
check("/part 는 현재 채널", sent and sent[0].get("channel") == "#a", sent)

print("\n[4] IRC 프로토콜 명령")
s2, sent2, evs2 = new_session("irc")
s2.send_message("#a", "/whois Mong")
check("/whois 라인", sent2 == ["WHOIS Mong"], sent2)

sent2.clear(); evs2.clear()
s2.send_message("#a", "/notice 공지")
check("/notice 는 진짜 NOTICE", sent2 == ["NOTICE #a :공지"], sent2)
check("/notice 로컬 표시", any(isinstance(e, events.SystemNotice) for e in evs2))

sent2.clear(); evs2.clear()
s2.send_message("#a", "/msg Mong 안녕")
check("/msg 귓속말", sent2 == ["PRIVMSG Mong :안녕"], sent2)

sent2.clear(); evs2.clear()
s2.send_message("#a", "/me 춤춘다")
check("/me IRC", sent2 == [f"PRIVMSG #a :{commands.format_action('춤춘다')}"], sent2)
got = [e for e in evs2 if isinstance(e, events.MessageReceived)]
check("/me 로컬에코 kind=action", got and got[0].kind == commands.KIND_ACTION, got)
check("/me 로컬에코 본문", got and got[0].text == "춤춘다", got)

sent2.clear(); evs2.clear()
s2.send_message("#a", "/topic 새 주제")
check("/topic", sent2 == ["TOPIC #a :새 주제"], sent2)
sent2.clear(); s2.send_message("#a", "/away 밥먹는 중")
check("/away", sent2 == ["AWAY :밥먹는 중"], sent2)
sent2.clear(); s2.send_message("#a", "/away")
check("/away 해제", sent2 == ["AWAY"], sent2)
sent2.clear(); s2.send_message("#a", "/kick Mong 시끄러움")
check("/kick", sent2 == ["KICK #a Mong :시끄러움"], sent2)
sent2.clear(); s2.send_message("#a", "/mode #a +m")
check("/mode", sent2 == ["MODE #a +m"], sent2)
sent2.clear(); s2.send_message("#a", "/list")
check("/list", sent2 == ["LIST"], sent2)
sent2.clear(); s2.send_message("#a", "/raw PING :x")
check("/raw", sent2 == ["PING :x"], sent2)
sent2.clear(); s2.send_message("#a", "/invite Mong")
check("/invite 채널 생략", sent2 == ["INVITE Mong #a"], sent2)

print("\n[5] IRC 수신 - 숫자 응답/KICK")
import irc_protocol
sent2.clear(); evs2.clear()
s2.handle_incoming(irc_protocol.parse_line(":srv 311 me Mong user host * :실명"))
check("WHOIS 응답 표시", any(isinstance(e, events.SystemNotice) for e in evs2), evs2)
evs2.clear()
s2.handle_incoming(irc_protocol.parse_line(":srv 372 me :- MOTD 잡음"))
check("MOTD는 무시", not evs2, evs2)
evs2.clear()
s2.handle_incoming(irc_protocol.parse_line(":srv 482 me #a :권한이 없습니다"))
check("오류 숫자 표시", any(isinstance(e, events.SystemNotice) for e in evs2), evs2)
evs2.clear()
s2.handle_incoming(irc_protocol.parse_line(":op!u@h KICK #a me :bye"))
check("KICK 당하면 채널 이탈", any(isinstance(e, events.ChannelLeft) for e in evs2), evs2)

print("\n[6] 수신 렌더링 종류")
s3, sent3, evs3 = new_session("custom")
evs3.clear()
s3.handle_incoming({"type": "chat", "from": "Mong", "channel": "#a",
                    "text": commands.format_action("춤춘다"), "ts": 1.0})
msgs = [e for e in evs3 if isinstance(e, events.MessageReceived)]
check("수신 action 분류", msgs and msgs[0].kind == commands.KIND_ACTION and msgs[0].text == "춤춘다", msgs)
evs3.clear()
s3.handle_incoming({"type": "chat", "from": "Mong", "channel": "#a",
                    "text": commands.format_action("@me 봐라"), "ts": 1.0})
msgs = [e for e in evs3 if isinstance(e, events.MessageReceived)]
check("프레이밍 안에서도 @호출 인식", msgs and msgs[0].is_mention, msgs)

print("\n[7] 치트")
check("자원 치트", find_cheat("show me the money").id == CHEAT_RESOURCES)
check("배틀크루저 소환", find_cheat("배틀크루저 소환").id == CHEAT_BATTLECRUISER_SUMMON)
check("배틀크루저 해제", find_cheat("배틀크루저 소환해제").id == CHEAT_BATTLECRUISER_DISMISS)
check("해제가 소환에 안 먹힘", find_cheat("배틀크루저 소환해제").id != CHEAT_BATTLECRUISER_SUMMON)
check("평문은 None", find_cheat("배틀크루저") is None)

s4, sent4, evs4 = new_session("custom")
s4.send_message("#a", "배틀크루저 소환")
check("소환 전송", len(sent4) == 1, sent4)
evs4.clear()
s4.send_message("#a", "배틀크루저 소환")
check("소환 쿨타임", any(isinstance(e, events.CheatBlocked) for e in evs4), evs4)
sent4.clear(); evs4.clear()
s4.send_message("#a", "배틀크루저 소환해제")
check("해제는 쿨타임 없음", len(sent4) == 1, sent4)
sent4.clear()
s4.send_message("#a", "배틀크루저 소환해제")
check("해제 연속 가능", len(sent4) == 1, sent4)
sent4.clear(); evs4.clear()
s4.send_message("#a", "show me the money")
check("자원 치트는 별도 쿨타임", len(sent4) == 1, sent4)

# 배틀크루저는 방향키로 조종하는 것이라 '친 사람만' 화면에 떠야 함
# (모두에게 뜨면 각자 배가 생겨 남이 친 것 때문에 내 방향키가 먹힘)
evs4.clear()
s4.handle_incoming({"type": "chat", "from": "me", "channel": "#a",
                    "text": "배틀크루저 소환", "ts": 1.0})
act = [e for e in evs4 if isinstance(e, events.CheatActivated)]
check("내가 치면 소환 이벤트가 옴", act and act[0].cheat_id == CHEAT_BATTLECRUISER_SUMMON, evs4)

evs4.clear()
s4.handle_incoming({"type": "chat", "from": "Mong", "channel": "#a",
                    "text": "배틀크루저 소환", "ts": 1.0})
act = [e for e in evs4 if isinstance(e, events.CheatActivated)]
check("남이 치면 내 화면엔 안 뜸", not act, evs4)
check("  그래도 채팅 메시지는 보임",
      any(isinstance(e, events.MessageReceived) for e in evs4), evs4)

# 반면 자원 오버레이는 보여주는 연출이라 남이 쳐도 모두에게 떠야 함
evs4.clear()
s4.cheat_cooldowns.clear()
s4.handle_incoming({"type": "chat", "from": "Mong", "channel": "#a",
                    "text": "show me the money", "ts": 1.0})
act = [e for e in evs4 if isinstance(e, events.CheatActivated)]
check("자원 치트는 남이 쳐도 뜸", act and act[0].cheat_id == CHEAT_RESOURCES, evs4)

print("\n[8] OCP/DIP 소스 검사")
src = open(_os.path.join(_REPO, "chat_core", "session.py"), encoding="utf-8").read()
check("세션에 프로토콜 이름 분기 없음", '== "irc"' not in src and '== "custom"' not in src)
check("세션에 명령 이름 분기 없음", '"whois"' not in src and '"notice"' not in src and '"me"' not in src)
for bad in ("PySide6", "import asyncio", "import socket"):
    check(f"세션에 {bad} 없음", bad not in src)

print("\n[9] 새 프로토콜 추가해도 코어 수정 불필요")
from chat_core.session import PROTOCOL_REGISTRY, ChatSession


class DummyProtocol:
    name = "dummy"
    def start_auth(self, s, u, p, m): pass
    def create_channel(self, s, c, k): pass
    def join(self, s, c, k): pass
    def leave(self, s, c): pass
    def send_chat(self, s, c, t): s.transport(("dummy", c, t))
    def publish_avatar(self, s, a): pass
    def publish_nickname(self, s, n): pass
    def handle_incoming(self, s, raw): pass
    def normalize_channel(self, c): return c
    def command_specs(self): return [commands.HELP]
    def run_command(self, s, ch, name, args):
        if name == "help":
            s.emit(events.CommandHelp(ch, ["/help"]))
            return True
        return False


PROTOCOL_REGISTRY[DummyProtocol.name] = DummyProtocol
sent5, evs5 = [], []
s5 = build_session("dummy", "h", 1, sent5.append, evs5.append, history_store=NullHistoryStore())
s5.send_message("#a", "/help")
check("더미 프로토콜 /help", any(isinstance(e, events.CommandHelp) for e in evs5), evs5)
s5.send_message("#a", "/whois x")
check("더미 프로토콜 미지원 안내", any(isinstance(e, events.CommandError) for e in evs5))

print()
if fails:
    print(f"실패 {len(fails)}건: {fails}")
    sys.exit(1)
print("전부 통과")
