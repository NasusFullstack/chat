"""왼쪽 채널 사이드바 - 접기 버튼 / 채널 목록 / '+' / 스크롤 화살표.

예전엔 이 234줄이 ChatPage 안에 섞여 있어서, 채널 목록을 손보려면 채팅 화면 전체를
읽어야 했다. 여기로 옮기면서 지킨 것:

- **이 컴포넌트는 채널 '목록'만 안다.** 대화 내용도, 참여자도, 입력창도 모른다.
  누가 눌렸다는 사실만 신호로 알리고, 실제로 무엇을 할지는 화면(ChatPage)이 정한다.
- 안읽음 깜빡임도 여기 둔다. 깜빡이는 대상이 채널 항목이라 목록 밖에서 만질 이유가 없다.
- **접기는 폭만 줄이는 일이라 여기서 스스로 한다.** 바깥은 아무것도 안 해도 된다 -
  폭이 고정폭이라 줄어든 만큼 대화 영역이 저절로 넓어진다.

바깥으로 나가는 신호:
  channel_selected(채널)  목록에서 고름
  add_requested()         '+' 눌림
  leave_requested(채널)   우클릭 -> 나가기
  collapsed_changed(접힘) 접거나 폄(안읽음 표시를 다르게 알릴 때 쓸 수 있음)
"""
from PySide6.QtCore import QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath
from PySide6.QtWidgets import (QFrame, QListWidget, QListWidgetItem, QMenu, QPushButton,
                               QStyledItemDelegate, QVBoxLayout, QWidget)

from gui.theme import (ADD_TAB_LABEL, CHANNEL_ROW_GAP, CHANNEL_ROW_HEIGHT,
                       CHANNEL_SCROLL_BTN_PX, CHANNEL_SIDEBAR_COLLAPSED_WIDTH,
                       CHANNEL_SIDEBAR_WIDTH, UNREAD_BLINK_COLOR, UNREAD_BLINK_COUNT,
                       UNREAD_BLINK_INTERVAL_MS, UNREAD_TINT_ALPHA_IDLE,
                       UNREAD_TINT_ALPHA_OFF, UNREAD_TINT_ALPHA_ON, UNREAD_TINT_RADIUS)


class ChannelSidebar(QWidget):
    """세로로 쌓이는 알약 모양 채널 목록.

    예전엔 채팅창 위쪽 가로 탭이었는데, 채널이 늘면 폭이 모자라고 이름이 잘렸다.
    세로 목록은 채널이 몇 개든 같은 폭으로 온전히 보인다.

    나가기는 항목을 우클릭해서 고른다 - 항목마다 x를 박아두면 채널 이름보다 버튼이 먼저
    눈에 들어와 어수선해지기 때문.
    """

    channel_selected = Signal(str)
    add_requested = Signal()
    leave_requested = Signal(str)
    collapsed_changed = Signal(bool)

    def __init__(self, top_gap: int, parent=None):
        super().__init__(parent)
        self.setObjectName("channelSidebar")
        self.setFixedWidth(CHANNEL_SIDEBAR_WIDTH)
        self._unread_timers: dict[str, QTimer] = {}
        self._unread_on: dict[str, bool] = {}
        self._unread_step: dict[str, int] = {}
        self._active_channel = ""
        self._collapsed = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self._top_gap = top_gap

        # 채팅창 위의 채널명 헤더와 같은 높이를 차지해야 첫 채널 항목의 윗선이 채팅 카드
        # 윗선과 같은 높이에서 시작함. 예전엔 그냥 빈 공간이었는데, 접기 버튼을 여기 넣으면
        # 새 자리를 만들지 않고도 버튼이 생긴다(세로 정렬도 그대로 유지됨)
        self.toggle_btn = QPushButton()
        self.toggle_btn.setObjectName("channelToggleBtn")
        self.toggle_btn.setFixedHeight(top_gap)
        self.toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle_btn.clicked.connect(self.toggle_collapsed)
        outer.addWidget(self.toggle_btn, 0)

        self.scroll_up = self._make_arrow("⌃", "이전 채널 보기", -1)
        outer.addWidget(self.scroll_up, 0)

        self.list = QListWidget()
        self.list.setObjectName("channelList")
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.setFrameShape(QFrame.Shape.NoFrame)
        self.list.currentRowChanged.connect(self._on_row_changed)
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._show_menu)
        # 안읽음 색칠은 그리는 사람을 바꿔서 한다 - 이유는 _UnreadTintDelegate 설명 참고
        self._tint = _UnreadTintDelegate(self.list)
        self.list.setItemDelegate(self._tint)
        outer.addWidget(self.list, 0)

        # '+'는 마지막 채널 바로 아래에, 네모 없이 기호만. 채널 항목과 같은 폭을 차지하게
        # 두고 그 안에서 가운데 정렬해야 항목들과 세로 중심선이 맞음
        self.add_btn = QPushButton(ADD_TAB_LABEL)
        self.add_btn.setObjectName("addChannelBtn")
        self.add_btn.setFixedHeight(CHANNEL_ROW_HEIGHT)
        self.add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_btn.setToolTip("새 채널에 입장합니다")
        self.add_btn.clicked.connect(self.add_requested.emit)
        outer.addWidget(self.add_btn, 0)

        self.scroll_down = self._make_arrow("⌄", "다음 채널 보기", 1)
        outer.addWidget(self.scroll_down, 0)

        outer.addStretch(1)
        self._sync_toggle_look()

    def _make_arrow(self, glyph: str, tip: str, direction: int) -> QPushButton:
        """채널이 많아 자리가 모자랄 때 목록을 미는 화살표.

        스크롤바를 띄우면 알약 항목 옆에 회색 막대가 붙어 지저분해서 화살표로 민다.
        """
        button = QPushButton(glyph)
        button.setObjectName("channelScrollBtn")
        button.setFixedHeight(CHANNEL_SCROLL_BTN_PX)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setToolTip(tip)
        button.clicked.connect(lambda: self.scroll_by(direction))
        button.setVisible(False)
        return button

    # ---------------- 채널 목록 ----------------

    def add_channel(self, channel: str):
        if self.row_of(channel) >= 0:
            return
        item = QListWidgetItem(channel)
        # 표시 이름과 별개로 실제 채널명을 들고 있게 함(안읽음 표시 등으로 보이는 글자가
        # 바뀌어도 어떤 채널인지 잃지 않도록)
        item.setData(Qt.ItemDataRole.UserRole, channel)
        item.setSizeHint(QSize(0, CHANNEL_ROW_HEIGHT))
        item.setToolTip(f"{channel}\n우클릭하면 나가기")
        self.list.addItem(item)
        self.sync_height()

    def remove_channel(self, channel: str):
        self.stop_blink(channel)
        row = self.row_of(channel)
        if row >= 0:
            self.list.takeItem(row)
            self.sync_height()

    def row_of(self, channel: str) -> int:
        """그 채널이 몇 번째 줄인지. 없으면 -1"""
        for row in range(self.list.count()):
            if self.list.item(row).data(Qt.ItemDataRole.UserRole) == channel:
                return row
        return -1

    def set_active(self, channel: str):
        self._active_channel = channel
        row = self.row_of(channel)
        if row >= 0 and self.list.currentRow() != row:
            self.list.setCurrentRow(row)
        self.stop_blink(channel)

    def count(self) -> int:
        return self.list.count()

    def _on_row_changed(self, row: int):
        if row < 0:
            return
        self.channel_selected.emit(self.list.item(row).data(Qt.ItemDataRole.UserRole))

    def _show_menu(self, pos):
        item = self.list.itemAt(pos)
        if item is None:
            return
        channel = item.data(Qt.ItemDataRole.UserRole)
        menu = QMenu(self.list)
        leave = menu.addAction(f"'{channel}' 나가기")
        if menu.exec(self.list.mapToGlobal(pos)) is leave:
            self.leave_requested.emit(channel)

    # ---------------- 높이 / 스크롤 ----------------

    def sync_height(self):
        """자리가 되는 만큼만 목록을 보여주고, 넘치면 화살표로 밀게 함."""
        if self._collapsed:
            return
        count = self.list.count()
        if count == 0:
            self.list.setFixedHeight(0)
            self._sync_arrows()
            return
        # 한 칸의 높이는 실측한 줄 높이 그대로다. 여기에 CHANNEL_ROW_GAP을 더하면 안 된다 -
        # 그 여백은 줄 '사이'가 아니라 줄 '안쪽'에 그려지므로(실측: 줄이 0, 44, 88...에서
        # 시작) 더하면 채널 수만큼 빈 공간이 쌓이고, 잘라낸 자리도 줄 경계와 어긋나
        # 마지막 항목이 반쯤 걸쳐 보인다
        row = self.list.visualItemRect(self.list.item(0))
        step = row.height()
        needed = step * count
        available = self._available_height(step)
        if available > 0 and available < needed:
            # 칸 단위로 잘라야 마지막 항목이 반쯤 걸쳐 보이지 않음
            available = max(step, (available // step) * step)
        self.list.setFixedHeight(min(needed, available) if available > 0 else needed)
        self._sync_arrows()

    def _available_height(self, step: int) -> int:
        if self.height() <= 0:
            return 0
        used = (self._top_gap + CHANNEL_ROW_HEIGHT          # 접기 버튼 줄 + '+' 버튼
                + CHANNEL_SCROLL_BTN_PX * 2)                 # 위/아래 화살표
        # 최소 한 칸은 보이게(너무 작으면 목록이 아예 안 보임)
        return max(step, self.height() - used)

    def scroll_by(self, direction: int):
        bar = self.list.verticalScrollBar()
        bar.setValue(bar.value() + direction * CHANNEL_ROW_HEIGHT)
        self._sync_arrows()

    def _sync_arrows(self):
        if self._collapsed:
            return  # 접힌 동안에는 아무것도 다시 나타나면 안 됨
        bar = self.list.verticalScrollBar()
        self.scroll_up.setVisible(bar.maximum() > 0 and bar.value() > 0)
        self.scroll_down.setVisible(bar.maximum() > 0 and bar.value() < bar.maximum())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.sync_height()   # 창 높이가 바뀌면 목록이 쓸 수 있는 자리도 바뀜

    # ---------------- 안읽음 표시 ----------------

    def mark_unread(self, channel: str):
        """채널 항목이 옅은 노랑으로 몇 번 깜빡인 뒤, 그 채널을 볼 때까지 노란색을 유지함."""
        if channel == self._active_channel or self.row_of(channel) < 0:
            return
        if channel in self._unread_timers:
            return  # 이미 깜빡이는 중
        timer = QTimer(self)
        timer.timeout.connect(lambda ch=channel: self._toggle_blink(ch))
        self._unread_timers[channel] = timer
        self._unread_on[channel] = False
        self._unread_step[channel] = 0
        timer.start(UNREAD_BLINK_INTERVAL_MS)
        self._toggle_blink(channel)  # 바로 한 번 켜서 즉각 반응하는 느낌을 줌

    def _toggle_blink(self, channel: str):
        row = self.row_of(channel)
        if row < 0 or channel == self._active_channel:
            self.stop_blink(channel)
            return
        step = self._unread_step.get(channel, 0) + 1
        self._unread_step[channel] = step
        on = not self._unread_on.get(channel, False)
        self._unread_on[channel] = on
        self._tint.set_alpha(channel, UNREAD_TINT_ALPHA_ON if on else UNREAD_TINT_ALPHA_OFF)
        if on and step >= 2 * UNREAD_BLINK_COUNT - 1:
            # 정해진 횟수만큼 깜빡였으니 타이머만 멈추고, 읽을 때까지 노란색을 유지한다
            # (실제로 그 채널을 봐야 stop_blink에서 사라짐)
            self._kill_timer(channel)
            self._tint.set_alpha(channel, UNREAD_TINT_ALPHA_IDLE)

    def stop_blink(self, channel: str):
        """그 채널을 봤다 - 깜빡임도 남은 노란색도 지운다."""
        self._kill_timer(channel)
        self._unread_on.pop(channel, None)
        self._unread_step.pop(channel, None)
        self._tint.set_alpha(channel, 0)

    def _kill_timer(self, channel: str):
        timer = self._unread_timers.pop(channel, None)
        if timer is not None:
            timer.stop()
            timer.deleteLater()

    def is_blinking(self, channel: str) -> bool:
        return channel in self._unread_timers

    def unread_alpha(self, channel: str) -> int:
        """그 채널에 지금 칠해진 노란색의 진하기(0이면 안읽음 표시 없음)."""
        return self._tint.alpha_of(channel)

    # ---------------- 접기 ----------------

    def is_collapsed(self) -> bool:
        return self._collapsed

    def toggle_collapsed(self):
        self.set_collapsed(not self._collapsed)

    def set_collapsed(self, collapsed: bool):
        """접으면 얇은 띠만 남기고 대화 영역에 폭을 내준다.

        위젯을 숨기는 것으로 충분하다 - 채널 목록의 상태(선택/안읽음 타이머)는 그대로
        살아 있어서, 펴면 접기 전 화면이 그대로 돌아온다. 목록을 비웠다가 다시 채우는
        방식이었다면 깜빡임 타이머와 선택 상태를 매번 복구해야 했을 것이다.
        """
        if collapsed == self._collapsed:
            return
        self._collapsed = collapsed
        for widget in (self.list, self.add_btn, self.scroll_up, self.scroll_down):
            widget.setVisible(not collapsed)
        self.setFixedWidth(CHANNEL_SIDEBAR_COLLAPSED_WIDTH if collapsed
                           else CHANNEL_SIDEBAR_WIDTH)
        self._sync_toggle_look()
        if not collapsed:
            self.sync_height()
            self._sync_arrows()
        self.collapsed_changed.emit(collapsed)

    def _sync_toggle_look(self):
        """접힘 상태에 따라 버튼 모양을 바꾼다(펼침: 채널 + 접는 화살표 / 접힘: 펴는 화살표)."""
        if self._collapsed:
            self.toggle_btn.setText("»")
            self.toggle_btn.setToolTip("채널 목록 펼치기")
        else:
            self.toggle_btn.setText("채널  «")
            self.toggle_btn.setToolTip("채널 목록 접기")


class _UnreadTintDelegate(QStyledItemDelegate):
    """안읽음 채널 항목 위에 옅은 노란색을 덧칠하는 그리는이.

    왜 항목의 배경색(`item.setBackground()`)을 안 쓰는가: 스타일시트에
    `QListWidget#channelList::item { background-color: ... }`가 있으면 **항상 그쪽이 이겨서**
    코드로 준 배경색은 무시된다(예전 탭에서 글자색으로 같은 일을 겪어 아이콘으로 우회했었다).
    그리는이는 스타일이 다 그린 **뒤에** 덧칠하므로 이 싸움에서 자유롭고, 선택/마우스오버
    상태도 그대로 비쳐 보인다(반투명이라 덮지 않고 물들이기만 함).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._alphas: dict[str, int] = {}

    def set_alpha(self, channel: str, alpha: int):
        if alpha <= 0:
            self._alphas.pop(channel, None)
        else:
            self._alphas[channel] = alpha
        view = self.parent()
        if view is not None:
            view.viewport().update()

    def alpha_of(self, channel: str) -> int:
        return self._alphas.get(channel, 0)

    def paint(self, painter: QPainter, option, index):
        super().paint(painter, option, index)
        alpha = self._alphas.get(index.data(Qt.ItemDataRole.UserRole), 0)
        if alpha <= 0:
            return
        color = QColor(UNREAD_BLINK_COLOR)
        color.setAlpha(alpha)
        # 항목의 둥근 모서리를 그대로 따라가야 네모난 색판이 삐져나오지 않는다.
        # 아래를 CHANNEL_ROW_GAP만큼 비우는 이유: 넘어오는 사각형은 줄 전체(44px)인데
        # 알약은 QSS의 margin-bottom만큼 그 안쪽에 그려진다. 그대로 칠하면 항목 사이
        # 틈까지 노랗게 번진다(실측으로 확인)
        path = QPainterPath()
        path.addRoundedRect(
            QRectF(option.rect).adjusted(0.5, 0.5, -0.5, -CHANNEL_ROW_GAP - 0.5),
            UNREAD_TINT_RADIUS, UNREAD_TINT_RADIUS)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillPath(path, color)
        painter.restore()
