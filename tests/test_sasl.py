"""접속 과정에서 하는 인증(SASL)이 제대로 도는가.

왜 넣었는가: 예전에는 접속을 **마친 뒤** NickServ에게 귓속말로 비밀번호를 보냈다.
그러면 비밀번호가 채팅 메시지로 나가고, 인증되기 전 잠깐 '남'인 상태가 생긴다.
SASL은 접속 과정 자체에서 인증을 끝내는 요즘 표준이고, 실측 결과 이 서버도 지원한다
(home.pdlab.kr: `sasl=EXTERNAL,PLAIN`).

**실제로 겪은 함정**: 서버는 지원 목록이 길면 여러 줄로 나눠 보내고 "더 있다"를 `*`로
표시한다. 첫 줄만 보고 판단했더니 sasl을 놓쳐서 협상을 먼저 끝내버렸고, 그 뒤에 나간
AUTHENTICATE가 순서를 잃어 인증이 안 됐다(실측: 서버가 기능 28개를 여러 줄로 보냄).
"""
import os as _os
import sys as _sys

_HERE = _os.path.dirname(_os.path.abspath(__file__))
_REPO = _os.path.dirname(_HERE)

_os.environ["QT_QPA_PLATFORM"] = "offscreen"
_sys.path.insert(0, _REPO)

import base64  # noqa: E402

import irc_protocol  # noqa: E402
from chat_core import events as domain_events  # noqa: E402
from chat_core.session import build_session  # noqa: E402

checks = []


def check(name, ok, detail=""):
    checks.append((name, ok, detail))


def line(raw):
    return irc_protocol.parse_line(raw)


def new_session(password):
    sent, events = [], []
    session = build_session("irc", "h", 6667, transport=sent.append, on_event=events.append)
    session.login("Mong", password)
    return session, sent, events


# ---------- 1) 비밀번호가 있으면 협상을 시작한다 ----------
session, sent, events = new_session("pw123")
check(f"협상을 먼저 건다({sent[0] if sent else ''})", sent and sent[0] == "CAP LS 302", sent)

# ---------- 2) 목록이 여러 줄로 와도 다 모아서 판단한다(실제로 겪은 함정) ----------
sent.clear()
session.handle_incoming(line(":h CAP * LS * :away-notify chghost multi-prefix"))
check("아직 더 온다고 하면 기다린다(성급히 끝내지 않는다)", not sent, sent)
session.handle_incoming(line(":h CAP * LS :sasl=PLAIN tls account-notify"))
check(f"다 모은 뒤에 sasl을 요청한다({sent})", sent == ["CAP REQ :sasl"], sent)

# ---------- 3) 자격 증명 ----------
sent.clear()
session.handle_incoming(line(":h CAP * ACK :sasl"))
check("방식을 알린다(PLAIN)", sent == ["AUTHENTICATE PLAIN"], sent)

sent.clear()
session.handle_incoming(line("AUTHENTICATE +"))
check("자격을 실어 보낸다", len(sent) == 1 and sent[0].startswith("AUTHENTICATE "), sent)
raw = base64.b64decode(sent[0].split(" ", 1)[1])
check(f"형식이 규약대로다({raw!r})", raw == b"Mong\x00Mong\x00pw123", raw)

# ---------- 4) 성공하면 귓속말 인증은 생략 ----------
sent.clear()
session.handle_incoming(line(":h 903 Mong :SASL authentication successful"))
check(f"성공하면 협상을 끝낸다({sent})", sent == ["CAP END"], sent)
check("이미 인증됐다고 기억한다", session.irc_identified is True)
sent.clear()
session.handle_incoming(line(":h 001 Mong :Welcome"))
check("접속 뒤에 비밀번호를 또 보내지 않는다",
      not [s for s in sent if "NickServ" in s], sent)

# ---------- 5) 실패해도 접속은 계속돼야 한다 ----------
failed, failed_sent, failed_events = new_session("틀린비번")
failed.handle_incoming(line(":h CAP * LS :sasl=PLAIN"))
failed.handle_incoming(line(":h CAP * ACK :sasl"))
failed.handle_incoming(line("AUTHENTICATE +"))
failed_sent.clear()
failed_events.clear()
failed.handle_incoming(line(":h 904 Mong :SASL authentication failed"))
check(f"실패해도 협상을 끝내 접속을 이어간다({failed_sent})",
      "CAP END" in failed_sent, failed_sent)
told = [e for e in failed_events if isinstance(e, domain_events.SystemNotice)]
check(f"왜 안 됐는지 알려준다({[e.text[:30] for e in told]})", bool(told), told)
failed_sent.clear()
failed.handle_incoming(line(":h 001 Mong :Welcome"))
check("실패했으면 예전 방식(귓속말 인증)으로 물러난다",
      any("NickServ" in s for s in failed_sent), failed_sent)

# ---------- 6) 서버가 지원 안 하면 붙잡고 있지 않는다 ----------
plain, plain_sent, _ = new_session("pw123")
plain_sent.clear()
plain.handle_incoming(line(":h CAP * LS :tls account-notify"))
check(f"지원 안 하면 바로 협상을 끝낸다({plain_sent})", plain_sent == ["CAP END"], plain_sent)

# ---------- 7) 비밀번호가 없으면 아예 시작하지 않는다 ----------
anon, anon_sent, _ = new_session("")
check("비밀번호가 없으면 협상 자체를 안 한다",
      not [s for s in anon_sent if s.startswith("CAP")], anon_sent)

# ---------- 8) 협상을 시작했으면 반드시 끝낸다 ----------
# CAP END를 안 보내면 서버가 등록을 마무리하지 않아 **아무도 접속을 못 한다**
for label, replies in (
    ("지원 안 함", [":h CAP * LS :tls"]),
    ("요청 거절", [":h CAP * LS :sasl", ":h CAP * NAK :sasl"]),
    ("인증 실패", [":h CAP * LS :sasl", ":h CAP * ACK :sasl", ":h 904 Mong :nope"]),
    ("인증 성공", [":h CAP * LS :sasl", ":h CAP * ACK :sasl", ":h 903 Mong :ok"]),
):
    probe, probe_sent, _ = new_session("pw123")
    for reply in replies:
        probe.handle_incoming(line(reply))
    check(f"{label}: 협상을 끝낸다(안 끝내면 접속이 멈춘다)",
          "CAP END" in probe_sent and probe.cap_negotiating is False, probe_sent)

print("=== 검증 결과 (접속 과정 인증 SASL) ===")
all_ok = True
for name, ok, *detail in checks:
    extra = f"  <- {detail[0]}" if detail and detail[0] and not ok else ""
    print(f"[{'OK' if ok else 'FAIL'}] {name}{extra}")
    all_ok = all_ok and ok
print("\n전체 통과:", all_ok)
_sys.exit(0 if all_ok else 1)
