"""채팅 메시지/로그/채널 탭바 위젯 (MessageWidget/ChannelLogView/_ChannelTabBar).

이름들은 몽키패치 대상이 아니라 어디서든 자유롭게 직접 import해도 안전함
(gui_client.py의 순환참조 노트 참고 - 그 규칙은 다른 5개 함수에만 적용됨).
"""
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QScrollArea, QSizePolicy, QTabBar, QVBoxLayout, QWidget,
)

from chat_core.commands import KIND_ACTION, KIND_CHAT, KIND_NOTICE
from gui.helpers import _format_ts, _linkify
from gui.theme import ADD_TAB_LABEL, AVATAR_MSG_PX, CHANNEL_TAB_FIXED_WIDTH, TIMESTAMP_BADGE_HEIGHT_PX


def _message_html(sender: str, safe_text: str, mine: bool, kind: str) -> str:
    """메시지 종류별 표시 형식 - IRC 클라이언트들의 관행을 그대로 따름.

    /me(행동)는 "* 닉 행동", /notice(공지)는 "-닉- 내용"으로 보통 채팅과 눈에 띄게 구분한다.
    """
    if kind == KIND_ACTION:
        return f'<span style="color:#b39ddb"><i>* <b>{sender}</b> {safe_text}</i></span>'
    if kind == KIND_NOTICE:
        return f'<span style="color:#7fd6a8">-<b>{sender}</b>- {safe_text}</span>'
    color = "#7cd0ff" if mine else "#ffd27c"
    return f'<span style="color:{color}"><b>{sender}</b></span>: {safe_text}'


class MessageWidget(QWidget):
    """채팅 메시지 한 개 - 왼쪽에 아바타, 오른쪽 아래에 시간 타원 배지"""

    def __init__(self, sender: str, text: str, mine: bool, ts: float, avatar_pixmap: QPixmap,
                 parent=None, kind: str = KIND_CHAT):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 1, 4, 1)

        avatar_label = QLabel()
        avatar_label.setFixedSize(AVATAR_MSG_PX, AVATAR_MSG_PX)
        avatar_label.setPixmap(avatar_pixmap.scaled(
            AVATAR_MSG_PX, AVATAR_MSG_PX,
            Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.FastTransformation,
        ))
        layout.addWidget(avatar_label, 0, Qt.AlignmentFlag.AlignTop)

        # 텍스트를 시간 배지와 같은 QHBoxLayout에 나란히 넣으면 word-wrap 라벨의
        # sizeHint()가 줄바꿈 전(한 줄) 너비를 그대로 요구해버려서 채팅창 폭을 넘어서는
        # 메시지가 오른쪽으로 잘리고, 그 여파로 스크롤 영역 크기 계산도 꼬여 아래쪽에
        # 빈 공간이 생기는 문제가 있었음. 텍스트를 세로 레이아웃에서 혼자 전체 폭을
        # 쓰게 하면 Qt가 heightForWidth를 제대로 적용해 창 크기에 맞춰 줄바꿈됨.
        body = QVBoxLayout()
        body.setSpacing(1)

        safe_text = text.replace("<", "&lt;").replace(">", "&gt;")
        safe_text = _linkify(safe_text)
        text_label = QLabel(_message_html(sender, safe_text, mine, kind))
        text_label.setTextFormat(Qt.TextFormat.RichText)
        text_label.setWordWrap(True)
        text_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        text_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.LinksAccessibleByMouse
        )
        text_label.setOpenExternalLinks(True)
        text_label.setCursor(Qt.CursorShape.IBeamCursor)
        body.addWidget(text_label)
        self._text_label = text_label

        badge_row = QHBoxLayout()
        badge_row.addStretch(1)
        badge = QLabel(_format_ts(ts))
        badge.setObjectName("timestampBadge")
        badge.setFixedHeight(TIMESTAMP_BADGE_HEIGHT_PX)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge_row.addWidget(badge)
        body.addLayout(badge_row)

        layout.addLayout(body, 1)

    def set_wrap_width(self, view_width: int):
        """네트워크로 비동기로 도착한 메시지는 QScrollArea 레이아웃이 아직 완전히
        안정되기 전에 위젯이 추가될 때가 있어, word-wrap 라벨의 자동 heightForWidth
        계산이 화면 폭을 반영 못 하고 줄바꿈이 안 풀린 채로 굳어버리는 경우가 있었음
        (내가 직접 보낸 메시지는 항상 창이 안정된 상태에서 추가돼서 이 문제가 안 드러남).
        Qt의 자동 계산에 기대는 대신 뷰포트 폭을 직접 계산해서 넘겨주면 타이밍과
        무관하게 항상 정확히 줄바꿈됨."""
        inner_width = max(40, view_width - AVATAR_MSG_PX - 24)
        self._text_label.setMaximumWidth(inner_width)


def _build_system_label(text: str) -> QLabel:
    label = QLabel(f'<span style="color:#9a9cad"><i>* {text}</i></span>')
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    label.setWordWrap(True)
    return label


class ChannelLogView(QScrollArea):
    """채널 하나의 메시지 목록 - 메시지마다 개별 위젯으로 쌓음 (QTextEdit HTML 방식 대체)"""

    def __init__(self, channel: str, parent=None):
        super().__init__(parent)
        self.channel_name = channel
        self.setWidgetResizable(True)
        # 테두리는 QSS(QScrollArea#chatLog)에서 참여자 목록과 똑같은 모양으로 그림 -
        # 예전엔 탭 pane 쪽 테두리와 겹쳐서 선이 끊겨 보였음
        self.setObjectName("chatLog")
        self.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        self._layout = QVBoxLayout(content)
        self._layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._layout.setSpacing(2)
        self.setWidget(content)
        self._messages: list[MessageWidget] = []
        # 숨겨진(비활성) 탭은 자기 자신의 viewport().width()가 실제 화면 폭과 다르게
        # 나올 수 있어서(레이아웃이 아직 그 탭을 기준으로 확정되지 않았으므로), ChatPage가
        # 항상 보이는 self.tabs 위젯 기준으로 계산한 폭을 미리 알려주는 값. 0이면 아직
        # 못 받은 상태라 자기 viewport 값으로 대체함
        self._container_width = 0

        # QTimer.singleShot(0, ...)로 "다음 이벤트 루프 틱에 맨 아래로" 하는 방식은
        # 레이아웃이 새 위젯의 크기를 아직 계산 전이라 스크롤 범위(maximum)가 갱신되기
        # 전에 실행될 때가 있어 스크롤이 씹히는 경우가 있었음. rangeChanged는 스크롤
        # 범위가 실제로 확정된 바로 그 순간에 울리므로 훨씬 안정적으로 맨 아래로 붙음.
        self.verticalScrollBar().rangeChanged.connect(self._scroll_to_bottom)

    def _scroll_to_bottom(self, minimum: int, maximum: int):
        self.verticalScrollBar().setValue(maximum)

    def _effective_width(self) -> int:
        return self._container_width or self.viewport().width()

    def append_message(self, sender: str, text: str, mine: bool, ts: float, avatar_pixmap: QPixmap,
                       kind: str = KIND_CHAT):
        widget = MessageWidget(sender, text, mine, ts, avatar_pixmap, kind=kind)
        widget.set_wrap_width(self._effective_width())
        self._layout.addWidget(widget)
        self._messages.append(widget)

    def append_system(self, text: str):
        self._layout.addWidget(_build_system_label(text))

    def set_container_width(self, width: int):
        """ChatPage가 (항상 보이는 self.tabs 기준으로) 미리 계산해서 알려주는 폭.
        탭을 실제로 보게 될 때가 아니라 채널 추가/창 리사이즈 시점에 미리 반영해두므로,
        탭을 전환하는 순간에 메시지들이 눈앞에서 다시 줄바꿈되며 스크롤이 출렁이는 게 없어짐."""
        if width <= 0 or width == self._container_width:
            return
        self._container_width = width
        self.refresh_wrap_widths()

    def refresh_wrap_widths(self):
        width = self._effective_width()
        for widget in self._messages:
            widget.set_wrap_width(width)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # 사용자가 실제로 창 크기를 바꿀 때는 지금 보이는 탭 기준 실측값으로 보정
        self.refresh_wrap_widths()


class _ChannelTabBar(QTabBar):
    """채널 탭은 글자 수와 무관하게 항상 고정폭, 맨 끝의 '+' 탭만 그 절반 크기로 그림"""

    def tabSizeHint(self, index: int) -> QSize:
        size = super().tabSizeHint(index)
        if self.tabText(index) == ADD_TAB_LABEL:
            return QSize(CHANNEL_TAB_FIXED_WIDTH // 2, size.height())
        return QSize(CHANNEL_TAB_FIXED_WIDTH, size.height())
