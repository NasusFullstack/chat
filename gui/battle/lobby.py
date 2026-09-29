"""대기방 - '배틀크루저 전투'를 치면 뜨는 창.

방을 연 사람과 들어온 사람이 **서로 다른 것을 할 수 있다**:

|            | 정원 | 색 | 시작 |
|------------|------|----|------|
| 방 연 사람 | 고름 | 고름 | 누름(2명 이상일 때) |
| 들어온 사람 | 보기만 | 고름 | 기다림 |

이 창은 **소켓을 모른다.** 무엇을 눌렀는지 신호로만 올리고, 그래서 무엇을 할지는
창(MainWindow)이 정한다. 그래야 서버 사정이 바뀌어도 이 파일은 안 건드린다
(gui/components/ 규칙과 같다).
"""
from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QHBoxLayout, QLabel,
                               QListWidget, QListWidgetItem, QPushButton, QVBoxLayout,
                               QWidget)

import battle_protocol as bp
from gui.helpers import _find_image_in_app_dirs
from gui.themed_dialogs import ThemedDialog, _MiniTitleBar

# 대기방 맨 위에 거는 시작 그림. 없으면(파일이 안 딸려온 빌드 등) 그냥 안 건다 -
# 그림 하나 때문에 전투를 못 하면 안 된다
TITLE_IMAGE = "battle_title.jpg"
TITLE_MAX_WIDTH = 460

# 배 색 - battle_protocol.COLOR_COUNT 개여야 한다(서버가 번호로만 주고받으므로
# 실제 색은 화면이 정한다). 스타1 플레이어 색을 본떠 서로 확실히 구분되게 골랐다.
# 마지막 '무지개'는 **숨겨진 색**이다 - 아래 KONAMI 설명 참고
SHIP_COLORS = (
    ("빨강", "#e53935"),
    ("파랑", "#1e88e5"),
    ("청록", "#00acc1"),
    ("보라", "#8e24aa"),
    ("주황", "#fb8c00"),
    ("갈색", "#8d6e63"),
    ("연두", "#7cb342"),
    ("노랑", "#fdd835"),
    ("분홍", "#ec407a"),
    ("하늘", "#4fc3f7"),
    ("남색", "#3949ab"),
    ("자주", "#6a1b9a"),
    ("초록", "#2e7d32"),
    ("올리브", "#9e9d24"),
    ("주홍", "#d84315"),
    ("연보라", "#b39ddb"),
    ("민트", "#26a69a"),
    ("살구", "#ffab91"),
    ("회색", "#90a4ae"),
    ("검정", "#455a64"),
    ("무지개", "#ff0066"),      # 견본용 대표색. 실제로는 계속 바뀐다
)
assert len(SHIP_COLORS) == bp.COLOR_COUNT, "색 개수가 규약과 다르면 서버와 말이 안 통한다"

RAINBOW = bp.RAINBOW_COLOR

# 색 고르는 화면에서 이 순서대로 방향키를 누르면 무지개가 열린다.
# 위 아래 위 위 아래 좌 우 위 아래
KONAMI = (Qt.Key.Key_Up, Qt.Key.Key_Down, Qt.Key.Key_Up, Qt.Key.Key_Up,
          Qt.Key.Key_Down, Qt.Key.Key_Left, Qt.Key.Key_Right,
          Qt.Key.Key_Up, Qt.Key.Key_Down)

# 무지개가 한 바퀴 도는 데 걸리는 틱 수(전투는 30fps라 약 2초).
# 너무 빠르면 눈이 아프고 너무 느리면 안 바뀌는 것처럼 보인다
RAINBOW_PERIOD_TICKS = 60

SWATCH_PX = 14


def color_name(index: int) -> str:
    return SHIP_COLORS[index % len(SHIP_COLORS)][0]


def color_hex(index: int) -> str:
    return SHIP_COLORS[index % len(SHIP_COLORS)][1]


def ship_color(index: int, phase: int = 0) -> QColor:
    """배를 그릴 색. 무지개면 `phase`(틱 번호)에 따라 계속 바뀐다.

    **벽시계가 아니라 틱 번호로 정한다.** 그래야 모두의 화면에서 같은 순간에 같은 색이
    된다(시계는 PC마다 조금씩 어긋난다).

    비싸지 않다: 배는 어차피 매 틱 다시 그려지고, 여기서 하는 일은 색 하나를 만드는
    것뿐이다(그림을 새로 만들지 않는다).
    """
    if index != RAINBOW:
        return QColor(color_hex(index))
    hue = int(phase * 360 / RAINBOW_PERIOD_TICKS) % 360
    return QColor.fromHsv(hue, 235, 255)


def _swatch(index: int) -> QPixmap:
    """색 견본 네모. 글자만으로는 어떤 색인지 잘 안 와닿는다."""
    pixmap = QPixmap(SWATCH_PX, SWATCH_PX)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setBrush(QColor(color_hex(index)))
    painter.setPen(QColor("#20222c"))
    painter.drawRoundedRect(0, 0, SWATCH_PX - 1, SWATCH_PX - 1, 3, 3)
    painter.end()
    return pixmap


class BattleLobby(ThemedDialog):
    """대기방 창. 바깥과는 신호로만 대화한다."""

    color_chosen = Signal(int)      # 색을 바꿨다
    capacity_chosen = Signal(int)   # 정원을 바꿨다(방 연 사람만)
    start_pressed = Signal()        # 시작을 눌렀다
    closed = Signal()               # 창을 닫았다(= 전투를 그만둠)
    rainbow_unlocked = Signal()     # 숨겨진 색을 열었다
    bots_chosen = Signal(int)        # 연습 상대를 몇 대 넣을지

    def __init__(self, is_host: bool, my_nick: str, parent=None):
        # ThemedDialog 는 글/버튼을 미리 채우는 팝업이라, 여기서는 틀만 빌리고
        # 안쪽은 우리가 다시 꾸민다(테두리 없는 창 + 자체 타이틀바를 그대로 쓰기 위함)
        super().__init__("배틀크루저 전투", "", [], parent=parent)
        self._is_host = is_host
        self._my_nick = my_nick
        self._my_slot = -1
        self._taken_colors = set()
        self._players = {}          # 자리 -> (이름, 색)
        self._bots = 0              # 연습 상대 수
        self._konami = []           # 방금 누른 방향키들(숨겨진 색을 여는 커맨드)
        self._rainbow_open = False

        # ThemedDialog 가 만든 내용물을 비우고 우리 것으로 채운다
        old = self.layout()
        while old.count():
            item = old.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()

        old.setContentsMargins(1, 1, 1, 1)
        old.setSpacing(0)
        old.addWidget(_MiniTitleBar(self, "배틀크루저 전투"))

        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        self.title_image = self._build_title_image()
        if self.title_image is not None:
            layout.addWidget(self.title_image)

        self.notice = QLabel(
            "방을 만들었습니다. 채널 사람들이 '배틀크루저 전투 참가'를 치면 들어옵니다."
            if is_host else "방에 들어왔습니다. 방을 만든 사람이 시작하면 전투가 열립니다.")
        self.notice.setWordWrap(True)
        layout.addWidget(self.notice)

        self.players = QListWidget()
        self.players.setObjectName("battleLobbyPlayers")
        self.players.setMinimumHeight(110)
        layout.addWidget(self.players)

        setting_row = QHBoxLayout()
        setting_row.addWidget(QLabel("정원"))
        self.capacity = QComboBox()
        for count in range(bp.MIN_PLAYERS, bp.MAX_PLAYERS + 1):
            self.capacity.addItem(f"{count}명", count)
        self.capacity.setCurrentIndex(self.capacity.count() - 1)
        # 들어온 사람에게도 **보이되 못 바꾸게** 한다. 숨기면 몇 명짜리 방인지 모른다
        self.capacity.setEnabled(is_host)
        self.capacity.currentIndexChanged.connect(
            lambda _i: self.capacity_chosen.emit(self.capacity.currentData()))
        setting_row.addWidget(self.capacity)

        setting_row.addSpacing(12)
        setting_row.addWidget(QLabel("내 배 색"))
        self.color = QComboBox()
        for index, (name, _hex) in enumerate(SHIP_COLORS):
            if index == RAINBOW:
                continue           # 숨겨진 색 - 커맨드를 넣어야 나타난다
            self.color.addItem(_swatch(index), name, index)
        self.color.currentIndexChanged.connect(self._on_color_changed)
        setting_row.addWidget(self.color)
        setting_row.addStretch(1)
        layout.addLayout(setting_row)

        # 연습 상대 - 혼자 있을 때 시험해 보라고 둔다.
        # **내 화면에서만 도는 상대**라는 걸 분명히 적는다(남들에겐 안 보인다)
        self.practice_row = QHBoxLayout()
        self.practice_row.addWidget(QLabel("연습 상대"))
        self.bot_less = QPushButton("−")
        self.bot_less.setObjectName("secondary")
        self.bot_less.setFixedWidth(30)
        self.bot_less.clicked.connect(lambda: self._change_bots(-1))
        self.practice_row.addWidget(self.bot_less)
        self.bot_count = QLabel("0")
        self.bot_count.setObjectName("battleBotCount")
        self.bot_count.setFixedWidth(22)
        self.bot_count.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.practice_row.addWidget(self.bot_count)
        self.bot_more = QPushButton("+")
        self.bot_more.setFixedWidth(30)
        self.bot_more.clicked.connect(lambda: self._change_bots(1))
        self.practice_row.addWidget(self.bot_more)
        # 방을 연 사람만 정한다. 손님에게는 **보이되 못 바꾸게** 한다 - 몇 대가 있는지는
        # 알아야 한다
        for widget in (self.bot_less, self.bot_more):
            widget.setEnabled(is_host)
        self.practice_hint = QLabel(f"최대 {bp.MAX_BOTS}대")
        self.practice_hint.setObjectName("battlePracticeHint")
        self.practice_row.addWidget(self.practice_hint)
        self.practice_row.addStretch(1)
        layout.addLayout(self.practice_row)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        self.leave_button = QPushButton("그만두기")
        self.leave_button.setObjectName("secondary")
        self.leave_button.clicked.connect(self.reject)
        button_row.addWidget(self.leave_button)
        self.start_button = QPushButton("시작")
        self.start_button.clicked.connect(self.start_pressed.emit)
        # 시작은 방 연 사람만. 손님 화면에는 아예 없다(눌리지 않는 버튼은 헷갈린다)
        self.start_button.setVisible(is_host)
        button_row.addWidget(self.start_button)
        layout.addLayout(button_row)

        old.addWidget(body)
        self._refresh()
        self._watch_keys()

    @staticmethod
    def _build_title_image():
        """맨 위 시작 그림. 파일이 없으면 None을 돌려주고 그 자리는 그냥 비운다.

        빌드에 그림이 안 딸려온 경우에도 전투는 되어야 하므로 여기서 조용히 넘어간다
        (없는 그림 때문에 창이 안 뜨면 그게 더 큰 문제다).
        """
        path = _find_image_in_app_dirs((TITLE_IMAGE,))
        if not path:
            return None
        pixmap = QPixmap(path)
        if pixmap.isNull():
            return None
        label = QLabel()
        label.setObjectName("battleTitleImage")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # 원본이 커서 그대로 두면 창이 화면을 넘는다. 비율을 지켜 줄인다
        label.setPixmap(pixmap.scaledToWidth(
            TITLE_MAX_WIDTH, Qt.TransformationMode.SmoothTransformation))
        return label

    # ------------------------------------------------------------------
    def set_me(self, slot: int, color: int, capacity: int):
        """서버가 정해준 내 자리·색·정원(내가 고른 것과 다를 수 있다)."""
        self._my_slot = slot
        self._players[slot] = (self._my_nick, color)
        self._set_color_silently(color)
        index = self.capacity.findData(capacity)
        if index >= 0:
            blocked = self.capacity.blockSignals(True)
            self.capacity.setCurrentIndex(index)
            self.capacity.blockSignals(blocked)
        self._refresh()

    def set_players(self, players):
        """지금 방에 있는 사람들(내가 들어갈 때 받은 목록)."""
        for entry in players:
            self._players[entry["slot"]] = (entry["nick"], entry["color"])
        self._refresh()

    def add_player(self, slot: int, nick: str, color: int):
        self._players[slot] = (nick, color)
        self._refresh()

    def remove_player(self, slot: int):
        self._players.pop(slot, None)
        self._refresh()

    # ------------------------------------------------------------------
    def _on_color_changed(self, _index):
        self.color_chosen.emit(self.color.currentData())

    def _set_color_silently(self, color: int):
        blocked = self.color.blockSignals(True)
        index = self.color.findData(color)
        if index >= 0:
            self.color.setCurrentIndex(index)
        self.color.blockSignals(blocked)

    def _refresh(self):
        """참가자 목록과 '고를 수 있는 색', 시작 버튼 상태를 한 번에 맞춘다."""
        self.players.clear()
        for slot in sorted(self._players):
            nick, color = self._players[slot]
            label = f"{nick}  ({color_name(color)})"
            if slot == self._my_slot:
                label += "  ← 나"
            if slot == 0:
                label += "  [방장]"
            item = QListWidgetItem(_swatch(color), label)
            self.players.addItem(item)

        # 남이 쓰는 색은 못 고르게 한다. 서버도 막아주지만 화면에서 먼저 막는 게 친절하다
        self._taken_colors = {c for slot, (_n, c) in self._players.items()
                              if slot != self._my_slot}
        model = self.color.model()
        for index in range(self.color.count()):
            item = model.item(index)
            if item is not None:
                item.setEnabled(self.color.itemData(index) not in self._taken_colors)

        # 연습 상대를 켜두면 혼자서도 시작할 수 있다(그게 이 기능을 넣은 이유다)
        # 연습 상대를 넣어뒀으면 혼자서도 시작할 수 있다
        enough = len(self._players) + self._bots >= bp.MIN_PLAYERS
        self.start_button.setEnabled(self._is_host and enough)
        if self._is_host:
            self.start_button.setToolTip(
                "" if enough
                else f"{bp.MIN_PLAYERS}명 이상 모이거나 연습 상대를 넣어야 합니다")

    def _change_bots(self, delta: int):
        wanted = max(0, min(bp.MAX_BOTS, self._bots + delta))
        if wanted == self._bots:
            return
        self._bots = wanted
        self.bot_count.setText(str(wanted))
        self.bots_chosen.emit(wanted)
        self._refresh()

    def set_bots(self, count: int):
        """서버가 알려준 연습 상대 수(손님도 몇 대인지 알아야 같은 배를 그린다)."""
        self._bots = max(0, min(bp.MAX_BOTS, int(count)))
        self.bot_count.setText(str(self._bots))
        self._refresh()

    def bot_count_now(self) -> int:
        return self._bots

    def all_bot_slots(self):
        """연습 상대가 앉을 자리들 - **모두가 같은 자리에 같은 배를 그린다.**"""
        return list(range(bp.MAX_HUMANS, bp.MAX_HUMANS + self._bots))

    def bot_slots(self):
        """내가 굴려야 할 연습 상대 자리(방장일 때만 있다)."""
        return self.all_bot_slots() if self._is_host else []

    def taken_colors(self):
        """남이 쓰고 있어서 못 고르는 색들(검사와 창이 같은 값을 본다)."""
        return set(self._taken_colors)

    def player_count(self) -> int:
        return len(self._players)

    # ------------------------------------------------------------------
    def eventFilter(self, obj, event):
        """방향키를 순서대로 누르면 숨겨진 무지개가 열린다.

        **창의 keyPressEvent로는 못 잡는다.** 포커스가 색/정원 콤보나 참가자 목록에
        있으면 그쪽이 방향키를 먼저 먹어버려서 창까지 안 온다(그래서 커맨드가 안
        먹혔다). 그래서 이 창과 그 안의 부품들에 필터를 걸어 먼저 본다.

        **먹어치우지는 않는다**(False를 돌려준다) - 커맨드를 넣는 동안에도 색 고르기가
        평소대로 움직여야 한다. ESC로 닫는 것도 그대로다.
        """
        # **처음 받은 위젯에서만 센다.** 콤보가 안 먹는 키(←/→)는 부모로 전파되는데
        # 부모에도 필터가 걸려 있어서 같은 입력이 두세 번 세어진다. 그러면 순서가
        # '←←←→→→'처럼 돼서 커맨드가 영영 안 맞는다(실제로 그래서 안 먹혔다).
        # 포커스를 가진 위젯이 곧 처음 받는 위젯이다
        first_receiver = obj is (QApplication.focusWidget() or self)
        if (first_receiver and event.type() == QEvent.Type.KeyPress
                and not self._rainbow_open and event.key() in KONAMI):
            self._konami.append(event.key())
            # 마지막 몇 개만 본다 - 중간에 틀려도 이어서 다시 넣으면 되게
            self._konami = self._konami[-len(KONAMI):]
            if tuple(self._konami) == KONAMI:
                self._unlock_rainbow()
        return super().eventFilter(obj, event)

    def _watch_keys(self):
        """이 창과 안쪽 부품 전부에 필터를 건다(어디에 포커스가 있든 커맨드가 먹히게)."""
        self.installEventFilter(self)
        for child in self.findChildren(QWidget):
            child.installEventFilter(self)

    def _unlock_rainbow(self):
        if self._rainbow_open:
            return
        self._rainbow_open = True
        self.color.addItem(_swatch(RAINBOW), color_name(RAINBOW), RAINBOW)
        self.color.setCurrentIndex(self.color.count() - 1)   # 바로 골라준다
        self.notice.setText("★ 무지개 배틀크루저를 손에 넣었습니다 ★")
        self.rainbow_unlocked.emit()

    def rainbow_available(self) -> bool:
        """무지개가 열려 있는가(검사와 창이 같은 값을 본다)."""
        return self._rainbow_open

    def reject(self):
        self.closed.emit()
        super().reject()

    def closeEvent(self, event):
        self.closed.emit()
        super().closeEvent(event)
