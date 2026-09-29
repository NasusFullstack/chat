"""스타크래프트1 방식 도트 체력바 - 배 아래에 붙는 납작한 막대.

사용자가 "스타1처럼 도트 체력바 그대로"를 콕 집어 요청했다. 그 체력바의 생김새를
그대로 옮기면 이렇게 된다.

    +----------------------------+   <- 검은 테두리(어떤 배경에서도 보이게)
    |####|####|####|##  |    |   |   <- 남은 만큼 왼쪽부터, 칸 사이는 어두운 세로선
    +----------------------------+

## 왜 이 파일이 따로 있는가
전투 화면은 배·포탄·격추 연출까지 같이 보므로, 체력바의 색 경계나 칸 나누기가 거기
섞이면 "칸이 삐져나갔다" 같은 것을 픽셀로 확인할 방법이 없어진다. 그래서 **판단은
순수 함수로 빼고 그리는 것만 QPainter에 맡긴다** - hp_level / segment_edges /
fill_width 는 QPainter도 위젯도 없이 그대로 불러 시험할 수 있다.

## 칸을 나눌 때 조심할 것
칸 수는 유닛 체력에 비례해 늘어나지만(스타1도 그렇다), 막대가 좁아지면 칸이 1px보다
가늘어져 세로선만 빽빽한 줄무늬가 된다. 그래서 effective_segments() 가 **칸 하나가
최소 2px는 되도록 칸 수를 줄인다.** 요청한 칸 수를 그대로 쓰면 좁은 폭에서 경계선이
서로 겹쳐 같은 자리에 두 번 그려지고, 체력이 얼마나 남았는지 도리어 안 보인다.

## 안티에일리어싱을 끄고 fillRect만 쓴다
펜으로 1px 선을 그으면 좌표가 반 칸 밀려 양옆으로 번진다. 도트 그림에서 그건 곧
"칸 경계가 흐릿해진다"는 뜻이고, 픽셀을 세서 검사할 수도 없게 된다. 그래서 테두리도
칸 경계도 전부 fillRect로 채운다.

## 들어오는 비율은 믿지 않는다
체력은 상대 조작으로부터 각자 계산해 얻는 값이다. 규약 쪽 규칙(battle_protocol.py
4번 - 범위 밖 값은 조용히 버린다)을 여기서도 지킨다: 비율이 음수든 1을 넘든 NaN이든
글자든 예외를 던지지 않고 0~1로 접는다. 체력바 하나 때문에 전투 화면이 멈추면 안 된다.
"""
from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QPainter

# ---- 판정 쪽(battle_sim.py)이 정한 칸 수를 쓸 수 있으면 쓴다 ------------------
# 체력 최대치는 판정이 정하는 값이라 여기서 또 정하면 두 곳이 어긋난다. 다만 그 파일이
# 아직 없거나(같이 만드는 중) 상수 이름이 다를 수 있으므로, 없으면 아래 기본값으로
# 떨어지고 부르는 쪽이 segments= 로 직접 넘길 수도 있게 둔다.
try:
    import battle_sim as _sim
except Exception:      # 아직 없음 / 만드는 중 / 문법 오류 - 체력바가 같이 죽을 이유는 없다
    _sim = None

FALLBACK_MAX_HP = 100


def _sim_int(names, fallback):
    for name in names:
        value = getattr(_sim, name, None) if _sim is not None else None
        # bool을 따로 막는다 - 파이썬에서 True는 정수 1로 통과해버린다(규약 쪽과 같은 이유)
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            return value
    return fallback


# ---- 생김새를 정하는 값 -------------------------------------------------------
BORDER_PX = 1          # 테두리 두께. 스타1 체력바도 딱 한 칸이다
DIVIDER_PX = 1         # 칸 사이 세로선
BAR_HEIGHT = 5         # 테두리까지 합친 높이(속은 3px) - 납작해야 배를 가리지 않는다
MIN_SEGMENT_PX = 2     # 칸 하나의 최소 폭. 이보다 좁아지면 칸 수를 줄인다
BAR_WIDTH_RATIO = 0.62  # 배 폭에 대한 막대 폭 - 스타1도 유닛보다 좁다
BAR_GAP_PX = 3         # 배 아래끝과 막대 사이 틈
MIN_BAR_WIDTH = 8

HP_PER_SEGMENT = 12    # 체력 이만큼마다 칸 하나(칸 수가 체력에 비례하는 이유)
MIN_SEGMENTS, MAX_SEGMENTS = 3, 12  # 너무 적으면 눈금이 뜻이 없고, 너무 많으면 세로선뿐이다

# 색. 스타1은 초록 -> 노랑 -> 빨강 세 단계뿐이고 중간색으로 섞지 않는다
# (섞으면 "지금 위험한가"가 한눈에 안 들어온다)
LEVEL_GREEN, LEVEL_YELLOW, LEVEL_RED = "green", "yellow", "red"
GREEN_ABOVE = 2.0 / 3.0   # 이 위는 초록
YELLOW_ABOVE = 1.0 / 3.0  # 이 위는 노랑, 아래는 빨강

_LEVEL_COLORS = {
    LEVEL_GREEN: QColor(30, 200, 30),
    LEVEL_YELLOW: QColor(230, 208, 0),
    LEVEL_RED: QColor(208, 32, 32),
}
BORDER_COLOR = QColor(0, 0, 0)       # 밝은 배경에서도 막대가 떠 보이게
EMPTY_COLOR = QColor(48, 48, 48)     # 깎인 부분(빈 칸)
DIVIDER_COLOR = QColor(20, 20, 20)   # 칸 경계. 테두리와 아주 가깝지만 같은 값은 아니다


def segments_for_hp(max_hp) -> int:
    """체력 최대치로 칸 수를 정한다 - 튼튼한 배일수록 눈금이 촘촘해진다."""
    try:
        hp = float(max_hp)
    except (TypeError, ValueError):
        return MIN_SEGMENTS
    if hp != hp or hp <= 0:   # NaN 또는 말이 안 되는 값
        return MIN_SEGMENTS
    return max(MIN_SEGMENTS, min(MAX_SEGMENTS, int(round(hp / HP_PER_SEGMENT))))


MAX_HP = _sim_int(("MAX_HP", "SHIP_HP", "START_HP", "HP"), FALLBACK_MAX_HP)
DEFAULT_SEGMENTS = _sim_int(("HP_SEGMENTS", "HP_BAR_SEGMENTS"), segments_for_hp(MAX_HP))


# ---- 여기부터 순수 함수 - QPainter도 위젯도 없이 시험할 수 있다 ---------------
def clamp_ratio(ratio) -> float:
    """어떤 값이 와도 0~1 사이 실수 하나로 만든다(예외를 던지지 않는다)."""
    try:
        value = float(ratio)
    except (TypeError, ValueError):
        return 0.0
    if value != value:   # NaN은 비교가 전부 거짓이라 따로 걸러야 한다
        return 0.0
    if value < 0.0:
        return 0.0
    return 1.0 if value > 1.0 else value


def hp_level(ratio) -> str:
    """체력 비율 -> 색 단계. 경계값은 나쁜 쪽 단계로 넣는다.

    2/3에 딱 걸린 순간을 초록으로 두면 "아직 멀쩡하다"로 읽히는데, 스타1에서 그 지점은
    이미 노랑이다. 경계에 걸린 값은 나쁜 쪽으로 보는 게 맞다.
    """
    value = clamp_ratio(ratio)
    if value > GREEN_ABOVE:
        return LEVEL_GREEN
    if value > YELLOW_ABOVE:
        return LEVEL_YELLOW
    return LEVEL_RED


def hp_color(ratio) -> QColor:
    """단계에 맞는 색. QColor는 고칠 수 있는 물건이라 표에 있는 것을 복사해 준다."""
    return QColor(_LEVEL_COLORS[hp_level(ratio)])


def inner_width(width) -> int:
    """테두리를 뺀 속 폭."""
    try:
        value = int(width)
    except (TypeError, ValueError):
        return 0
    return max(0, value - 2 * BORDER_PX)


def wanted_segments(segments) -> int:
    """부르는 쪽이 말한 칸 수를 정수 하나로 정리한다(폭은 아직 안 본다)."""
    try:
        wanted = int(segments)
    except (TypeError, ValueError):
        wanted = MIN_SEGMENTS
    return max(1, wanted)


def effective_segments(width, segments) -> int:
    """이 폭에서 실제로 나눌 칸 수.

    요청한 칸 수를 그대로 쓰면 좁은 막대에서 칸이 1px 미만이 되어 경계선이 겹친다.
    칸 하나가 최소 MIN_SEGMENT_PX는 되도록 줄여서 겹치는 일이 아예 없게 만든다.
    """
    wanted = wanted_segments(segments)
    inner = inner_width(width)
    if inner <= 0:
        return 1
    return max(1, min(wanted, inner // MIN_SEGMENT_PX))


def segment_edges(width, segments) -> list:
    """칸 경계선의 x 위치들(막대 **속** 왼쪽을 0으로 본 값).

    막대 안쪽에만 들어가고(0도 끝도 아니다), 반드시 왼쪽에서 오른쪽으로 늘어나며
    같은 자리가 두 번 나오지 않는다 - 그래야 세로선이 겹쳐 굵어지지 않는다.
    """
    inner = inner_width(width)
    count = effective_segments(width, segments)
    edges = []
    for index in range(1, count):
        x = int(round(inner * index / count))
        if 1 <= x <= inner - DIVIDER_PX and (not edges or x > edges[-1]):
            edges.append(x)
    return edges


def fill_width(inner, ratio) -> int:
    """남은 체력만큼의 폭. 조금이라도 살아 있으면 최소 1px은 남긴다.

    그냥 반내림하면 체력이 1 남은 배의 막대가 통째로 비어 보여서 이미 죽은 것처럼
    읽힌다. 스타1도 마지막 한 칸은 가느다랗게라도 남는다.
    """
    try:
        span = int(inner)
    except (TypeError, ValueError):
        return 0
    span = max(0, span)
    value = clamp_ratio(ratio)
    if span == 0 or value <= 0.0:
        return 0
    return max(1, min(span, int(round(span * value))))


def bar_geometry(ship_width, hull_bottom, segments=None):
    """배 그림 왼쪽 위를 (0,0)으로 봤을 때 막대가 놓일 자리 (x, y, w, h).

    hull_bottom 은 위젯 높이가 아니라 **실제로 그려진 배의 아래끝**이다. 배틀크루저
    오버레이는 회전해도 안 잘리게 위젯을 넉넉히 잡아서(96px 위젯에 0.86배로 그린다)
    위젯 아래끝을 기준으로 잡으면 막대가 배에서 한참 떨어진다. 어디가 아래끝인지는
    그리는 쪽만 아니까 인자로 받는다.
    """
    try:
        width = max(0, int(ship_width))
        bottom = int(hull_bottom)
    except (TypeError, ValueError):
        return (0, 0, MIN_BAR_WIDTH, BAR_HEIGHT)
    bar_w = max(MIN_BAR_WIDTH, int(round(width * BAR_WIDTH_RATIO)))
    if segments is not None:
        # 칸이 뭉개지지 않는 최소 폭은 확보해 둔다(칸 수를 몰래 줄이지 않게).
        # 여기서 effective_segments()를 쓰면 안 된다 - 그건 이미 좁아진 폭에 맞춰 줄인
        # 값이라, 좁으면 줄이고 줄었으니 안 넓히는 순환이 된다(실제로 그렇게 새서 12px에
        # 5칸으로 눌러앉았다). 넓힐 기준은 **요청받은 칸 수**다
        bar_w = max(bar_w, wanted_segments(segments) * MIN_SEGMENT_PX + 2 * BORDER_PX)
    return ((width - bar_w) // 2, bottom + BAR_GAP_PX, bar_w, BAR_HEIGHT)


# ---- 그리기 ------------------------------------------------------------------
def draw_hp_bar(painter, rect, ratio, segments=None):
    """rect(테두리 포함) 안에 체력바를 그린다. rect 밖으로는 한 픽셀도 나가지 않는다.

    칸 경계는 찬 부분과 빈 부분 **양쪽 모두**에 그린다 - 스타1도 깎인 칸의 눈금이
    남아 있어서 "몇 칸 중 몇 칸인지"가 보인다. 빈 곳 눈금을 지우면 전체가 얼마였는지
    알 수 없게 된다.
    """
    if painter is None or rect is None:
        return
    x, y = int(rect.x()), int(rect.y())
    width, height = int(rect.width()), int(rect.height())
    if width <= 0 or height <= 0:
        return

    count = DEFAULT_SEGMENTS if segments is None else segments
    painter.save()
    # 도트 그림이라 번지면 안 된다(맨 위 설명) - 펜도 쓰지 않는다
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
    painter.setPen(Qt.PenStyle.NoPen)

    painter.fillRect(QRect(x, y, width, height), BORDER_COLOR)
    inner_w = inner_width(width)
    inner_h = height - 2 * BORDER_PX
    if inner_w > 0 and inner_h > 0:
        ix, iy = x + BORDER_PX, y + BORDER_PX
        painter.fillRect(QRect(ix, iy, inner_w, inner_h), EMPTY_COLOR)
        filled = fill_width(inner_w, ratio)
        if filled > 0:
            painter.fillRect(QRect(ix, iy, filled, inner_h), hp_color(ratio))
        for edge in segment_edges(width, count):
            painter.fillRect(QRect(ix + edge, iy, DIVIDER_PX, inner_h), DIVIDER_COLOR)
    painter.restore()
