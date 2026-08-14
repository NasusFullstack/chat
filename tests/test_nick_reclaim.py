"""회선이 바뀌었을 때 원래 이름을 되찾는가.

실제 신고(2026-08-13, 채널 대화에서): "와이파이-랜선 변경시 로그인정보 바뀌는 거".

무슨 일이 일어나는가:
1. 회선이 바뀌면 예전 TCP 연결은 조용히 죽지만, 서버는 그 사실을 **바로 모른다**.
   서버가 알아채는 데 최대 180초가 걸린다(핑 타임아웃 - 실측으로 확인).
2. 그 사이에 다시 접속하면 내 이름은 아직 '유령'이 쥐고 있어서 못 쓴다.
   서버는 433(이미 사용 중)을 답하고, 우리는 뒤에 _를 붙여 접속한다(Mong -> Mong_).
3. **예전에는 여기서 끝이었다.** 유령이 사라진 뒤에도 계속 Mong_로 남았고, 사람마다
   Mong_, Ming_, Milk_ 같은 이름이 쌓였다(실제 기록에 남아 있다).

지금은 원래 이름을 기억해뒀다가 주기적으로 되찾는다. 되찾기 시도가 거절당하는 것은
사용자가 한 일이 아니므로 조용히 넘어가고, 유령이 사라지는 순간 저절로 성공한다.
"""
import os as _os
import sys as _sys

_HERE = _os.path.dirname(_os.path.abspath(__file__))
_REPO = _os.path.dirname(_HERE)

_os.environ["QT_QPA_PLATFORM"] = "offscreen"
_sys.path.insert(0, _REPO)

import irc_protocol  # noqa: E402
from chat_core import events as domain_events  # noqa: E402
from chat_core.session import build_session  # noqa: E402

checks = []


def check(name, ok, detail=""):
    checks.append((name, ok, detail))


def line(raw):
    return irc_protocol.parse_line(raw)


sent, events = [], []
session = build_session("irc", "home.pdlab.kr", 6667,
                        transport=sent.append, on_event=events.append)
session.login("Mong", "")
check("접속할 때 원하는 이름을 기억한다", session.wanted_nick == "Mong", session.wanted_nick)

# 유령 세션 때문에 이름이 밀린다
session.handle_incoming(line(":h 433 * Mong :Nickname is already in use."))
session.handle_incoming(line(":h 001 Mong_ :Welcome"))
check(f"이름이 밀려도 접속은 된다({session.my_id})", session.my_id == "Mong_", session.my_id)
check("원하는 이름은 그대로 기억한다", session.wanted_nick == "Mong", session.wanted_nick)

# 되찾기 시도
sent.clear()
events.clear()
session.reclaim_nickname()
check(f"원래 이름으로 다시 요청한다({sent})", sent == ["NICK Mong"], sent)

# 아직 유령이 안 사라졌으면 거절당한다 - 이건 사용자가 한 일이 아니므로 조용해야 한다
session.handle_incoming(line(":h 433 * Mong :Nickname is already in use."))
noisy = [e for e in events if isinstance(e, (domain_events.NicknameChangeFailed,
                                             domain_events.AuthFailed))]
check(f"되찾기가 막혀도 오류를 띄우지 않는다({[type(e).__name__ for e in events]})",
      not noisy, noisy)
check("연결도 그대로 유지된다(끊지 않는다)", session.my_id == "Mong_", session.my_id)

# 유령이 사라지면 다음 시도에서 성공한다
sent.clear()
session.reclaim_nickname()
session.handle_incoming(line(":Mong_!u@h NICK :Mong"))
check(f"유령이 사라지면 원래 이름으로 돌아온다({session.my_id})",
      session.my_id == "Mong", session.my_id)

# 되찾았으면 더 조르지 않는다
sent.clear()
session.reclaim_nickname()
check("원래 이름을 쓰고 있으면 아무 것도 안 보낸다", not sent, sent)

# 사용자가 직접 바꾼 이름이 새 기준이 된다
session.set_nickname("몽키")
check("사용자가 고른 이름이 새 기준이 된다", session.wanted_nick == "몽키",
      session.wanted_nick)

# 사용자가 직접 바꾸다 실패한 것은 **알려야 한다**(되찾기와 구분)
events.clear()
session.nick_change_pending = True
session.handle_incoming(line(":h 433 * 몽키 :Nickname is already in use."))
told = [e for e in events if isinstance(e, domain_events.NicknameChangeFailed)]
check("사용자가 직접 바꾸다 막힌 것은 알려준다", bool(told),
      [type(e).__name__ for e in events])

# 로그인 전 단계에서는 예전처럼 _를 붙여 재시도해야 한다(접속 자체가 안 되면 안 되니까)
fresh_sent = []
fresh = build_session("irc", "h", 1, transport=fresh_sent.append, on_event=lambda e: None)
fresh.login("Mong", "")
fresh_sent.clear()
fresh.handle_incoming(line(":h 433 * Mong :Nickname is already in use."))
check(f"로그인 중에는 _를 붙여서라도 접속한다({fresh_sent})",
      fresh_sent == ["NICK Mong_"], fresh_sent)

# 우리 서버(커스텀)는 해당 없음
custom_sent = []
custom = build_session("custom", "h", 1, transport=custom_sent.append,
                       on_event=lambda e: None)
custom.my_id = "몽키"
custom.wanted_nick = "다른이름"
custom.reclaim_nickname()
check("우리 서버에서는 되찾을 일이 없다", not custom_sent, custom_sent)

# ---------- 유령을 즉시 쫓아낼 수 있는 경우 ----------
# 실측(home.pdlab.kr, 2026-08-14): 이 서버의 NickServ는 GHOST가 없고 RECOVER를 쓴다.
# "다른 사람이 내 이름을 쥐고 있으면 죽인다(옛 GHOST와 같음)" - 단, 이름이 등록돼 있고
# 비밀번호가 있어야 한다. 비밀번호가 없으면 쓸 수 없으므로 보내면 안 된다
with_pw_sent = []
with_pw = build_session("irc", "h", 6667, transport=with_pw_sent.append,
                        on_event=lambda e: None)
with_pw.login("Mong", "비밀번호")
with_pw_sent.clear()
with_pw.handle_incoming(line(":h 433 * Mong :Nickname is already in use."))
recover = [s for s in with_pw_sent if "RECOVER" in s]
check(f"비밀번호가 있으면 유령을 즉시 쫓아낸다({recover})",
      recover == ["PRIVMSG NickServ :RECOVER Mong 비밀번호"], with_pw_sent)
check("그래도 접속은 계속한다(_를 붙여 들어간다)",
      "NICK Mong_" in with_pw_sent, with_pw_sent)

no_pw_sent = []
no_pw = build_session("irc", "h", 6667, transport=no_pw_sent.append, on_event=lambda e: None)
no_pw.login("Mong", "")
no_pw_sent.clear()
no_pw.handle_incoming(line(":h 433 * Mong :Nickname is already in use."))
check("비밀번호가 없으면 서비스에 부탁하지 않는다(쓸 수 없는 명령이다)",
      not [s for s in no_pw_sent if "RECOVER" in s], no_pw_sent)

# ---------- 되찾기가 서버에 홍수로 보이지 않는가 ----------
# 이름을 **영영 못 되찾는 경우**(진짜 다른 사람이 쓰는 중)에도 짧은 간격으로 계속
# 시도하면 서버가 닉네임 변경 홍수로 본다. 실측: 15초마다면 한 시간에 240줄.
# 그래서 시도할수록 간격을 늘리고 정해진 횟수 뒤에는 포기한다
from chat_core import constants  # noqa: E402

flood_sent = []
flood = build_session("irc", "h", 6667, transport=flood_sent.append, on_event=lambda e: None)
flood.login("Mong", "")
flood.handle_incoming(line(":h 433 * Mong :in use"))
flood.handle_incoming(line(":h 001 Mong_ :Welcome"))
flood_sent.clear()
for _ in range(50):                      # 타이머가 50번 도는 동안
    flood.nick_reclaim_next_at = 0       # 시간이 지난 것처럼
    flood.reclaim_nickname()
    flood.handle_incoming(line(":h 433 * Mong :in use"))
check(f"영영 못 되찾아도 정해진 횟수에서 멈춘다({len(flood_sent)}번)",
      len(flood_sent) <= constants.NICK_RECLAIM_MAX_ATTEMPTS, len(flood_sent))

check("간격이 시도할수록 늘어난다(홍수 방지)",
      constants.NICK_RECLAIM_MAX_DELAY_SEC > constants.NICK_RECLAIM_FIRST_DELAY_SEC)
check("비밀번호가 있으면 첫 시도는 훨씬 빠르다(_로 머무는 시간을 없앤다)",
      constants.NICK_RECLAIM_FAST_DELAY_SEC < constants.NICK_RECLAIM_FIRST_DELAY_SEC,
      (constants.NICK_RECLAIM_FAST_DELAY_SEC, constants.NICK_RECLAIM_FIRST_DELAY_SEC))

# 사용자가 이름을 새로 고르면 다시 처음부터 시도할 수 있어야 한다
flood.set_nickname("새이름")
check("이름을 새로 고르면 시도 횟수가 초기화된다", flood.nick_reclaim_attempts == 0,
      flood.nick_reclaim_attempts)

print("=== 검증 결과 (이름 되찾기) ===")
all_ok = True
for name, ok, *detail in checks:
    extra = f"  <- {detail[0]}" if detail and detail[0] and not ok else ""
    print(f"[{'OK' if ok else 'FAIL'}] {name}{extra}")
    all_ok = all_ok and ok
print("\n전체 통과:", all_ok)
_sys.exit(0 if all_ok else 1)
