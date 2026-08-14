"""이상한 입력을 잔뜩 넣어도 앱이 안 터지는가.

지금까지의 검사는 "올바른 경우에 올바르게 도는가"를 봤다. 그런데 실제 사고는 대개
**예상 못 한 입력**에서 났다(잘린 CTCP 프레임이 채팅으로 샌 일, 색 번호가 글자로
튀어나온 일, 링크 하나에 화면이 13초 멈춘 일).

그래서 여기서는 일부러 험한 것을 넣는다:
- 서버가 보낼 리 없는 이상한 줄(빈 줄, 잘린 줄, 파라미터가 모자란 줄, 아주 긴 줄)
- 사람이 칠 수 있는 이상한 글(제어문자, 이모지, 아주 긴 글, HTML 같은 글)
- 순서가 뒤엉킨 상황(로그인 전에 메시지가 온다든지)

**터지지 않는 것**이 통과 조건이다(무엇을 하든 예외 없이 넘어가야 한다).
"""
import os as _os
import sys as _sys

_HERE = _os.path.dirname(_os.path.abspath(__file__))
_REPO = _os.path.dirname(_HERE)

_os.environ["QT_QPA_PLATFORM"] = "offscreen"
_sys.path.insert(0, _REPO)

import random  # noqa: E402
import traceback  # noqa: E402

from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])

import irc_protocol  # noqa: E402
import link_meta  # noqa: E402
from chat_core.session import build_session  # noqa: E402
from gui import irc_format  # noqa: E402
from gui.preview import youtube  # noqa: E402

checks = []
failures = []


def check(name, ok, detail=""):
    checks.append((name, ok, detail))


def survives(name, action) -> bool:
    """터지면 그 자리를 기록한다(무엇이 터졌는지 알아야 고칠 수 있다)."""
    try:
        action()
        return True
    except Exception:  # noqa: BLE001 - 여기서는 무엇이든 잡아서 보고하는 게 목적
        failures.append(f"{name}\n{traceback.format_exc(limit=3)}")
        return False


# ---------- 1) 서버가 보낼 수 있는 이상한 줄 ----------
WEIRD_LINES = [
    "", " ", "\r\n", ":", "::::", ":server", ":server 001",
    "PING", "PING :", "PRIVMSG", "PRIVMSG #ch", "PRIVMSG #ch :",
    ":a!b@c PRIVMSG",
    ":a!b@c PRIVMSG #ch :\x01VERSION",              # 닫히지 않은 CTCP
    ":a!b@c PRIVMSG #ch :\x01FCAVATAR 잘림",
    ":a!b@c PRIVMSG #ch :\x03",                      # 색 지정만 있고 숫자 없음
    ":a!b@c PRIVMSG #ch :\x0399999 이상한 색",
    ":a!b@c NOTICE #ch :\x01\x01\x01",
    ":server 433", ":server 433 *", ":server 001", ":server 366 me",
    ":server 353 me = #ch :", ":server 005 me " + "X" * 400,
    "@tag=1;tag2=2 :a!b@c PRIVMSG #ch :태그 달린 줄",
    ":a!b@c NICK", ":a!b@c QUIT", ":a!b@c JOIN", ":a!b@c PART",
    ":server CAP", ":server CAP *", ":server CAP * LS", "AUTHENTICATE",
    "가나다" * 300,                                   # 아주 긴 줄
    "\x00\x01\x02 이상한 문자들",
]

sent, events = [], []
session = build_session("irc", "h", 6667, transport=sent.append, on_event=events.append)
session.login("나", "")
broken = 0
for raw in WEIRD_LINES:
    if not survives(f"이상한 줄: {raw[:40]!r}",
                    lambda raw=raw: session.handle_incoming(irc_protocol.parse_line(raw))):
        broken += 1
check(f"서버가 이상한 줄을 보내도 안 터진다({len(WEIRD_LINES)}가지)", broken == 0, broken)

# 로그인 전에 아무 줄이나 와도 안 터져야 한다
early = build_session("irc", "h", 1, transport=lambda p: None, on_event=lambda e: None)
broken = 0
for raw in WEIRD_LINES:
    if not survives(f"로그인 전 이상한 줄: {raw[:30]!r}",
                    lambda raw=raw: early.handle_incoming(irc_protocol.parse_line(raw))):
        broken += 1
check("로그인 전에 아무 줄이 와도 안 터진다", broken == 0, broken)

# 커스텀 서버 쪽도 마찬가지
custom = build_session("custom", "h", 1, transport=lambda p: None, on_event=lambda e: None)
WEIRD_DICTS = [{}, {"type": None}, {"type": "chat"}, {"type": "chat", "text": None},
               {"type": 123}, {"type": "auth_result"}, {"type": "userlist"},
               {"type": "chat", "channel": None, "from": None, "text": "가"},
               {"type": "x" * 500}]
broken = 0
for payload in WEIRD_DICTS:
    if not survives(f"이상한 메시지: {payload}",
                    lambda payload=payload: custom.handle_incoming(payload)):
        broken += 1
check(f"우리 서버가 이상한 메시지를 보내도 안 터진다({len(WEIRD_DICTS)}가지)", broken == 0, broken)

# ---------- 2) 사람이 칠 수 있는 이상한 글 ----------
WEIRD_TEXTS = [
    "", " ", "\x00", "\x01\x01", "\x03", "\x0399", "\x02\x1d\x1f",
    "<script>alert(1)</script>", "&lt;&amp;&gt;", "&" * 100,
    "가" * 5000, "a" * 5000, "😀" * 500, "​" * 100,
    "https://" + "a" * 900, "http://192.168.0.1/", "http://[::1]/",
    "/help", "/", "//", "/nick", "/me", "@" * 200,
]
broken = 0
for text in WEIRD_TEXTS:
    if not survives(f"이상한 입력: {text[:24]!r}",
                    lambda text=text: session.send_message("#ch", text)):
        broken += 1
check(f"사람이 이상한 글을 쳐도 안 터진다({len(WEIRD_TEXTS)}가지)", broken == 0, broken)

# ---------- 3) 글자 꾸밈/자르기/주소 판별 ----------
broken = 0
for text in WEIRD_TEXTS:
    for name, action in (
        ("색 해석", lambda text=text: irc_format.to_html(text)),
        ("색 걷어내기", lambda text=text: irc_format.strip(text)),
        ("나눠 보내기", lambda text=text: irc_protocol.split_message(text)),
        ("주소 판별", lambda text=text: link_meta.is_safe_public_url(text)),
        ("유튜브 판별", lambda text=text: youtube.is_youtube(text)),
        ("oEmbed 해석", lambda text=text: youtube.parse_oembed(text.encode(), "u")),
    ):
        if not survives(f"{name}: {text[:20]!r}", action):
            broken += 1
check("글자 처리 함수들이 어떤 입력에도 안 터진다", broken == 0, broken)

# 나눈 조각은 항상 512바이트 규칙을 지켜야 한다(길이와 상관없이)
too_long = []
for text in WEIRD_TEXTS + ["가" * 3000, "x" * 3000]:
    for piece in irc_protocol.split_message(text):
        size = len(irc_protocol.format_privmsg("#pdlab", piece).encode()) + 2 + 60
        if size > 512:
            too_long.append((text[:20], size))
check(f"어떤 입력이든 나눈 조각이 512바이트를 안 넘는다({len(too_long)}건 위반)",
      not too_long, too_long[:3])

# ---------- 4) 무작위로 만든 줄 ----------
random.seed(20260814)
alphabet = "abc가나다 :!@#\x01\x02\x03\x0f\r\n*+#&"
broken = 0
for _ in range(300):
    raw = "".join(random.choice(alphabet) for _ in range(random.randint(0, 60)))
    if not survives(f"무작위 줄: {raw[:24]!r}",
                    lambda raw=raw: session.handle_incoming(irc_protocol.parse_line(raw))):
        broken += 1
check(f"무작위로 만든 줄 300개에도 안 터진다({broken}건 실패)", broken == 0, broken)

# ---------- 5) 화면까지 태워보기 ----------
import gui_client as g  # noqa: E402

app.setStyleSheet(g.STYLE_SHEET)
view = g.ChannelLogView("#fuzz")
view.resize(500, 400)
view.show()
avatar = g._hashed_avatar_pixmap("t")
broken = 0
for text in WEIRD_TEXTS:
    if not survives(f"화면에 그리기: {text[:20]!r}",
                    lambda text=text: view.append_message("남", text, False, 0, avatar)):
        broken += 1
for _ in range(6):
    app.processEvents()
check(f"이상한 글을 화면에 그려도 안 터진다({broken}건 실패)", broken == 0, broken)

print("=== 검증 결과 (험한 입력 견디기) ===")
all_ok = True
for name, ok, *detail in checks:
    extra = f"  <- {detail[0]}" if detail and detail[0] and not ok else ""
    print(f"[{'OK' if ok else 'FAIL'}] {name}{extra}")
    all_ok = all_ok and ok
if failures:
    print(f"\n터진 곳 {len(failures)}건 - 앞의 3건:")
    for item in failures[:3]:
        print(item)
print("\n전체 통과:", all_ok)
_sys.exit(0 if all_ok else 1)
