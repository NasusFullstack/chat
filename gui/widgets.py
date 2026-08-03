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
from gui.helpers import _format_ts, _linkify, extract_urls, text_is_only_urls
from gui.theme import (
    ADD_TAB_LABEL, ADD_TAB_WIDTH, AVATAR_MSG_PX, CHANNEL_TAB_FIXED_WIDTH, CHANNEL_TAB_HEIGHT,
    TIMESTAMP_BADGE_HEIGHT_PX,
)


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
                 parent=None, kind: str = KIND_CHAT, preview: bool = False, image_fetcher=None):
        super().__init__(parent)
        # 말풍선 배경은 채팅 카드 면색이 그대로 비쳐야 함. objectName으로 한정하지 않으면
        # 이 규칙이 자식(링크 미리보기 카드 등)까지 상속돼 그쪽 배경/테두리를 지워버림
        self.setObjectName("messageRow")
        self.setStyleSheet("QWidget#messageRow { background: transparent; }")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 1, 4, 1)

        avatar_label = QLabel()
        avatar_label.setObjectName("messageAvatar")
        avatar_label.setStyleSheet("QLabel#messageAvatar { background: transparent; }")
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
        text_label.setObjectName("messageText")
        text_label.setStyleSheet("QLabel#messageText { background: transparent; }")
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

        # 링크 미리보기 자리. 못 받으면 높이 0이라 평소 메시지와 똑같이 보임
        self.preview_area = None
        self.preview_urls = extract_urls(text) if preview else []
        # 링크만 있는 메시지는 미리보기가 뜨면 주소 문자열을 지움 - 긴 주소가 몇 줄씩
        # 차지하기만 하고, 그림/카드를 눌러 열 수 있어서 주소가 없어도 못 여는 일이 없음.
        # 미리보기를 끝내 못 받으면 콜백이 안 불려서 주소가 그대로 남음
        self._sender_only_html = _message_html(sender, "", mine, kind).rstrip(": ")
        self._link_only = bool(self.preview_urls) and text_is_only_urls(text)
        if self.preview_urls:
            from gui.link_preview import LinkPreviewArea
            self.preview_area = LinkPreviewArea(
                self.preview_urls, image_fetcher, self,
                on_preview_shown=self._hide_url_text if self._link_only else None,
            )
            body.addWidget(self.preview_area)

        badge_row = QHBoxLayout()
        badge_row.addStretch(1)
        badge = QLabel(_format_ts(ts))
        badge.setObjectName("timestampBadge")
        badge.setFixedHeight(TIMESTAMP_BADGE_HEIGHT_PX)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge_row.addWidget(badge)
        body.addLayout(badge_row)

        layout.addLayout(body, 1)

    def _hide_url_text(self):
        """미리보기가 떴으니 주소 문자열은 지우고 보낸 사람만 남김.

        라벨을 통째로 숨기지 않는 이유: 누가 보낸 건지는 남아야 하기 때문."""
        self._text_label.setText(self._sender_only_html)

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
    label.setObjectName("systemNotice")
    label.setStyleSheet("QLabel#systemNotice { background: transparent; }")
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    label.setWordWrap(True)
    return label


class ChannelLogView(QScrollArea):
    """채널 하나의 메시지 목록 - 메시지마다 개별 위젯으로 쌓음 (QTextEdit HTML 방식 대체)"""

    def __init__(self, channel: str, parent=None, image_fetcher=None):
        super().__init__(parent)
        self.channel_name = channel
        # 미리보기 이미지를 받아오는 담당자 - 모든 채널이 하나를 공유함(연결 재사용)
        self._image_fetcher = image_fetcher
        self.setWidgetResizable(True)
        # 테두리는 QSS(QScrollArea#chatLog)에서 참여자 목록과 똑같은 모양으로 그림 -
        # 예전엔 탭 pane 쪽 테두리와 겹쳐서 선이 끊겨 보였음
        self.setObjectName("chatLog")
        self.setFrameShape(QFrame.Shape.NoFrame)
        # 둥근 모서리를 살리려면 viewport와 내용 위젯이 반드시 투명해야 함. 둘 중 하나라도
        # 불투명하면 사각형인 그 자식이 둥근 모서리 위에 덮여 그려져서 모서리가 잘려나간
        # 것처럼 보임(테두리가 끊긴 것처럼 보이던 원인). 배경색은 QScrollArea 자신이 그림
        # 선택자를 반드시 objectName으로 한정할 것. 위젯에 직접 준 스타일시트는 자식 위젯에도
        # 그대로 상속되므로, 그냥 "background: transparent"라고 쓰면 이 안에 들어가는
        # 링크 미리보기 카드 같은 것들의 배경/테두리까지 다 지워버림(실제로 그 증상이 났음)
        self.viewport().setObjectName("chatLogViewport")
        self.viewport().setAutoFillBackground(False)
        self.viewport().setStyleSheet(
            "QWidget#chatLogViewport { background: transparent; border: none; }")

        content = QWidget()
        content.setObjectName("chatLogContent")
        content.setAutoFillBackground(False)
        content.setStyleSheet("QWidget#chatLogContent { background: transparent; }")
        self._layout = QVBoxLayout(content)
        self._layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        # 둥근 모서리 안쪽으로 내용이 파고들지 않게 여백을 둠
        self._layout.setContentsMargins(8, 8, 8, 8)
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
                       kind: str = KIND_CHAT, preview: bool = True):
        widget = MessageWidget(sender, text, mine, ts, avatar_pixmap, kind=kind, preview=preview,
                               image_fetcher=self._image_fetcher)
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
    """채널 탭은 글자 수와 무관하게 항상 같은 크기, 맨 끝의 '+' 탭만 작은 정사각형."""

    def __init__(self, parent=None):
        super().__init__(parent)
        # 탭 아래를 가로지르는 기본 밑줄(base line)을 끄지 않으면 탭 위쪽으로 짧은 선분이
        # 삐져나오고, 아래로는 채팅 카드 테두리와 별개인 줄이 하나 더 그어져 지저분해짐
        self.setDrawBase(False)
        # 긴 채널명은 잘라내는 대신 말줄임(...)으로 - 그냥 잘리면 글자가 반쯤 남아 엉성함
        self.setElideMode(Qt.TextElideMode.ElideRight)
        self.setExpanding(False)
        self.setUsesScrollButtons(True)

    def tabSizeHint(self, index: int) -> QSize:
        if self.tabText(index) == ADD_TAB_LABEL:
            return QSize(ADD_TAB_WIDTH, CHANNEL_TAB_HEIGHT)
        return QSize(CHANNEL_TAB_FIXED_WIDTH, CHANNEL_TAB_HEIGHT)

    def minimumTabSizeHint(self, index: int) -> QSize:
        # 이걸 안 주면 탭이 많아졌을 때 Qt가 제멋대로 줄여서 크기가 들쭉날쭉해짐
        return self.tabSizeHint(index)
