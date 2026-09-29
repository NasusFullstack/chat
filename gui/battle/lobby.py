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
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import (QComboBox, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
                               QPushButton, QVBoxLayout, QWidget)

import battle_protocol as bp
from gui.themed_dialogs import ThemedDialog, _MiniTitleBar

# 배 색 - battle_protocol.COLOR_COUNT 개여야 한다(서버가 번호로만 주고받으므로
# 실제 색은 화면이 정한다). 스타1 플레이어 색을 본떠 서로 확실히 구분되게 골랐다
SHIP_COLORS = (
    ("빨강", "#e53935"),
    ("파랑", "#1e88e5"),
    ("청록", "#00acc1"),
    ("보라", "#8e24aa"),
    ("주황", "#fb8c00"),
    ("갈색", "#8d6e63"),
    ("연두", "#7cb342"),
    ("노랑", "#fdd835"),
)
assert len(SHIP_COLORS) == bp.COLOR_COUNT, "색 개수가 규약과 다르면 서버와 말이 안 통한다"

SWATCH_PX = 14


def color_name(index: int) -> str:
    return SHIP_COLORS[index % len(SHIP_COLORS)][0]


def color_hex(index: int) -> str:
    return SHIP_COLORS[index % len(SHIP_COLORS)][1]


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

    def __init__(self, is_host: bool, my_nick: str, parent=None):
        # ThemedDialog 는 글/버튼을 미리 채우는 팝업이라, 여기서는 틀만 빌리고
        # 안쪽은 우리가 다시 꾸민다(테두리 없는 창 + 자체 타이틀바를 그대로 쓰기 위함)
        super().__init__("배틀크루저 전투", "", [], parent=parent)
        self._is_host = is_host
        self._my_nick = my_nick
        self._my_slot = -1
        self._taken_colors = set()
        self._players = {}          # 자리 -> (이름, 색)

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
            self.color.addItem(_swatch(index), name, index)
        self.color.currentIndexChanged.connect(self._on_color_changed)
        setting_row.addWidget(self.color)
        setting_row.addStretch(1)
        layout.addLayout(setting_row)

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

        enough = len(self._players) >= bp.MIN_PLAYERS
        self.start_button.setEnabled(self._is_host and enough)
        if self._is_host:
            self.start_button.setToolTip(
                "" if enough else f"{bp.MIN_PLAYERS}명 이상 모여야 시작할 수 있습니다")

    def taken_colors(self):
        """남이 쓰고 있어서 못 고르는 색들(검사와 창이 같은 값을 본다)."""
        return set(self._taken_colors)

    def player_count(self) -> int:
        return len(self._players)

    def reject(self):
        self.closed.emit()
        super().reject()

    def closeEvent(self, event):
        self.closed.emit()
        super().closeEvent(event)
