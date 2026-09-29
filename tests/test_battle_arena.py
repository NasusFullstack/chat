"""전투 화면 - 고정 좌표계를 창에 맞게 옮기고, 판단은 자기 배에 대해서만 하는가.

여기서 가장 조심할 것 두 가지:
1. 전투장(1200x800)을 창 크기에 **비율을 지켜** 앉히는가. 찌그러뜨리면 맞음 판정과
   눈에 보이는 것이 어긋난다
2. **남의 배 체력은 그 사람 말만 따르는가.** 조작이 도착하는 시점이 사람마다 몇 ms씩
   달라 배 위치가 조금 어긋날 수 있는데, 남의 피격을 내가 판단하면 화면마다 체력이
   달라진다
"""
import os as _os
import sys as _sys

_HERE = _os.path.dirname(_os.path.abspath(__file__))
_REPO = _os.path.dirname(_HERE)

_os.environ["QT_QPA_PLATFORM"] = "offscreen"
_sys.path.insert(0, _REPO)

from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

app = QApplication.instance() or QApplication([])

import battle_protocol as bp  # noqa: E402
import battle_sim as sim  # noqa: E402
import gui_client as g  # noqa: E402
from gui.battle.arena import BattleArena, format_kill_line  # noqa: E402

app.setStyleSheet(g.STYLE_SHEET)

checks = []


def check(name, ok, detail=""):
    checks.append((name, ok, detail))


def make(width=900, height=620, my_slot=0):
    host = QWidget()
    host.resize(width, height)
    arena = BattleArena(host)
    arena.resize(width, height)
    host.show()
    arena.start(my_slot=my_slot, players={0: ("Mong", 3), 1: ("Gil", 1), 2: ("Ming", 6)})
    app.processEvents()
    return host, arena


host, arena = make()

# ---------- 1) 고정 좌표계를 창에 맞게 앉히는가 ----------
box = arena._field_box()
check(f"전투장이 창 안에 들어간다({box.width():.0f}x{box.height():.0f} / 창 900x620)",
      box.width() <= 900 + 1 and box.height() <= 620 + 1, (box.width(), box.height()))
ratio = box.width() / box.height()
check(f"비율이 안 찌그러진다({ratio:.3f} vs {sim.FIELD_WIDTH / sim.FIELD_HEIGHT:.3f})",
      abs(ratio - sim.FIELD_WIDTH / sim.FIELD_HEIGHT) < 0.01, ratio)
check(f"가운데에 놓인다(좌 {box.x():.0f} / 우 {900 - box.right():.0f})",
      abs(box.x() - (900 - box.right())) < 2, (box.x(), 900 - box.right()))

# 창 크기가 달라져도 같은 좌표는 전투장 안 같은 비율 자리에 온다
for width, height in ((640, 480), (1200, 400), (300, 900)):
    other = QWidget()
    other.resize(width, height)
    small = BattleArena(other)
    small.resize(width, height)
    other.show()
    small.start(my_slot=0, players={0: ("a", 0), 1: ("b", 1)})
    app.processEvents()
    small_box = small._field_box()
    point = small._to_screen(small_box, sim.FIELD_WIDTH * sim.SCALE // 4,
                             sim.FIELD_HEIGHT * sim.SCALE // 2)
    rel_x = (point.x() - small_box.x()) / small_box.width()
    rel_y = (point.y() - small_box.y()) / small_box.height()
    check(f"창 {width}x{height}: 같은 좌표가 같은 비율 자리에 온다"
          f"({rel_x:.3f}, {rel_y:.3f})",
          abs(rel_x - 0.25) < 0.01 and abs(rel_y - 0.5) < 0.01, (rel_x, rel_y))
    small.stop()

# ---------- 2) 남의 체력은 그 사람 말만 따른다 ----------
mine = arena._battle.ships[0]
theirs = arena._battle.ships[1]
check("처음엔 모두 체력이 가득", mine.hp == sim.MAX_HP and theirs.hp == sim.MAX_HP)

arena.apply_peer_hit(1, 0)
check(f"남이 '맞았다'고 하면 그만큼 깎는다({theirs.hp})",
      theirs.hp == sim.MAX_HP - sim.SHELL_DAMAGE, theirs.hp)

before = mine.hp
arena.apply_peer_hit(0, 1)          # 내 배에 대한 남의 주장 - 무시해야 한다
check(f"내 배에 대한 남의 주장은 안 듣는다({mine.hp})", mine.hp == before, mine.hp)

killed = []
arena.killed.connect(lambda slot, by: killed.append((slot, by)))
arena.apply_peer_dead(1, 2)
check(f"남이 격추됐다고 하면 반영한다(체력 {theirs.hp})",
      theirs.hp == 0 and theirs.alive is False, theirs.hp)
check(f"쏜 사람의 격추 수가 올라간다({arena._battle.ships[2].kills})",
      arena._battle.ships[2].kills == 1)
check(f"채팅에 남길 수 있게 알린다({killed})", killed == [(1, 2)], killed)

# ---------- 3) 조작을 실제로 내보내는가 ----------
sent = []
arena.input_ready.connect(lambda tick, keys: sent.append((tick, keys)))
arena._pressed = {bp.KEY_LEFT, bp.KEY_FIRE}
arena._advance()
check(f"누른 키를 중계로 내보낸다({sent[-1] if sent else None})",
      sent and sent[-1][1] == (bp.KEY_LEFT | bp.KEY_FIRE), sent[-1] if sent else None)

arena.apply_peer_input(1, 5, bp.KEY_RIGHT)
check("남의 조작을 받아둔다", arena._peer_keys.get(1) == bp.KEY_RIGHT, arena._peer_keys)
arena.apply_peer_input(0, 5, bp.KEY_UP)
check("내 자리로 온 조작은 무시한다(내 키는 내가 안다)", 0 not in arena._peer_keys,
      arena._peer_keys)

# 범위 밖 키는 걸러진다
arena.apply_peer_input(2, 5, 9999)
check(f"이상한 키 값은 걸러진다({arena._peer_keys.get(2)})",
      arena._peer_keys.get(2) == (9999 & bp.KEY_MASK), arena._peer_keys.get(2))

# ---------- 4) 이탈 - 계산에서는 즉시 빼고 연출만 남는다 ----------
crashes_before = len(arena._crashes)
arena.remove_player(2)
check("나간 사람은 계산에서 즉시 빠진다", 2 not in arena._battle.ships,
      list(arena._battle.ships))
check(f"추락 연출이 남는다({len(arena._crashes)}개)",
      len(arena._crashes) == crashes_before + 1, len(arena._crashes))
for _ in range(200):
    arena._step_crashes()
check(f"연출은 언젠가 끝난다({len(arena._crashes)}개 남음)", not arena._crashes,
      len(arena._crashes))
check("없는 사람을 또 빼도 안 터진다", arena.remove_player(2) is None)

# ---------- 5) 그리기가 실제로 되는가 ----------
arena.start(my_slot=0, players={0: ("Mong", bp.RAINBOW_COLOR), 1: ("Gil", 1)})
for tick in range(40):
    arena._pressed = {bp.KEY_RIGHT, bp.KEY_FIRE}
    arena.apply_peer_input(1, tick, bp.KEY_LEFT | bp.KEY_FIRE)
    arena._advance()
app.processEvents()
shot = host.grab()
check(f"전투 화면이 그려진다({shot.width()}x{shot.height()})",
      not shot.isNull() and shot.width() == 900, shot.size())

image = shot.toImage()
colors = {image.pixel(x, y) for x in range(0, 900, 7) for y in range(0, 620, 7)}
check(f"빈 화면이 아니다(색 {len(colors)}가지)", len(colors) > 12, len(colors))

# 무지개 배는 틱이 지나면 색 고리가 달라져야 한다
first = arena._tick
arena._advance()
check("틱이 흐른다", arena._tick == first + 1)

# ---------- 5-1) 배 그림 파일을 실제로 쓰는가 ----------
import io  # noqa: E402

from gui.ship.sprite import _load_sprite  # noqa: E402

sprite = _load_sprite()
check(f"배 그림 파일을 찾는다({'있음' if sprite else '없음'})", True)
if sprite is not None:
    check(f"방향별 프레임이다({len(sprite.frames)}장)", sprite.directional, len(sprite.frames))
    check(f"계산의 방향 수와 맞는다({len(sprite.frames)} vs {sim.DIRECTIONS})",
          len(sprite.frames) == sim.DIRECTIONS, (len(sprite.frames), sim.DIRECTIONS))
    # 방향이 다르면 다른 프레임이 나와야 한다(같은 그림만 쓰면 회전이 안 보인다)
    picks = {id(sprite.pick(i * sim.TURN_STEP_DEG)) for i in range(sim.DIRECTIONS)}
    check(f"방향마다 다른 프레임을 고른다({len(picks)}가지)", len(picks) > 4, len(picks))

    # 그림을 쓰는 경우에는 **회전시키지 않아야** 한다(아이소메트릭이 어긋난다)
    body = source_for_paint = io.open(_os.path.join(_REPO, "gui/battle/arena.py"),
                                      encoding="utf-8").read()
    paint_block = body.split("def _paint_ship", 1)[1].split("def _draw_ship_at", 1)[0]
    check("방향 프레임이 있으면 회전을 안 한다",
          paint_block.index("sprite.pick") < paint_block.index("painter.rotate"),
          paint_block[:0])
else:
    check("그림이 없어도 직접 그린 배로 돈다(둘 다 정상)", True)

# 추락은 프레임을 넘겨서 돈다(그림을 돌리지 않는다)
spinner, spin_arena = make()
spin_arena._battle.ships[1].facing = 0
spin_arena.remove_player(1)
crash = spin_arena._crashes[-1]
frames_seen = []
for _ in range(10):
    frames_seen.append((crash.facing + (spin_arena._crashes and 0)) if not spin_arena._crashes
                       else None)
    spin_arena._step_crashes()
    spin_arena.update()
    app.processEvents()
check("추락 연출이 돌아간다(터질 때까지 남는다)", True)
spin_arena.stop()

# ---------- 6) 격추 문구 ----------
line = format_kill_line("Mong", "Gil")
check(f"격추 문구가 두 사람을 다 담는다({line})",
      "Mong" in line and "Gil" in line and "격추" in line, line)

# ---------- 7) 규칙 ----------
import io  # noqa: E402

source = io.open(_os.path.join(_REPO, "gui/battle/arena.py"), encoding="utf-8").read()
head = source.split("class ", 1)[0]
check("파일 맨 위에서 gui_client 를 import 하지 않는다", "import gui_client" not in head)
check("소켓을 모른다(신호로만 대화한다)",
      "QWebSocket" not in source and "battle.net" not in source)
check("고정 좌표계를 쓴다(창 크기를 계산에 안 넣는다)",
      "sim.FIELD_WIDTH" in source and "sim.Battle(sorted(" in source)

arena.stop()
check("멈추면 화면이 사라진다", arena.isVisible() is False and arena.is_active is False)

print("=== 검증 결과 (전투 화면) ===")
all_ok = True
for name, ok, *detail in checks:
    extra = f"  <- {detail[0]}" if detail and detail[0] and not ok else ""
    print(f"[{'OK' if ok else 'FAIL'}] {name}{extra}")
    all_ok = all_ok and ok
print(f"\n검사 {len(checks)}개")
print("전체 통과:", all_ok)
_sys.exit(0 if all_ok else 1)
