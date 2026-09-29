"""스타1 도트 체력바 - 색이 정말 바뀌는가, 그린 결과가 정말 그렇게 생겼는가.

체력바는 '보이는 것'이 전부인 부품이라 함수가 맞는 값을 돌려주는 것만으로는 부족하다.
실제로 QPixmap에 그린 뒤 **픽셀을 세서** 확인한다(CLAUDE.md 7번 - 눈으로 보고 판단하지
말고 재라). 여기서 잡아야 할 것:

- 100%/70%/50%/30%/10%/0% 에서 그려진 색이 실제로 초록 -> 노랑 -> 빨강으로 바뀌는가
  (함수가 답하는 색이 아니라 **픽셀에 찍힌 색**을 본다)
- 왼쪽이 차고 오른쪽이 비는가(반대로 차면 통과하면 안 된다)
- 칸 경계선이 진짜 찍혔는가, 그 자리가 막대 안쪽인가, 겹쳐서 굵어지지 않는가
- 테두리가 있고, 막대 **밖으로는 한 픽셀도** 안 나가는가
- 이상한 비율(음수, 1 초과, NaN, 글자, None)과 아주 좁은 폭에서 안 터지는가

앞쪽 순수 함수 검사는 **QGuiApplication을 만들기 전에** 돌린다 - 색과 칸 경계 판단이
정말 QPainter 없이 되는지가 이 부품의 전제이기 때문이다.
"""
import os as _os
import sys as _sys

_os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_HERE = _os.path.dirname(_os.path.abspath(__file__))
_REPO = _os.path.dirname(_HERE)
_sys.path.insert(0, _REPO)

import math  # noqa: E402

from gui.battle import hp_bar as hb  # noqa: E402

checks = []


def check(name, ok, detail=""):
    checks.append((name, ok, detail))


# ---------- 1) 색 단계 - 그림 없이 판단되는가 (앱도 painter도 아직 없다) ----------
LEVELS = [(1.0, hb.LEVEL_GREEN), (0.7, hb.LEVEL_GREEN), (0.5, hb.LEVEL_YELLOW),
          (0.3, hb.LEVEL_RED), (0.1, hb.LEVEL_RED), (0.0, hb.LEVEL_RED)]
for ratio, want in LEVELS:
    got = hb.hp_level(ratio)
    check(f"체력 {int(ratio * 100)}% -> {want}", got == want, got)

check("세 단계 색이 서로 다르다",
      len({hb.hp_color(r).rgb() for r in (1.0, 0.5, 0.1)}) == 3,
      [hb.hp_color(r).name() for r in (1.0, 0.5, 0.1)])

# 경계값 - 딱 걸린 값은 나쁜 쪽으로 가야 한다(2/3은 이미 노랑, 1/3은 이미 빨강)
EPS = 1e-9
for value, want, why in (
    (hb.GREEN_ABOVE, hb.LEVEL_YELLOW, "2/3에 딱 걸리면 노랑"),
    (hb.GREEN_ABOVE + EPS, hb.LEVEL_GREEN, "2/3을 넘으면 초록"),
    (hb.GREEN_ABOVE - EPS, hb.LEVEL_YELLOW, "2/3 밑은 노랑"),
    (hb.YELLOW_ABOVE, hb.LEVEL_RED, "1/3에 딱 걸리면 빨강"),
    (hb.YELLOW_ABOVE + EPS, hb.LEVEL_YELLOW, "1/3을 넘으면 노랑"),
):
    got = hb.hp_level(value)
    check(f"{why} ({value:.9f} -> {got})", got == want, got)

# 체력이 줄어드는 동안 색이 되돌아가지 않는다(초록 -> 노랑 -> 빨강 한 방향)
ORDER = {hb.LEVEL_GREEN: 2, hb.LEVEL_YELLOW: 1, hb.LEVEL_RED: 0}
ladder = [ORDER[hb.hp_level(i / 200)] for i in range(200, -1, -1)]
check("체력이 줄면 색이 되돌아가지 않는다",
      all(b <= a for a, b in zip(ladder, ladder[1:])), ladder[:8])

# ---------- 2) 이상한 비율이 와도 안 터진다 ----------
WEIRD = [-5, -0.001, 1.001, 2.0, 99, None, "50%", "", float("nan"),
         float("inf"), float("-inf"), True, [], object()]
for bad in WEIRD:
    try:
        got = hb.clamp_ratio(bad)
        ok = isinstance(got, float) and 0.0 <= got <= 1.0
    except Exception as exc:                      # noqa: BLE001 - 터지면 그게 실패다
        got, ok = f"{type(exc).__name__}: {exc}", False
    check(f"이상한 비율 {bad!r} -> {got!r}", ok, got)

check("음수는 0으로", hb.clamp_ratio(-3) == 0.0)
check("1 초과는 1로", hb.clamp_ratio(7) == 1.0)
check("NaN은 0으로(비교가 전부 거짓이라 따로 걸러야 한다)",
      hb.clamp_ratio(float("nan")) == 0.0)

# ---------- 3) 칸 수와 칸 경계 ----------
check(f"기본 칸 수가 말이 된다({hb.DEFAULT_SEGMENTS}칸, 체력 {hb.MAX_HP})",
      hb.MIN_SEGMENTS <= hb.DEFAULT_SEGMENTS <= hb.MAX_SEGMENTS, hb.DEFAULT_SEGMENTS)

check("넉넉한 폭에서는 요청한 칸 수가 그대로 나온다",
      hb.effective_segments(40, 8) == 8 and len(hb.segment_edges(40, 8)) == 7,
      (hb.effective_segments(40, 8), hb.segment_edges(40, 8)))

# 폭 x 칸수를 전부 훑어서 경계선이 막대 밖으로 나가거나 겹치는 조합이 하나라도 있는지 본다
bad_bounds, bad_order, bad_count = [], [], []
for width in range(-3, 121):
    inner = hb.inner_width(width)
    for segments in range(1, hb.MAX_SEGMENTS + 1):
        edges = hb.segment_edges(width, segments)
        if any(not (1 <= e <= inner - hb.DIVIDER_PX) for e in edges):
            bad_bounds.append((width, segments, edges))
        if any(b <= a for a, b in zip(edges, edges[1:])):
            bad_order.append((width, segments, edges))
        if len(edges) != hb.effective_segments(width, segments) - 1:
            bad_count.append((width, segments, edges))
check(f"모든 폭에서 칸 경계가 막대 안에 있다(폭 -3~120)", not bad_bounds, bad_bounds[:3])
check("칸 경계가 겹치거나 뒤집히지 않는다", not bad_order, bad_order[:3])
check("칸 수와 경계선 수가 맞는다(칸 수 - 1)", not bad_count, bad_count[:3])

check(f"좁은 막대(10px)에서는 칸 수를 줄인다({hb.effective_segments(10, 8)}칸)",
      hb.effective_segments(10, 8) < 8 and hb.effective_segments(10, 8) >= 1,
      hb.effective_segments(10, 8))
narrow_edges = hb.segment_edges(10, 8)
check(f"좁은 막대에서도 칸이 붙어버리지 않는다({narrow_edges})",
      all(b - a >= hb.MIN_SEGMENT_PX for a, b in zip(narrow_edges, narrow_edges[1:])),
      narrow_edges)

check("체력이 많을수록 칸이 촘촘해진다",
      all(hb.segments_for_hp(a) <= hb.segments_for_hp(b)
          for a, b in zip(range(1, 400), range(2, 401))))
check(f"칸 수는 상한/하한 안에 있다(체력 1 -> {hb.segments_for_hp(1)}, "
      f"9999 -> {hb.segments_for_hp(9999)})",
      hb.segments_for_hp(1) == hb.MIN_SEGMENTS
      and hb.segments_for_hp(9999) == hb.MAX_SEGMENTS)
check("체력 값이 이상해도 칸 수는 나온다",
      all(hb.segments_for_hp(v) == hb.MIN_SEGMENTS
          for v in (None, "많이", 0, -5, float("nan"))))

# ---------- 4) 남은 만큼의 폭 ----------
check("체력이 0이면 한 칸도 안 찬다", hb.fill_width(38, 0) == 0)
check("체력이 꽉 차면 속을 다 채운다", hb.fill_width(38, 1) == 38)
check(f"절반이면 절반({hb.fill_width(38, 0.5)}/38)", hb.fill_width(38, 0.5) == 19)
check("조금이라도 남으면 1px은 남긴다(다 죽은 것처럼 보이지 않게)",
      hb.fill_width(38, 0.001) == 1, hb.fill_width(38, 0.001))
check("폭을 넘겨 채우지 않는다", hb.fill_width(38, 5) == 38)
check("폭이 0이면 0", hb.fill_width(0, 1) == 0 and hb.fill_width(-9, 1) == 0)

# ---------- 5) 놓일 자리 ----------
geo_x, geo_y, geo_w, geo_h = hb.bar_geometry(96, 60, hb.DEFAULT_SEGMENTS)
check(f"막대는 배 아래에 붙는다(y={geo_y}, 배 아래끝 60)", geo_y > 60, geo_y)
check(f"막대는 배 폭 가운데에 온다(x={geo_x}, w={geo_w}, 배 96)",
      geo_x > 0 and geo_x + geo_w <= 96 and abs(geo_x - (96 - geo_w) / 2) <= 1,
      (geo_x, geo_w))
check(f"막대는 납작하다(h={geo_h})", geo_h == hb.BAR_HEIGHT and geo_h <= 8, geo_h)
check("자리 계산에 이상한 값이 와도 안 터진다",
      hb.bar_geometry(None, None)[2] >= hb.MIN_BAR_WIDTH
      and hb.bar_geometry(0, 0)[2] >= hb.MIN_BAR_WIDTH)
check("칸 수를 넘기면 칸이 뭉개지지 않을 폭은 확보한다",
      hb.effective_segments(hb.bar_geometry(20, 10, 8)[2], 8) == 8,
      hb.bar_geometry(20, 10, 8))

# ---------- 여기부터 실제로 그려서 픽셀을 센다 ----------
from PySide6.QtCore import QRect, QRectF  # noqa: E402
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPixmap  # noqa: E402

_app = QGuiApplication.instance() or QGuiApplication([])

SENTINEL = QColor(255, 0, 255)   # 이 색이 남아 있으면 "거긴 안 그렸다"는 뜻
NAMES = {
    SENTINEL.rgb(): "sentinel",
    hb.BORDER_COLOR.rgb(): "border",
    hb.EMPTY_COLOR.rgb(): "empty",
    hb.DIVIDER_COLOR.rgb(): "divider",
    hb.hp_color(1.0).rgb(): hb.LEVEL_GREEN,
    hb.hp_color(0.5).rgb(): hb.LEVEL_YELLOW,
    hb.hp_color(0.1).rgb(): hb.LEVEL_RED,
}
FILL_NAMES = (hb.LEVEL_GREEN, hb.LEVEL_YELLOW, hb.LEVEL_RED)


def render(ratio, segments, rect, canvas):
    """빈 종이를 눈에 띄는 색으로 칠해두고 그 위에 체력바만 그린다."""
    pixmap = QPixmap(*canvas)
    pixmap.fill(SENTINEL)
    painter = QPainter(pixmap)
    hb.draw_hp_bar(painter, rect, ratio, segments)
    painter.end()
    return pixmap.toImage()


def name_at(image, x, y):
    return NAMES.get(image.pixelColor(x, y).rgb(), f"?{image.pixelColor(x, y).name()}")


def scan(image, y, x0, x1):
    return [name_at(image, x, y) for x in range(x0, x1)]


BAR = QRect(10, 7, 40, 5)
CANVAS = (60, 20)
INNER_X0 = BAR.x() + hb.BORDER_PX
INNER_X1 = BAR.x() + BAR.width() - hb.BORDER_PX
MID_Y = BAR.y() + BAR.height() // 2

# ---------- 6) 왼쪽이 차고 오른쪽이 빈다 ----------
for ratio in (0.85, 0.5, 0.3):
    image = render(ratio, 8, BAR, CANVAS)
    row = scan(image, MID_Y, INNER_X0, INNER_X1)
    inner_w = hb.inner_width(BAR.width())
    want_fill = hb.fill_width(inner_w, ratio)
    fill_idx = [i for i, n in enumerate(row) if n in FILL_NAMES]
    empty_idx = [i for i, n in enumerate(row) if n == "empty"]
    check(f"비율 {ratio}: 막대 속에 모르는 색이 없다(번짐 없음)",
          not [n for n in row if n.startswith("?")], [n for n in row if n.startswith("?")][:4])
    check(f"비율 {ratio}: 찬 부분이 전부 왼쪽에 있다(0~{want_fill - 1})",
          bool(fill_idx) and max(fill_idx) < want_fill, (fill_idx[:3], fill_idx[-3:]))
    check(f"비율 {ratio}: 빈 부분이 전부 오른쪽에 있다({want_fill}~)",
          bool(empty_idx) and min(empty_idx) >= want_fill, (empty_idx[:3], want_fill))
    check(f"비율 {ratio}: 찬 부분과 빈 부분이 안 섞인다",
          max(fill_idx) < min(empty_idx), (max(fill_idx), min(empty_idx)))

# ---------- 7) 찍힌 색이 비율마다 바뀐다(픽셀에서 읽는다) ----------
painted = {}
for ratio in (1.0, 0.7, 0.5, 0.3, 0.1):
    row = scan(render(ratio, 8, BAR, CANVAS), MID_Y, INNER_X0, INNER_X1)
    found = {n for n in row if n in FILL_NAMES}
    painted[ratio] = found
    want = hb.hp_level(ratio)
    check(f"비율 {ratio}: 찍힌 색이 {want} 하나뿐이다({sorted(found)})",
          found == {want}, sorted(found))
check(f"비율에 따라 찍히는 색이 실제로 세 가지다({[sorted(v) for v in painted.values()]})",
      len({tuple(sorted(v)) for v in painted.values()}) == 3,
      [sorted(v) for v in painted.values()])

dead_row = scan(render(0.0, 8, BAR, CANVAS), MID_Y, INNER_X0, INNER_X1)
check(f"체력 0이면 찬 부분이 하나도 없다({sorted(set(dead_row))})",
      not [n for n in dead_row if n in FILL_NAMES], sorted(set(dead_row)))
full_row = scan(render(1.0, 8, BAR, CANVAS), MID_Y, INNER_X0, INNER_X1)
check("체력 100%면 빈 부분이 하나도 없다",
      "empty" not in full_row, sorted(set(full_row)))

# ---------- 8) 칸 경계선이 실제로 찍혔는가 ----------
image = render(0.3, 8, BAR, CANVAS)
row = scan(image, MID_Y, INNER_X0, INNER_X1)
drawn = [i for i, n in enumerate(row) if n == "divider"]
want_edges = hb.segment_edges(BAR.width(), 8)
check(f"칸 경계선이 계산한 자리에 그대로 찍혔다({drawn})", drawn == want_edges,
      (drawn, want_edges))
check(f"경계선이 7개 찍혔다(8칸)", len(drawn) == 7, len(drawn))
check("경계선이 서로 붙어 굵어지지 않았다",
      all(b - a >= hb.MIN_SEGMENT_PX for a, b in zip(drawn, drawn[1:])), drawn)
check("빈 부분에도 눈금이 남아 있다(몇 칸 중 몇 칸인지 보이게)",
      any(i >= hb.fill_width(hb.inner_width(BAR.width()), 0.3) for i in drawn), drawn)
check("찬 부분에도 눈금이 있다",
      any(i < hb.fill_width(hb.inner_width(BAR.width()), 0.3) for i in drawn), drawn)

# 경계선은 세로로 속을 관통한다(한 줄만 찍히고 마는 게 아니다)
column = drawn[0] + INNER_X0
through = [name_at(image, column, y)
           for y in range(BAR.y() + hb.BORDER_PX, BAR.y() + BAR.height() - hb.BORDER_PX)]
check(f"경계선은 막대 속 높이를 관통한다({through})",
      through == ["divider"] * len(through), through)

# ---------- 9) 테두리가 있고, 밖으로 안 나간다 ----------
top = scan(image, BAR.y(), BAR.x(), BAR.x() + BAR.width())
bottom = scan(image, BAR.y() + BAR.height() - 1, BAR.x(), BAR.x() + BAR.width())
check(f"위쪽 테두리가 한 줄 통째로 있다({len(top)}px)",
      top == ["border"] * len(top), sorted(set(top)))
check("아래쪽 테두리가 한 줄 통째로 있다",
      bottom == ["border"] * len(bottom), sorted(set(bottom)))
check("좌우 테두리도 있다",
      name_at(image, BAR.x(), MID_Y) == "border"
      and name_at(image, BAR.x() + BAR.width() - 1, MID_Y) == "border",
      (name_at(image, BAR.x(), MID_Y), name_at(image, BAR.x() + BAR.width() - 1, MID_Y)))

OUTSIDE = [(BAR.x() - 1, MID_Y), (BAR.x() + BAR.width(), MID_Y),
           (BAR.x(), BAR.y() - 1), (BAR.x(), BAR.y() + BAR.height()),
           (0, 0), (CANVAS[0] - 1, CANVAS[1] - 1)]
outside_names = [name_at(image, x, y) for x, y in OUTSIDE]
check(f"막대 밖은 한 픽셀도 안 건드린다({sorted(set(outside_names))})",
      outside_names == ["sentinel"] * len(outside_names), outside_names)

# ---------- 10) 아주 좁은 폭 ----------
NARROW = QRect(2, 2, 10, 5)
image = render(0.75, 8, NARROW, (16, 12))
n_x0 = NARROW.x() + hb.BORDER_PX
n_x1 = NARROW.x() + NARROW.width() - hb.BORDER_PX
n_row = scan(image, NARROW.y() + NARROW.height() // 2, n_x0, n_x1)
n_drawn = [i for i, n in enumerate(n_row) if n == "divider"]
check(f"10px 막대도 그려진다({n_row})",
      not [n for n in n_row if n.startswith("?")], n_row)
check(f"10px 막대의 경계선이 계산과 같다({n_drawn} vs {hb.segment_edges(10, 8)})",
      n_drawn == hb.segment_edges(10, 8), (n_drawn, hb.segment_edges(10, 8)))
check("10px 막대에서 경계선이 붙지 않았다",
      all(b - a >= hb.MIN_SEGMENT_PX for a, b in zip(n_drawn, n_drawn[1:])), n_drawn)
check("10px 막대에도 찬 부분과 테두리가 있다",
      any(n in FILL_NAMES for n in n_row)
      and name_at(image, NARROW.x(), NARROW.y()) == "border", n_row)

# ---------- 11) 터지지 않는가(폭/높이/비율 전부 이상한 값) ----------
crashed = []
for width in (-5, 0, 1, 2, 3, 4, 5, 7, 10):
    for height in (0, 1, 2, 3, 5):
        for ratio in (0, 0.5, 1, -1, 2, float("nan"), None, "x"):
            for segments in (None, 0, 1, 8, 99, -3, "여덟"):
                try:
                    render(ratio, segments, QRect(1, 1, width, height), (20, 12))
                except Exception as exc:          # noqa: BLE001
                    crashed.append((width, height, ratio, segments,
                                    f"{type(exc).__name__}: {exc}"))
check(f"폭·높이·비율·칸수를 막 넣어도 안 터진다({9 * 5 * 8 * 7}가지)",
      not crashed, crashed[:3])

try:
    render(0.5, 8, QRectF(10.4, 7.6, 40.2, 5.9), CANVAS)
    float_rect_ok = True
except Exception as exc:                          # noqa: BLE001
    float_rect_ok, crashed = False, f"{type(exc).__name__}: {exc}"
check("실수 좌표 사각형(QRectF)도 받는다", float_rect_ok)

pixmap = QPixmap(20, 12)
pixmap.fill(SENTINEL)
painter = QPainter(pixmap)
hb.draw_hp_bar(painter, None, 0.5, 8)
hb.draw_hp_bar(None, QRect(0, 0, 10, 5), 0.5, 8)
painter.end()
check("사각형이나 painter가 없으면 아무 것도 안 그린다",
      name_at(pixmap.toImage(), 5, 5) == "sentinel")

# 속이 없는 높이(2px)에서는 테두리만 남는다 - 이때도 터지지 않아야 한다
thin = render(0.5, 8, QRect(2, 2, 10, 2), (16, 8))
check("높이 2px면 테두리만 그린다",
      name_at(thin, 2, 2) == "border" and name_at(thin, 6, 3) == "border",
      (name_at(thin, 2, 2), name_at(thin, 6, 3)))

print("=== 검증 결과 (스타1 도트 체력바) ===")
all_ok = True
for name, ok, *detail in checks:
    extra = f"  <- {detail[0]}" if detail and detail[0] and not ok else ""
    print(f"[{'OK' if ok else 'FAIL'}] {name}{extra}")
    all_ok = all_ok and ok
print(f"\n검사 {len(checks)}개")
print("전체 통과:", all_ok)
_sys.exit(0 if all_ok else 1)
