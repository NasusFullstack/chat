"""chat_core 도메인 코어 단위 테스트 - Qt도 소켓도 파일 I/O도 없이 순수하게 검증.

DIP 덕분에 가짜 transport/history_store만 꽂으면 되므로 서버를 띄울 필요가 없음
(이번 리팩토링의 실질적 이득 - 예전에는 이런 검증도 오프스크린 Qt + 실제 서버가 필요했음).
"""
import os as _os
import sys as _sys

_HERE = _os.path.dirname(_os.path.abspath(__file__))
_REPO = _os.path.dirname(_HERE)

import sys
sys.path.insert(0, _REPO)

from chat_core import events
from chat_core.session import build_session, PROTOCOL_REGISTRY
from chat_core.history_adapter import NullHistoryStore
import irc_protocol

checks = []


class FakeHistory:
    """HistoryStorePort의 가짜 구현 - 파일을 안 건드리고 메모리에만 기록"""

    def __init__(self, preload=None):
        self.saved = []
        self._preload = preload or []

    def load_history(self, protocol, host, port, channel):
        return list(self._preload)

    def append_message(self, protocol, host, port, channel, sender, text, ts):
        self.saved.append((channel, sender, text))


def make(protocol="custom", history=None):
    sent, evs = [], []
    s = build_session(
        protocol, "127.0.0.1", 1234,
        transport=lambda p: sent.append(p),
        on_event=lambda e: evs.append(e),
        history_store=history or NullHistoryStore(),
    )
    return s, sent, evs


# ===== 커스텀: 로그인/회원가입 =====
s, sent, evs = make()
s.login("alice", "pw")
checks.append(("login()이 올바른 cmd 전송", sent[-1] == {"cmd": "login", "id": "alice", "pw": "pw"}))
s.handle_incoming({"type": "auth_result", "ok": True})
checks.append(("로그인 성공 -> LoggedIn", isinstance(evs[-1], events.LoggedIn) and evs[-1].user_id == "alice"))

s2, _, evs2 = make()
s2.register("bob", "pw")
s2.handle_incoming({"type": "auth_result", "ok": True})
checks.append(("회원가입 성공 -> RegisterSucceeded(로그인 아님)", isinstance(evs2[-1], events.RegisterSucceeded)))
checks.append(("회원가입만으로 my_id 안 정해짐", s2.my_id == ""))

s3, _, evs3 = make()
s3.login("x", "bad")
s3.handle_incoming({"type": "auth_result", "ok": False, "text": "비밀번호 틀림"})
checks.append(("로그인 실패 -> AuthFailed", isinstance(evs3[-1], events.AuthFailed)))

# ===== 커스텀: 채널 생성 != 입장 =====
s.handle_incoming({"type": "channel_result", "ok": True, "text": "채널 생성 완료", "channel": "#a"})
checks.append(("생성 응답은 ChannelCreated", isinstance(evs[-1], events.ChannelCreated)))
checks.append(("생성만으로는 입장 안 됨", "#a" not in s.joined_channels))
s.handle_incoming({"type": "channel_result", "ok": True, "text": "입장 성공", "channel": "#a"})
checks.append(("입장 응답은 ChannelJoined", isinstance(evs[-1], events.ChannelJoined)))
checks.append(("joined_channels/active_channel 반영", "#a" in s.joined_channels and s.active_channel == "#a"))

# ===== 커스텀: 메시지 + 히스토리 기록(DIP - 가짜 저장소로 확인) =====
hist = FakeHistory()
s4, sent4, evs4 = make(history=hist)
s4.login("alice", "pw")
s4.handle_incoming({"type": "auth_result", "ok": True})
s4.handle_incoming({"type": "channel_result", "ok": True, "text": "입장 성공", "channel": "#a"})
s4.handle_incoming({"type": "chat", "channel": "#a", "from": "carol", "text": "안녕", "ts": 1.0})
checks.append(("메시지 수신 이벤트", isinstance(evs4[-1], events.MessageReceived) and evs4[-1].mine is False))
checks.append(("주입된 history_store에 기록됨(파일 안 건드림)", hist.saved == [("#a", "carol", "안녕")]))

hist2 = FakeHistory(preload=[{"from": "alice", "text": "옛날 메시지", "ts": 1.0}])
s5, _, evs5 = make(history=hist2)
s5.handle_incoming({"type": "channel_result", "ok": True, "text": "입장 성공", "channel": "#h"})
checks.append(("ChannelJoined에 주입된 저장소의 히스토리가 실림", len(evs5[-1].history) == 1))

# ===== 커스텀: 로컬 에코 안 함 (서버가 돌려주므로) =====
before = len([e for e in evs4 if isinstance(e, events.MessageReceived)])
s4.members["#a"] = {"alice", "carol"}
s4.send_message("#a", "hello")
after = len([e for e in evs4 if isinstance(e, events.MessageReceived)])
checks.append(("커스텀 프로토콜은 로컬 에코 안 함(서버 응답 대기)", after == before))

# ===== @호출 쿨타임 =====
s4.nicknames["carol"] = "Carol"
n_before = len(sent4)
s4.send_message("#a", "@Carol 안녕")
checks.append(("첫 @호출은 전송됨", len(sent4) == n_before + 1))
n_before = len(sent4)
s4.send_message("#a", "@Carol 또")
checks.append(("같은 사람 재호출은 전송 자체가 막힘", len(sent4) == n_before))
checks.append(("MentionBlocked 이벤트", isinstance(evs4[-1], events.MentionBlocked) and evs4[-1].target_display == "Carol"))
n_before = len(sent4)
s4.send_message("#a", "@alice 다른사람")
checks.append(("다른 사람은 쿨타임 무관하게 전송", len(sent4) == n_before + 1))

s4.handle_incoming({"type": "chat", "channel": "#a", "from": "carol", "text": "@alice 야", "ts": 2.0})
checks.append(("나를 멘션한 메시지는 is_mention=True", evs4[-1].is_mention is True))
s4.handle_incoming({"type": "chat", "channel": "#a", "from": "carol", "text": "그냥 잡담", "ts": 3.0})
checks.append(("나를 안 멘션하면 is_mention=False", evs4[-1].is_mention is False))

# ===== 아바타 크기 제한 =====
checks.append(("너무 큰 아바타는 거부", s4.set_avatar("x" * 3000) is False))
checks.append(("정상 크기 아바타는 통과", s4.set_avatar("ZmFrZQ==") is True))

# ===== IRC: 등록 + 닉 충돌 재시도 =====
si, senti, evsi = make("irc")
si.login("dave", "")
checks.append(("IRC 등록 시 NICK/USER 전송", any("NICK dave" in l for l in senti) and any("USER dave" in l for l in senti)))
si.handle_incoming(irc_protocol.parse_line(":srv 433 * dave :in use"))
checks.append(("닉 충돌 시 밑줄 붙여 자동 재시도", any("NICK dave_" in l for l in senti)))
si.handle_incoming(irc_protocol.parse_line(":srv 001 dave_ :Welcome"))
checks.append(("RPL_WELCOME -> LoggedIn, 서버가 확정한 닉 사용", si.my_id == "dave_"))

# ===== IRC: PING 자동 응답 =====
n_before = len(senti)
si.handle_incoming(irc_protocol.parse_line("PING :xyz"))
checks.append(("PING에 PONG 자동 응답", any("PONG" in str(p) for p in senti[n_before:])))

# ===== IRC: ENDOFNAMES 버퍼링 (예전 CLI 버그) =====
si.handle_incoming(irc_protocol.parse_line(":srv 353 dave_ = #c :dave_ eve"))
checks.append(("ENDOFNAMES 전엔 멤버 미확정", "#c" not in si.members))
si.handle_incoming(irc_protocol.parse_line(":srv 366 dave_ #c :End"))
checks.append(("ENDOFNAMES에서 멤버 확정", si.members.get("#c") == {"dave_", "eve"}))
si.handle_incoming(irc_protocol.parse_line(":eve!u@h PART #c"))
checks.append(("PART 시 멤버가 실제로 제거됨(예전 CLI 버그 아님)", si.members.get("#c") == {"dave_"}))

# ===== IRC: CTCP 아바타가 채팅으로 안 샘 (예전 CLI 버그) =====
# format_ctcp_avatar는 512바이트 제한 때문에 여러 줄을 반환함(작은 아이콘은 1줄)
ctcp = irc_protocol.parse_line(
    ":eve!u@h " + irc_protocol.format_ctcp_avatar("#c", "QVZBVEFS")[0])
n_before = len(evsi)
si.handle_incoming(ctcp)
leaked = any(isinstance(e, events.MessageReceived) and "QVZBVEFS" in e.text for e in evsi[n_before:])
checks.append(("CTCP 아바타가 채팅 텍스트로 안 샘", not leaked))
checks.append(("아바타로 정상 처리됨", si.avatars.get("eve") == "QVZBVEFS"))

# ===== IRC: 로컬 에코 함 (서버가 안 돌려주므로) =====
si.members["#c"] = {"dave_"}
n_before = len([e for e in evsi if isinstance(e, events.MessageReceived)])
si.send_message("#c", "hi")
n_after = len([e for e in evsi if isinstance(e, events.MessageReceived)])
checks.append(("IRC는 로컬 에코를 함(서버가 안 돌려줌)", n_after == n_before + 1))


# ===== OCP 검증: 새 프로토콜을 ChatSession 수정 없이 추가할 수 있는가 =====
class DummyProtocol:
    """ProtocolPort만 만족하는 새 프로토콜 - ChatSession/기존 코드를 전혀 안 고치고 추가"""
    name = "dummy"

    def start_auth(self, session, user_id, password, mode):
        session.set_identity(user_id)

    def create_channel(self, session, channel, key):
        pass

    def join(self, session, channel, key):
        session.enter_channel(channel, "더미 입장")

    def leave(self, session, channel):
        pass

    def send_chat(self, session, channel, text):
        session.transport(("dummy", channel, text))

    def publish_avatar(self, session, avatar_b64):
        pass

    def publish_nickname(self, session, nickname):
        pass

    def handle_incoming(self, session, raw):
        pass

    def normalize_channel(self, channel):
        return channel


PROTOCOL_REGISTRY["dummy"] = DummyProtocol
sd, sentd, evsd = make("dummy")
sd.login("zoe", "")
sd.join_channel("#d")
sd.send_message("#d", "테스트")
checks.append(("새 프로토콜을 registry 등록만으로 추가 가능(ChatSession 수정 0줄)",
               sd.my_id == "zoe" and sentd[-1] == ("dummy", "#d", "테스트")))
del PROTOCOL_REGISTRY["dummy"]

# ===== DIP/OCP 검증: 코어 소스에 저수준 의존/프로토콜 분기가 없는가 =====
import chat_core.session as sess_mod
src = open(sess_mod.__file__, encoding="utf-8").read()
checks.append(("코어가 PySide6를 import 하지 않음", "PySide6" not in src))
checks.append(("코어가 asyncio/socket을 import 하지 않음",
               "import asyncio" not in src and "import socket" not in src))
checks.append(("코어가 history_store를 직접 import 하지 않음(포트로만 접근)",
               "import history_store" not in src))
checks.append(("코어가 irc_protocol을 직접 import 하지 않음(프로토콜 전략에만 있음)",
               "import irc_protocol" not in src))
checks.append(("코어에 프로토콜 이름 분기가 없음(OCP)",
               '== "irc"' not in src and "== 'irc'" not in src))

print("\n=== 검증 결과 (chat_core 도메인 코어 - Qt/소켓/파일 없이) ===")
all_ok = True
for name, ok in checks:
    print(f"[{'OK' if ok else 'FAIL'}] {name}")
    all_ok = all_ok and ok
print(f"\n총 {len(checks)}개 검증, 전체 통과: {all_ok}")
