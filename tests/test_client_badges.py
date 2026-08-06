"""참여자가 무슨 프로그램으로 접속했는지 알아내고 로고로 보여주는 기능.

여기서 확인하는 것:
1. CTCP VERSION 줄을 제대로 만들고 읽는가 (irc_protocol)
2. 남이 물어오면 답하고, 답을 받으면 채팅으로 새지 않고 조용히 기록되는가 (코어)
3. 응답 문자열에서 어느 프로그램인지 알아내는가 (표)
4. 한꺼번에 묻지 않고 하나씩 묻는가 (프로브)
5. 참여자 목록 오른쪽에 닉네임보다 작은 로고가 그려지는가 (화면)
"""
import os as _os
import sys as _sys

_HERE = _os.path.dirname(_os.path.abspath(__file__))
_REPO = _os.path.dirname(_HERE)

_os.environ["QT_QPA_PLATFORM"] = "offscreen"
_sys.path.insert(0, _REPO)
_sys.path.insert(0, _HERE)

import irc_protocol
from chat_core import constants, events
from chat_core.session import build_session

checks = []


def check(name, ok, detail=""):
    checks.append((name, ok, detail))


# ---------- 1) 와이어 형식 ----------
request = irc_protocol.format_ctcp_version_request("앨리스")
check("물어보는 줄이 귓속말 + \\x01VERSION\\x01",
      request == "PRIVMSG 앨리스 :\x01VERSION\x01", request)
reply = irc_protocol.format_ctcp_version_reply("앨리스", "ChupChat 9.9")
check("답은 NOTICE로 보냄(무한 되받기 방지)", reply.startswith("NOTICE 앨리스 :\x01VERSION "), reply)
check("물음을 알아봄", irc_protocol.is_ctcp_version_request("\x01VERSION\x01"))
check("아이콘 프레임을 물음으로 오인하지 않음",
      not irc_protocol.is_ctcp_version_request("\x01FCAVATAR abc\x01"))
check("답에서 프로그램 이름만 뽑음",
      irc_protocol.parse_ctcp_version_reply("\x01VERSION WeeChat 4.4.2\x01") == "WeeChat 4.4.2")
check("답이 아닌 것은 None",
      irc_protocol.parse_ctcp_version_reply("\x01FCAVATAR abc\x01") is None)

# ---------- 2) 코어 (Qt도 소켓도 없이) ----------
sent = []
seen = []
session = build_session("irc", "irc.test", 6667, transport=sent.append, on_event=seen.append)
session.my_id = "몽키"

session.handle_incoming(irc_protocol.parse_line(":앨리스!u@h PRIVMSG 몽키 :\x01VERSION\x01"))
answered = [line for line in sent if line.startswith("NOTICE 앨리스")]
check("남이 물어오면 답한다", bool(answered), sent[-1] if sent else "보낸 것 없음")
check("답에 우리 이름이 들어간다",
      bool(answered) and constants.OUR_CLIENT_NAME in answered[0], answered[0] if answered else "")
check("물음은 채팅으로 새지 않는다",
      not any(isinstance(e, events.MessageReceived) for e in seen))

seen.clear()
session.handle_incoming(irc_protocol.parse_line(
    ":앨리스!u@h NOTICE 몽키 :\x01VERSION WeeChat 4.4.2\x01"))
updates = [e for e in seen if isinstance(e, events.ClientVersionUpdated)]
check("답을 받으면 알림 이벤트가 나온다", len(updates) == 1, [type(e).__name__ for e in seen])
check("누가 무엇을 쓰는지 기록된다",
      session.client_versions.get("앨리스") == "WeeChat 4.4.2", session.client_versions)
check("답이 채팅창에 안내문으로 뜨지 않는다",
      not any(isinstance(e, events.SystemNotice) for e in seen),
      [type(e).__name__ for e in seen])

# 진짜 NOTICE(서버 안내)는 예전처럼 그대로 보여야 한다
seen.clear()
session.handle_incoming(irc_protocol.parse_line(":irc.test NOTICE 몽키 :서버 점검 예정"))
check("보통 NOTICE는 예전처럼 안내문으로 뜬다",
      any(isinstance(e, events.SystemNotice) for e in seen))

# 아직 모르는 사람 골라내기
session.members["#일반"] = {"몽키", "앨리스", "Bob"}
unknown = session.unknown_client_users("#일반")
check("모르는 사람만 골라낸다(나와 이미 아는 사람 제외)", unknown == ["Bob"], unknown)

# 커스텀 서버는 우리 클라이언트만 붙으므로 묻지 않고 바로 정함
custom_sent = []
custom_seen = []
custom = build_session("custom", "h", 1, transport=custom_sent.append, on_event=custom_seen.append)
custom.my_id = "몽키"
custom.request_client_version("앨리스")
check("커스텀 서버에서는 물어보지 않는다(보낸 줄 없음)", not custom_sent, custom_sent)
check("커스텀 서버 참여자는 바로 우리 프로그램으로 표시",
      constants.OUR_CLIENT_NAME in custom.client_versions.get("앨리스", ""),
      custom.client_versions)

# ---------- 3) 프로그램 알아보기 ----------
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])
import gui_client as g  # noqa: E402

app.setStyleSheet(g.STYLE_SHEET)
from gui.client_badges import (CLIENT_BADGE_PX, ClientBadges,  # noqa: E402
                               resolve_spec, short_label, spec_for, spec_for_nick)

for version, expected in [("WeeChat 4.4.2", "weechat"),
                          ("HexChat 2.16.2 [x64] / Windows 11", "hexchat"),
                          ("irssi v1.4.5", "irssi"),
                          ("mIRC v7.75 Khaled Mardam-Bey", "mirc"),
                          ("matterbridge (discord)", "discord"),
                          ("ChupChat 2.0.2 - https://github.com/x", "chupchat")]:
    spec = spec_for(version)
    check(f"{version.split()[0]} 알아봄", spec is not None and spec.key == expected,
          spec.key if spec else None)
check("처음 보는 프로그램은 모른다고 함", spec_for("SomeNewClient 1.0") is None)
check("모르는 프로그램도 이름은 보여준다", short_label("SomeNewClient 1.0") == "SomeNewClient")

badges = ClientBadges(fetcher=None)          # 인터넷 없이도
weechat_badge = badges.badge("WeeChat 4.4.2")
check("로고를 못 받아도 글자 배지가 나온다",
      weechat_badge is not None and not weechat_badge.isNull())
check(f"배지가 작다({CLIENT_BADGE_PX}px)", weechat_badge.width() <= CLIENT_BADGE_PX)

# ---------- 4) 한 번에 우르르 묻지 않기 ----------
from gui.version_prober import (MAX_PROBES_PER_ROUND, PROBE_INTERVAL_MS,  # noqa: E402
                                VersionProber)

asked = []
prober = VersionProber(asked.append)
prober.enqueue(["a", "b", "c", "d"])
check("줄만 세우고 곧바로 묻지는 않는다(들어가는 순간 서버가 바쁨)", asked == [], asked)
check("네 명이 줄에 섬", prober.pending() == 4, prober.pending())
prober._ask_next()
prober._ask_next()
check("시간이 지나면 한 명씩", asked == ["a", "b"], asked)
prober.enqueue(["a", "b"])
check("이미 물어본 사람은 다시 안 묻는다", prober.pending() == 2, prober.pending())
check(f"간격이 넉넉하다({PROBE_INTERVAL_MS}ms)", PROBE_INTERVAL_MS >= 3000)
prober.enqueue([f"user{i}" for i in range(100)])
check(f"한 번에 {MAX_PROBES_PER_ROUND}명을 넘겨 세우지 않는다",
      prober.pending() <= MAX_PROBES_PER_ROUND + 2, prober.pending())
prober.reset()
check("초기화하면 줄이 비워진다", prober.pending() == 0)

# ---------- 4-1) 한 번 알아낸 것은 기억해서 다시 안 묻는다 ----------
import client_version_store  # noqa: E402

client_version_store.STORE_FILE = _os.path.join(
    _os.environ.get("TEMP", _HERE), "test_client_versions.json")
if _os.path.exists(client_version_store.STORE_FILE):
    _os.remove(client_version_store.STORE_FILE)

client_version_store.remember("irc.test", "앨리스", "WeeChat 4.4.2")
check("기억한 것을 다시 꺼내 쓸 수 있다",
      client_version_store.load("irc.test").get("앨리스") == "WeeChat 4.4.2")
check("다른 서버의 기억과 섞이지 않는다", client_version_store.load("other.test") == {})

import time as _time  # noqa: E402

first = _time.time()
client_version_store.remember("irc.test", "앨리스", "WeeChat 4.4.2")   # 같은 값 다시
raw = client_version_store._read()["irc.test"]["앨리스"]
check("같은 값이면 적은 시각을 건드리지 않는다(기한이 영원히 미뤄지지 않게)",
      raw[1] <= first, raw)

client_version_store.remember("irc.test", "앨리스", "HexChat 2.16")     # 프로그램을 바꿈
check("바뀐 프로그램은 갱신된다",
      client_version_store.load("irc.test").get("앨리스") == "HexChat 2.16")

old = client_version_store._read()
old["irc.test"]["옛날사람"] = ["irssi v1.0", _time.time() - client_version_store.REMEMBER_SEC - 10]
client_version_store._write(old)
check(f"{client_version_store.REMEMBER_DAYS}일이 지난 기억은 쓰지 않는다(다시 한 번 물어봄)",
      "옛날사람" not in client_version_store.load("irc.test"))
_os.remove(client_version_store.STORE_FILE)

# ---------- 4-2) 서버가 거절하면 멈춘다 ----------
client_version_store.STORE_FILE = _os.path.join(
    _os.environ.get("TEMP", _HERE), "test_client_versions2.json")
if _os.path.exists(client_version_store.STORE_FILE):
    _os.remove(client_version_store.STORE_FILE)

check("처음에는 물어봐도 된다", client_version_store.probe_allowed("irc.test"))
client_version_store.mark_probe_refused("irc.test")
check("거절당한 서버에는 다시 안 묻는다", not client_version_store.probe_allowed("irc.test"))
check("거절 표시가 사람 목록에 섞이지 않는다",
      client_version_store.load("irc.test") == {}, client_version_store.load("irc.test"))
check("다른 서버는 그대로 물어봐도 된다", client_version_store.probe_allowed("other.test"))
_os.remove(client_version_store.STORE_FILE)

# 거절 문구를 알아보는가(실제로 받은 문구 그대로)
from gui.main_window import MainWindow  # noqa: E402

markers = MainWindow._PROBE_REFUSED_MARKERS
real = "Multi-target messaging is not allowed (MangMang2)"
check(f"실제로 받은 거절 문구를 알아본다({real})",
      any(m in real.lower() for m in markers))
check("보통 서버 안내는 거절로 오해하지 않는다",
      not any(m in "환영합니다! 메인 채널은 #pdlab 입니다".lower() for m in markers))

# 거절당하면 멈추고, 뒤늦게 오는 같은 경고는 화면에 안 보여준다
client_version_store.STORE_FILE = _os.path.join(
    _os.environ.get("TEMP", _HERE), "test_client_versions3.json")
if _os.path.exists(client_version_store.STORE_FILE):
    _os.remove(client_version_store.STORE_FILE)

win = g.MainWindow()
win._host = "irc.refuse"
win._prober.enqueue(["앨리스", "Bob"])       # 물어보는 중인 상태를 만든다
check("서버와 무관한 안내는 그대로 보여준다",
      win.note_server_message("PDLab. IRC 에 오신 것을 환영합니다!") is False)
first = win.note_server_message("Multi-target messaging is not allowed (PDLab)")
check("거절당하면 그 경고를 화면에 안 보여준다(우리 안내문으로 갈음)", first is True)
check("거절당하면 즉시 멈춘다", win._prober.pending() == 0, win._prober.pending())
check("그 서버를 기억해 다시 안 묻는다",
      not client_version_store.probe_allowed("irc.refuse"))
later = win.note_server_message("Multi-target messaging is not allowed (Mong)")
check("이미 보낸 요청의 답이 뒤늦게 와도 조용히 버린다(경고가 줄줄이 쌓이지 않게)",
      later is True)
win.deleteLater()
if _os.path.exists(client_version_store.STORE_FILE):
    _os.remove(client_version_store.STORE_FILE)

# ---------- 4-3) 물어보지 않고도 우리 클라이언트를 알아본다 ----------
import avatar_store  # noqa: E402

quiet_sent = []
quiet_seen = []
quiet = build_session("irc", "irc.test", 6667, transport=quiet_sent.append,
                      on_event=quiet_seen.append)
quiet.my_id = "몽키"
tiny_png = ("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmM"
            "IQAAAABJRU5ErkJggg==")
frame = irc_protocol.format_ctcp_avatar("#일반", tiny_png)[0]
body = frame.split(" :", 1)[1]
quiet.handle_incoming(irc_protocol.parse_line(f":앨리스!u@h PRIVMSG #일반 :{body}"))
check("아이콘 프레임을 보낸 사람은 물어보지 않아도 춥채팅인 걸 안다",
      constants.OUR_CLIENT_NAME in quiet.client_versions.get("앨리스", ""),
      quiet.client_versions)
check("그러느라 서버에 아무 것도 보내지 않는다", not quiet_sent, quiet_sent)

# 모르는 CTCP 응답은 채팅창에 새면 안 된다(실제로 샜던 문구)
quiet_seen.clear()
quiet.handle_incoming(irc_protocol.parse_line(
    ":앨리스!u@h NOTICE 몽키 :ERRMSG VERSION :that is an unknown CTCP query".replace(
        "\x01", "")))
check("모르는 CTCP 응답이 채팅창에 안 뜬다",
      not any(isinstance(e, events.SystemNotice) for e in quiet_seen),
      [type(e).__name__ for e in quiet_seen])

# ---------- 4-4) 여럿이면 채널에 한 줄 (실측으로 정한 방식) ----------
# home.pdlab.kr 실측: 개인에게 연달아 보내면 "Multi-target messaging is not allowed"로
# 막혔지만, 채널에 한 줄 보내니 그 자리에 있던 전원이 답했다(WeeChat/ChupChat/다리 봇)
ch_sent = []
ch = build_session("irc", "irc.test", 6667, transport=ch_sent.append, on_event=lambda e: None)
ch.my_id = "몽키"
ch.request_client_versions_in_channel("#pdlab")
check("채널로는 딱 한 줄만 나간다", len(ch_sent) == 1, ch_sent)
check("그 한 줄이 채널 대상 CTCP VERSION이다",
      ch_sent[0] == "PRIVMSG #pdlab :VERSION".replace("\x01", ""), repr(ch_sent[0]))

# 다리 봇은 자기가 쓰는 라이브러리 이름을 답한다(실측: girc) - 이름 쪽을 믿어야 한다
real_bridge = "girc (github.com/lrstanley/girc) using go1.19.5 (linux, amd64)"
check("다리 봇이 라이브러리 이름을 답해도 디스코드로 본다",
      resolve_spec(real_bridge, "Discord").key == "discord",
      resolve_spec(real_bridge, "Discord").key)
check("사람이 쓰는 프로그램은 응답 그대로 판단한다",
      resolve_spec("WeeChat 3.5 (Mar 31 2022 11:36:01)", "hjsong").key == "weechat")

# ---------- 4-5) 사람이 아닌 것들과 휴대폰 ----------
# 실측: PDLab이 "Anope-2.0.21-git (...) services.pdlab.kr :UnrealIRCd 4+"라고 답했다.
# 사람이 쓰는 클라이언트가 아니라 서비스(NickServ/ChanServ를 돌리는 것)다
anope = "Anope-2.0.21-git (g15f5be7) services.pdlab.kr :UnrealIRCd 4+ - (enc_sha256)"
spec = resolve_spec(anope, "PDLab")
check(f"서비스를 알아본다({spec.label if spec else None})",
      spec is not None and spec.shape == "robot")
check("이름이 ~Serv면 서비스로 본다(NickServ/ChanServ 관례)",
      spec_for_nick("NickServ") is not None and spec_for_nick("NickServ").shape == "robot")
check("사람 이름은 서비스로 오해하지 않는다", spec_for_nick("hjsong") is None)

for version, shape, what in [("Eggdrop v1.9.5", "robot", "봇"),
                             ("Sopel 8.0.0", "robot", "봇"),
                             ("PircBotX 2.3.1", "robot", "봇 라이브러리"),
                             ("Goguma 0.7.0", "phone", "휴대폰"),
                             ("Palaver 1.2", "phone", "아이폰"),
                             ("Revolution IRC 1.0", "phone", "안드로이드")]:
    got = resolve_spec(version, "x")
    check(f"{version.split()[0]}은 {what} 모양", got is not None and got.shape == shape,
          got.shape if got else None)

check("WeeChat Android는 휴대폰으로(일반 WeeChat과 구분)",
      resolve_spec("WeeChat Android 0.19", "x").shape == "phone")
check("일반 WeeChat은 그대로 WeeChat",
      resolve_spec("WeeChat 4.4.2", "x").key == "weechat")

# 앱 목록에 없는 프로그램이어도 응답에 적힌 운영체제로 판단해야 한다.
# (표에 앱을 하나씩 등록하는 것보다 이 방법이 훨씬 많이 잡는다)
from gui.client_badges import kind_for  # noqa: E402

for version, expected, why in [
        ("WeeChat 4.4.2 (Android)", "phone", "안드로이드라고 적혀 있음"),
        ("irssi v1.4.5 - running on Android 13", "phone", "안드로이드에서 돌고 있음"),
        ("Palaver 2.0 (iOS 17.2)", "phone", "iOS라고 적혀 있음"),
        ("SomeNewApp 1.0 iPhone", "phone", "처음 보는 앱이지만 아이폰"),
        ("Quasseldroid 1.1", "phone", "이름부터 안드로이드판"),
        ("HexChat 2.16.2 [x64] / Windows 11", "", "PC라서 표시 없음"),
        ("mIRC v7.75", "", "PC"),
        ("MyCoolBot 1.0", "robot", "이름이 Bot으로 끝남"),
        ("SomeThing 1.0 relay bridge", "robot", "다리라고 밝힘")]:
    got = kind_for(version, "x")
    check(f"{version[:30]} -> {expected or 'PC'} ({why})", got == expected, got)
check("이름이 ~Bot이면 사람이 아니다", kind_for("AwesomeApp 2", "GitHubBot") == "robot")
# 실측: hjsong_mobile이 "IRCCloud irccloud.com"이라고만 답했다. IRCCloud는 웹에서 쓰든
# 휴대폰에서 쓰든 같은 말을 하므로, 응답만으로는 절대 알 수 없고 이름을 봐야 한다
check("응답에 단서가 없어도 이름이 ~_mobile이면 휴대폰",
      kind_for("IRCCloud irccloud.com", "hjsong_mobile") == "phone")
check("이름에 droid가 들어가도 휴대폰", kind_for("SomeApp 1", "user-droid") == "phone")
only_main, only_marker = ClientBadges(fetcher=None).badges("", nick="누구_mobile")
check("프로그램을 몰라도 이름만으로 휴대폰 표시는 뜬다",
      only_main is None and only_marker is not None)
check("보통 닉네임은 사람으로 본다", kind_for("HexChat 2.16", "hjsong") == "")

shape_badges = ClientBadges(fetcher=None)
for version in ("Anope-2.0.21", "Goguma 0.7"):
    made = shape_badges.badge(version)
    check(f"{version.split()[0]} 배지가 그려진다(인터넷 없이도)",
          made is not None and not made.isNull())
    check(f"{version.split()[0]} 배지도 작다({CLIENT_BADGE_PX}px 이하)",
          made.width() <= CLIENT_BADGE_PX)

# ---------- 5) 화면 표시 ----------
page = g.ChatPage(on_send=lambda c, t: None, on_add_channel=lambda: None,
                  on_leave_channel=lambda c: None, on_set_avatar=lambda: None)
page.resize(900, 560)
page.show()
page.add_channel("#일반")
panel = page.member_panel
panel.set_members("#일반", ["몽키", "앨리스"])
panel.show_channel("#일반")
for _ in range(4):
    app.processEvents()
check("아직 모르는 사람에게는 로고가 없다", panel._badge_for("앨리스") == (None, None))

page.set_client_version("앨리스", "WeeChat 4.4.2")
for _ in range(4):
    app.processEvents()
badge, _marker = panel._badge_for("앨리스")
check("알아낸 사람에게는 로고가 생긴다", badge is not None and not badge.isNull())

row = panel.list.item(1)
check("줄에 실제 아이디가 달려 있다(로고를 그릴 때 필요)",
      row.data(0x0100) in ("앨리스", "몽키"), row.data(0x0100))
check("툴팁으로 어떤 프로그램인지 알 수 있다", "WeeChat" in (row.toolTip() or ""), row.toolTip())

metrics = panel.list.fontMetrics().height()
check(f"로고가 닉네임 글자({metrics}px)를 넘지 않는다", badge.height() <= metrics, badge.height())

panel.reset()
check("로그아웃하면 프로그램 정보도 지워진다", panel.client_version("앨리스") == "")

# 로고 옆에 종류 표시가 따로 붙는다(겹쳐 그리면 12px에서 안 보인다)
two = ClientBadges(fetcher=None)
pc_main, pc_marker = two.badges("WeeChat 4.4.2")
check("PC 프로그램은 로고만(표시 칸은 비움)", pc_main is not None and pc_marker is None)
m_main, m_marker = two.badges("WeeChat Android 0.19")
check("휴대폰이면 로고와 표시가 둘 다", m_main is not None and m_marker is not None)
b_main, b_marker = two.badges("Anope-2.0.21")
check("봇/서비스도 로고와 표시가 둘 다", b_main is not None and b_marker is not None)
check("디스코드 연결도 봇이므로 표시가 붙는다",
      two.badges("girc (github.com/x/girc)", nick="Discord")[1] is not None)
check("표시도 닉네임 글자를 안 넘는다",
      all(b.width() <= CLIENT_BADGE_PX for b in two.badges("Goguma 0.7") if b))

# ---------- 6) 디스코드 다리처럼 '물어봐도 소용없는' 계정 ----------
# 채널이 통째로 디스코드와 이어져 있는 경우, 그 계정은 사람이 쓰는 IRC 프로그램이 아니라
# 이어주는 봇이다. CTCP로 물어도 봇 이름이 나오거나 아예 답이 없다 - 이름으로 알아본다
panel.set_members("#일반", ["Discord", "PDLab", "몽키"])
panel.show_channel("#일반")
for _ in range(4):
    app.processEvents()
check("이름이 Discord면 답이 없어도 로고가 뜬다", panel._badge_for("Discord")[0] is not None)
check("이름으로 짐작한 것임을 툴팁에 밝힌다",
      "짐작" in (panel.list.item(0).toolTip() or ""), panel.list.item(0).toolTip())
check("아무 단서도 없는 사람은 그대로 비워둔다", panel._badge_for("몽키") == (None, None))
check("봇 이름으로 답해도 다리로 알아본다",
      spec_for_nick("discord-bridge") is not None)

# 모르는 응답의 배지는 '?'가 아니라 응답의 첫 글자다.
# 12px에서 굵은 물음표는 곡선이 뭉개져 숫자 7처럼 보인다는 신고를 받았다
page.set_client_version("PDLab", "PircBotX 2.3.1")
for _ in range(4):
    app.processEvents()
unknown_badge = panel._badge_for("PDLab")[0]
check("모르는 프로그램도 배지가 나온다", unknown_badge is not None)
check("툴팁에 응답 원문이 그대로 보인다(표에 추가할 수 있게)",
      "PircBotX 2.3.1" in (panel.list.item(1).toolTip() or ""), panel.list.item(1).toolTip())

print("=== 검증 결과 (접속 프로그램 표시) ===")
all_ok = True
for name, ok, *detail in checks:
    extra = f"  <- {detail[0]}" if detail and detail[0] and not ok else ""
    print(f"[{'OK' if ok else 'FAIL'}] {name}{extra}")
    all_ok = all_ok and ok
print("\n전체 통과:", all_ok)
_sys.exit(0 if all_ok else 1)
