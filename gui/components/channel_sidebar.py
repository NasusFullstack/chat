"""왼쪽 채널 사이드바 - 채널 목록 / '+' / 스크롤 화살표 / 아래쪽 만든이 표시.

예전엔 이 234줄이 ChatPage 안에 섞여 있어서, 채널 목록을 손보려면 채팅 화면 전체를
읽어야 했다. 여기로 옮기면서 지킨 것:

- **이 컴포넌트는 채널 '목록'만 안다.** 대화 내용도, 참여자도, 입력창도 모른다.
  누가 눌렸다는 사실만 신호로 알리고, 실제로 무엇을 할지는 화면(ChatPage)이 정한다.
- 안읽음 깜빡임도 여기 둔다. 깜빡이는 대상이 채널 항목이라 목록 밖에서 만질 이유가 없다.

바깥으로 나가는 신호:
  channel_selected(채널)  목록에서 고름
  add_requested()         '+' 눌림
  leave_requested(채널)   우클릭 -> 나가기
"""
from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (QFrame, QLabel, QListWidget, QListWidgetItem, QMenu,
                               QPushButton, QVBoxLayout, QWidget)

from gui.helpers import _build_unread_dot_icon, _find_logo_image
from gui.theme import (ADD_TAB_LABEL, APP_TITLE, CHANNEL_ROW_GAP, CHANNEL_ROW_HEIGHT,
                       CHANNEL_SCROLL_BTN_PX, CHANNEL_SIDEBAR_WIDTH, COPYRIGHT_YEAR,
                       DEVELOPER_EMAIL, DEVELOPER_GITHUB, DEVELOPER_NAME, FOOTER_LOGO_PX,
                       GITHUB_URL, UNREAD_BLINK_COLOR,
                       UNREAD_BLINK_COUNT, UNREAD_BLINK_INTERVAL_MS)
from version import APP_VERSION


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

    def __init__(self, top_gap: int, parent=None):
        super().__init__(parent)
        self.setObjectName("channelSidebar")
        self.setFixedWidth(CHANNEL_SIDEBAR_WIDTH)
        self._unread_timers: dict[str, QTimer] = {}
        self._unread_on: dict[str, bool] = {}
        self._unread_step: dict[str, int] = {}
        self._active_channel = ""

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        # 채팅창 위의 채널명 헤더와 같은 높이만큼 비워둬야 첫 채널 항목의 윗선이
        # 채팅 카드 윗선과 같은 높이에서 시작함
        outer.addSpacing(top_gap)
        self._top_gap = top_gap

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
        self.footer = _SidebarFooter()
        outer.addWidget(self.footer, 0)

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
        count = self.list.count()
        if count == 0:
            self.list.setFixedHeight(0)
            self._sync_arrows()
            return
        row = self.list.visualItemRect(self.list.item(0))
        # 항목 사이 간격(QSS의 margin-bottom)까지 포함해야 마지막 줄이 안 잘림
        step = row.height() + CHANNEL_ROW_GAP
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
        used = (self._top_gap + CHANNEL_ROW_HEIGHT          # 헤더 자리 + '+' 버튼
                + CHANNEL_SCROLL_BTN_PX * 2                  # 위/아래 화살표
                + self.footer.sizeHint().height())
        # 최소 한 칸은 보이게(너무 작으면 목록이 아예 안 보임)
        return max(step, self.height() - used)

    def scroll_by(self, direction: int):
        bar = self.list.verticalScrollBar()
        bar.setValue(bar.value() + direction * (CHANNEL_ROW_HEIGHT + CHANNEL_ROW_GAP))
        self._sync_arrows()

    def _sync_arrows(self):
        bar = self.list.verticalScrollBar()
        self.scroll_up.setVisible(bar.maximum() > 0 and bar.value() > 0)
        self.scroll_down.setVisible(bar.maximum() > 0 and bar.value() < bar.maximum())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.sync_height()   # 창 높이가 바뀌면 목록이 쓸 수 있는 자리도 바뀜

    # ---------------- 안읽음 표시 ----------------

    def mark_unread(self, channel: str):
        """채널 항목에 작은 점이 몇 번 깜빡인 뒤, 그 채널을 볼 때까지 점을 유지함.

        글자색을 깜빡이는 방식은 못 씀 - 스타일시트의 색 지정이 항상 이겨서 코드로 바꾼
        글자색이 안 먹힌다(예전 탭에서 이미 겪음). 아이콘은 스타일시트 영향을 안 받는다.
        """
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
        self.list.item(row).setIcon(
            _build_unread_dot_icon(UNREAD_BLINK_COLOR) if on else QIcon())
        if on and step >= 2 * UNREAD_BLINK_COUNT - 1:
            # 정해진 횟수만큼 깜빡였으니 타이머만 멈추고 밝은 점은 그대로 둠
            # (실제로 그 채널을 봐야 stop_blink에서 사라짐)
            self._kill_timer(channel)

    def stop_blink(self, channel: str):
        self._kill_timer(channel)
        self._unread_on.pop(channel, None)
        self._unread_step.pop(channel, None)
        row = self.row_of(channel)
        if row >= 0:
            self.list.item(row).setIcon(QIcon())

    def _kill_timer(self, channel: str):
        timer = self._unread_timers.pop(channel, None)
        if timer is not None:
            timer.stop()
            timer.deleteLater()

    def is_blinking(self, channel: str) -> bool:
        return channel in self._unread_timers


class _SidebarFooter(QWidget):
    """사이드바 아래쪽 - 로고/이름/버전/만든이. 채널이 적을 때 비는 자리를 채움."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("sidebarFooter")
        column = QVBoxLayout(self)
        column.setContentsMargins(10, 10, 10, 12)
        column.setSpacing(2)

        logo_path = _find_logo_image()
        if logo_path:
            logo = QLabel()
            logo.setObjectName("footerLogo")
            logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
            logo.setPixmap(QPixmap(logo_path).scaled(
                FOOTER_LOGO_PX, FOOTER_LOGO_PX, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation))
            column.addWidget(logo, 0, Qt.AlignmentFlag.AlignHCenter)

        title = QLabel(f"{APP_TITLE}  <span style='color:#7f8296'>v{APP_VERSION}</span>")
        title.setObjectName("footerTitle")
        title.setTextFormat(Qt.TextFormat.RichText)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        column.addWidget(title)

        maker = QLabel(
            f'<a href="mailto:{DEVELOPER_EMAIL}" style="color:#8f92a6; text-decoration:none;">'
            f"{DEVELOPER_EMAIL}</a>")
        maker.setObjectName("footerMaker")
        maker.setTextFormat(Qt.TextFormat.RichText)
        maker.setAlignment(Qt.AlignmentFlag.AlignCenter)
        maker.setOpenExternalLinks(True)
        maker.setToolTip("만든 사람에게 메일 보내기")
        column.addWidget(maker)

        # 만든 사람 이름만 있으면 그게 깃허브 계정인지 알 수 없어서, 아이콘 대신 글자로
        # 밝히고 저장소로 바로 갈 수 있게 링크를 건다
        github = QLabel(
            f'<a href="{GITHUB_URL}" style="color:#8f92a6; text-decoration:none;">'
            f"GitHub @{DEVELOPER_GITHUB}</a>")
        github.setObjectName("footerGithub")
        github.setTextFormat(Qt.TextFormat.RichText)
        github.setAlignment(Qt.AlignmentFlag.AlignCenter)
        github.setOpenExternalLinks(True)
        github.setToolTip(GITHUB_URL)
        column.addWidget(github)

        copyright_label = QLabel(f"© {COPYRIGHT_YEAR} {DEVELOPER_NAME}")
        copyright_label.setObjectName("footerCopyright")
        copyright_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        column.addWidget(copyright_label)
