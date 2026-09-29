"""중계 서버와 실제로 주고받는가.

인터넷이 없거나 서버가 내려가 있으면 그 항목은 **건너뛴다**(실패로 세지 않는다) -
러너가 인터넷 없이도 돌아야 하기 때문. 다만 건너뛴 건 눈에 띄게 찍는다.
"""
import os as _os
import sys as _sys

_HERE = _os.path.dirname(_os.path.abspath(__file__))
_REPO = _os.path.dirname(_HERE)

_os.environ["QT_QPA_PLATFORM"] = "offscreen"
_sys.path.insert(0, _REPO)

import io  # noqa: E402
import time  # noqa: E402
import urllib.error  # noqa: E402
import urllib.request  # noqa: E402

from PySide6.QtCore import QEventLoop, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])

import battle_protocol as bp  # noqa: E402
from gui.battle.net import RELAY_URL, BattleLink  # noqa: E402

checks = []
skipped = []


def check(name, ok, detail=""):
    checks.append((name, ok, detail))


def pump(seconds):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.005)


def wait_for(predicate, seconds=12):
    """조건이 될 때까지 기다린다. app.quit()을 쓰면 안 된다(CLAUDE.md 11-3)."""
    end = time.time() + seconds
    while time.time() < end and not predicate():
        app.processEvents()
        time.sleep(0.005)
    return predicate()


# ---------- 1) 네트워크 없이 확인되는 것 ----------
source = io.open(_os.path.join(_REPO, "gui/battle/net.py"), encoding="utf-8").read()
check("받은 것을 규약 검사에 통과시킨다", "bp.decode(" in source)
check("보낼 때도 규약이 만든 줄을 쓴다", "bp.encode(" in source)
check("조작에 자리 번호를 안 싣는다(서버가 붙인다)",
      '"slot"' not in source.split("def send_input", 1)[1].split("def ", 1)[0], source)
# 설명 글에는 "TOFU를 쓰면 안 된다"는 이유가 적혀 있으므로, 글자만 세면 안 되고
# **실제로 가져다 쓰는지**를 봐야 한다
check("지문 고정(TOFU)을 가져다 쓰지 않는다 - 가로채는 백신이 있으면 전부 막힌다",
      "import trusted_certs" not in source and "trusted_certs.fingerprint" not in source
      and "setPeerVerifyMode" not in source, source[:0])
check("연결 시간 제한이 있다", "CONNECT_TIMEOUT_MS" in source)
check("주소가 중계 서버다", RELAY_URL.startswith("wss://"), RELAY_URL)

link = BattleLink()
check("처음에는 연결이 없다", link.is_open() is False)
check("아직 자리가 없다", link.my_slot == -1)
link.send_input(1, bp.KEY_FIRE)          # 연결 없이 보내도 안 터져야 한다
link.send_hit(0)
link.start_battle()
check("연결이 없을 때 보내도 안 터진다", True)

# ---------- 2) 서버가 살아있는가 ----------
alive = False
try:
    with urllib.request.urlopen("https://jsserv.pdlab.kr/battle", timeout=8) as response:
        alive = response.status == 200
except (urllib.error.URLError, OSError, TimeoutError):
    alive = False

if not alive:
    skipped.append("중계 서버에 닿지 않아 실제 접속 검사를 건너뜀")
else:
    room = bp.new_room()

    host = BattleLink()
    host_state = {"joined": None, "peers": [], "started": False, "inputs": [],
                  "dead": [], "left": [], "refused": None, "failed": None}
    host.joined.connect(lambda slot, color, cap, players:
                        host_state.update(joined=(slot, color, cap, players)))
    host.peer_joined.connect(lambda slot, nick, color: host_state["peers"].append(
        (slot, nick, color)))
    host.peer_left.connect(lambda slot: host_state["left"].append(slot))
    host.started.connect(lambda: host_state.update(started=True))
    host.peer_input.connect(lambda slot, tick, keys: host_state["inputs"].append(
        (slot, tick, keys)))
    host.peer_dead.connect(lambda slot, by: host_state["dead"].append((slot, by)))
    host.refused.connect(lambda why: host_state.update(refused=why))
    host.failed.connect(lambda why: host_state.update(failed=why))

    host.join(room, "방장", color=3, cap=2)
    got = wait_for(lambda: host_state["joined"] is not None or host_state["failed"])
    check(f"방장이 들어간다({host_state['joined']})",
          got and host_state["joined"] is not None, host_state)

    if host_state["joined"]:
        slot, color, cap, players = host_state["joined"]
        check(f"0번 자리를 받는다({slot})", slot == 0, slot)
        check(f"고른 색 그대로({color})", color == 3, color)
        check(f"정한 정원 그대로({cap}명)", cap == 2, cap)
        check(f"처음엔 아무도 없다({players})", players == [], players)
        check(f"연결이 열려 있다", host.is_open() is True)

        guest = BattleLink()
        guest_state = {"joined": None, "started": False, "refused": None}
        guest.joined.connect(lambda s, c, p, pl: guest_state.update(joined=(s, c, p, pl)))
        guest.started.connect(lambda: guest_state.update(started=True))
        guest.refused.connect(lambda why: guest_state.update(refused=why))
        guest.join(room, "손님", color=3)     # 일부러 같은 색을 고른다

        wait_for(lambda: guest_state["joined"] is not None)
        check(f"손님도 들어간다({guest_state['joined']})",
              guest_state["joined"] is not None, guest_state)
        if guest_state["joined"]:
            g_slot, g_color, g_cap, g_players = guest_state["joined"]
            check(f"1번 자리({g_slot})", g_slot == 1, g_slot)
            check(f"겹치는 색이면 다른 색을 준다(원한 3 -> 받은 {g_color})", g_color != 3,
                  g_color)
            check(f"손님이 정원을 못 바꾼다({g_cap}명)", g_cap == 2, g_cap)
            check(f"대기방에 방장이 보인다({g_players})",
                  g_players and g_players[0]["nick"] == "방장", g_players)

        wait_for(lambda: host_state["peers"])
        check(f"방장에게 '손님이 들어왔다'({host_state['peers']})",
              host_state["peers"] and host_state["peers"][0][0] == 1, host_state["peers"])

        # 손님이 시작을 눌러도 안 먹힌다
        guest.start_battle()
        pump(1.0)
        check("손님이 시작을 눌러도 시작되지 않는다", host_state["started"] is False)

        host.start_battle()
        wait_for(lambda: host_state["started"] and guest_state["started"])
        check("방장이 누르면 둘 다 시작된다",
              host_state["started"] and guest_state["started"],
              (host_state["started"], guest_state["started"]))

        started_at = time.perf_counter()
        guest.send_input(42, bp.KEY_FIRE | bp.KEY_LEFT)
        wait_for(lambda: host_state["inputs"])
        elapsed = (time.perf_counter() - started_at) * 1000
        check(f"조작이 상대에게 도착한다({host_state['inputs']}, {elapsed:.0f}ms)",
              host_state["inputs"] == [(1, 42, bp.KEY_FIRE | bp.KEY_LEFT)],
              host_state["inputs"])

        guest.send_dead(0)
        wait_for(lambda: host_state["dead"])
        check(f"격추 신고가 도착한다({host_state['dead']})",
              host_state["dead"] == [(1, 0)], host_state["dead"])

        # 이미 시작된 방에는 못 들어온다
        late = BattleLink()
        late_state = {"refused": None}
        late.refused.connect(lambda why: late_state.update(refused=why))
        late.join(room, "늦은사람")
        wait_for(lambda: late_state["refused"] is not None)
        check(f"시작된 뒤에는 이유와 함께 거절({late_state['refused']})",
              late_state["refused"] and "시작" in late_state["refused"], late_state)

        # 정원이 차서 거절되는 건 **아직 시작 안 한 방**에서 봐야 한다
        # (시작된 방은 정원과 무관하게 거절되므로 뒤섞이면 무엇을 확인한 건지 알 수 없다)
        small = bp.new_room()
        seats = []
        for index in range(2):
            member = BattleLink()
            state = {"joined": None}
            member.joined.connect(lambda s, c, p, pl, st=state: st.update(joined=s))
            member.join(small, f"자리{index}", cap=2)
            wait_for(lambda st=state: st["joined"] is not None)
            seats.append(member)
        full = BattleLink()
        full_state = {"refused": None}
        full.refused.connect(lambda why: full_state.update(refused=why))
        full.join(small, "셋째")
        wait_for(lambda: full_state["refused"] is not None)
        check(f"정원이 차면 이유와 함께 거절({full_state['refused']})",
              full_state["refused"] and "정원" in full_state["refused"], full_state)
        for member in seats:
            member.leave()

        guest.leave()
        wait_for(lambda: host_state["left"])
        check(f"나가면 알려준다({host_state['left']})", host_state["left"] == [1],
              host_state["left"])

        host.leave()
        pump(0.4)
        check("떠나면 연결이 닫힌다", host.is_open() is False)
        check("떠날 때는 '끊겼다'고 안 알린다(일부러 끊은 것이므로)",
              host_state["failed"] is None, host_state["failed"])

print("=== 검증 결과 (중계 서버 연결) ===")
all_ok = True
for name, ok, *detail in checks:
    extra = f"  <- {detail[0]}" if detail and detail[0] and not ok else ""
    print(f"[{'OK' if ok else 'FAIL'}] {name}{extra}")
    all_ok = all_ok and ok
for note in skipped:
    print(f"[건너뜀] {note}")
print(f"\n검사 {len(checks)}개")
print("전체 통과:", all_ok)
_sys.exit(0 if all_ok else 1)
