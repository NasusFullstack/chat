"""채팅 메시지/로그 위젯 (MessageWidget / ChannelLogView).

이름들은 몽키패치 대상이 아니라 어디서든 자유롭게 직접 import해도 안전함
(gui_client.py의 순환참조 노트 참고 - 그 규칙은 다른 5개 함수에만 적용됨).
"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

import error_log
from chat_core.commands import KIND_ACTION, KIND_CHAT, KIND_NOTICE
from gui.helpers import _format_ts, _linkify, extract_urls, text_is_only_urls
from gui.theme import AVATAR_MSG_PX, TIMESTAMP_BADGE_HEIGHT_PX


# 폭 계산에 두는 여유. 스크롤바가 나타나는 순간 viewport가 그만큼 좁아지는데, 그 폭을
# 미리 빼두지 않으면 "넘침 -> 스크롤바 등장 -> 더 좁아져서 또 넘침"이 반복됨
_WRAP_SAFETY_PX = 4


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

        라벨을 통째로 숨기지 않는 이유: 누가 보낸 건지는 남아야 하기 때문.
        글자가 줄어들면 높이도 줄어드는데, 그걸 레이아웃에 알리지 않으면 예전 높이가
        그대로 남아 아래에 빈 공간이 생긴다."""
        self._text_label.setText(self._sender_only_html)
        self._text_label.updateGeometry()
        self.updateGeometry()

    def set_wrap_width(self, view_width: int):
        """네트워크로 비동기로 도착한 메시지는 QScrollArea 레이아웃이 아직 완전히
        안정되기 전에 위젯이 추가될 때가 있어, word-wrap 라벨의 자동 heightForWidth
        계산이 화면 폭을 반영 못 하고 줄바꿈이 안 풀린 채로 굳어버리는 경우가 있었음
        (내가 직접 보낸 메시지는 항상 창이 안정된 상태에서 추가돼서 이 문제가 안 드러남).
        Qt의 자동 계산에 기대는 대신 뷰포트 폭을 직접 계산해서 넘겨주면 타이밍과
        무관하게 항상 정확히 줄바꿈됨."""
        # 빼야 할 폭을 상수로 어림잡지 말고 실제 레이아웃 값에서 계산할 것.
        # 예전엔 24로 어림했는데 실제 여백/간격 합과 안 맞아서, 좁은 창에서 그림이
        # 10px쯤 삐져나가 가로 스크롤이 생기고 오른쪽이 잘려 보였음
        row = self.layout()
        margins = row.contentsMargins()
        overhead = (AVATAR_MSG_PX + margins.left() + margins.right() + row.spacing()
                    + _WRAP_SAFETY_PX)
        inner_width = max(40, view_width - overhead)
        self._text_label.setMaximumWidth(inner_width)
        # 미리보기 그림/카드도 같은 폭 안에 들어와야 함. 안 그러면 채팅창이 좁을 때
        # 그림이 밖으로 삐져나가 가로 스크롤이 생기고 시간 배지까지 화면 밖으로 밀림
        if self.preview_area is not None:
            self.preview_area.set_max_width(inner_width)


def _build_system_label(text: str) -> QLabel:
    label = QLabel(f'<span style="color:#9a9cad"><i>* {text}</i></span>')
    label.setObjectName("systemNotice")
    label.setStyleSheet("QLabel#systemNotice { background: transparent; }")
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    label.setWordWrap(True)
    return label


class _ChatLogContent(QWidget):
    """메시지들이 담기는 안쪽 위젯. 높이를 '폭에 따라' 계산해야 한다.

    QScrollArea(widgetResizable)는 기본적으로 폭과 무관한 sizeHint로 안쪽 위젯 높이를
    잡는다. 그런데 말풍선 글자는 폭에 따라 줄 수가 달라지므로(word wrap), 그 sizeHint는
    실제로 필요한 높이와 어긋난다. 어긋난 만큼이 그대로 **채팅 맨 아래 빈 공간**으로 남는다
    (실측: 창 폭 880에서 76px, 700으로 좁히면 778px). 새 메시지가 오면 잠깐 맞았다가
    창 크기를 만지면 다시 벌어져서 "됐다 안 됐다" 하는 것처럼 보였다.

    기본 QWidget.sizeHint()는 레이아웃의 totalSizeHint()를 쓰는데, 그 값은 '말풍선이
    한 줄로 다 들어가는 넓은 폭'을 가정하고 계산돼서 지금 폭에서 실제로 필요한 높이와
    다르다. 반면 레이아웃의 sizeHint()는 (말풍선 라벨에 최대폭을 이미 지정해두므로)
    지금 폭 기준 값이라 실측과 정확히 일치했다. 그래서 그 값을 그대로 쓴다.
    """

    def sizeHint(self):
        layout = self.layout()
        if layout is None:
            return super().sizeHint()
        return layout.sizeHint()

    def measured_height(self) -> int:
        """지금 실제로 배치된 마지막 위젯의 아랫끝(= 정말로 필요한 높이).

        계산식(sizeHint / heightForWidth)은 상황에 따라 실제 배치와 어긋난다. 실측으로는
        둘 다 틀리는 경우를 봤다 - 대화가 200건 쌓인 화면에서는 heightForWidth가 1152px
        크게 나오고, 로그인 후 채널에 들어가며 화면이 나타난 경우에는 sizeHint가 864px
        크게 나왔다. 어긋난 만큼은 그대로 채팅 맨 아래 빈 공간이 되어, 맨 아래로 내리면
        메시지가 하나도 안 보이는 상태가 된다.

        그래서 예측값 대신 '위젯들이 실제로 놓인 자리'를 쓴다. activate()로 배치를 먼저
        확정시키므로 방금 추가된 메시지도 포함된다.
        """
        layout = self.layout()
        if layout is None:
            return 0
        layout.activate()
        bottom = 0
        for i in range(layout.count()):
            item = layout.itemAt(i).widget()
            if item is not None and not item.isHidden():
                bottom = max(bottom, item.geometry().bottom() + 1)
        return bottom + layout.contentsMargins().bottom() if bottom else 0

    def heightForWidth(self, width: int) -> int:
        """QScrollArea(widgetResizable)가 안쪽 위젯 높이를 정할 때 실제로 보는 값."""
        layout = self.layout()
        if layout is None:
            return super().heightForWidth(width)
        if width == self.width():
            # 지금 폭 그대로면 실측이 가장 정확하다(계산식은 양쪽으로 다 틀릴 수 있음)
            measured = self.measured_height()
            if measured > 0:
                return measured
        height = layout.heightForWidth(width)
        if height <= 0:
            return layout.sizeHint().height()
        return height


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

        content = _ChatLogContent()
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
        # "빈 화면" 진단을 채널당 한 번만 남기기 위한 표시(로그가 불어나지 않게)
        self._blank_reported = False
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
        """메시지 하나가 쓸 수 있는 폭 - 이 스크롤 영역의 좌우 여백을 뺀 값.

        여백을 안 빼면 메시지가 딱 그 여백만큼 넘쳐서 가로 스크롤이 생긴다.
        기준 폭은 탭바 쪽에서 밀어준 값을 쓰되(숨은 탭은 자기 viewport 폭이 부정확함),
        실제로 보이는 상태라면 viewport를 넘지 않게 한 번 더 눌러준다.
        """
        base = self._container_width or self.viewport().width()
        visible = self.viewport().width()
        if visible > 0:
            base = min(base, visible)
        margins = self._layout.contentsMargins()
        return max(40, base - margins.left() - margins.right())

    def append_message(self, sender: str, text: str, mine: bool, ts: float, avatar_pixmap: QPixmap,
                       kind: str = KIND_CHAT, preview: bool = True):
        widget = MessageWidget(sender, text, mine, ts, avatar_pixmap, kind=kind, preview=preview,
                               image_fetcher=self._image_fetcher)
        widget.set_wrap_width(self._effective_width())
        self._layout.addWidget(widget)
        self._messages.append(widget)
        self.sync_content_height()
        self._warn_if_blank()

    def append_system(self, text: str):
        self._layout.addWidget(_build_system_label(text))
        self.sync_content_height()

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
        self.sync_content_height()

    def sync_content_height(self):
        """안쪽 위젯 높이를 지금 필요한 높이로 맞춘다.

        말풍선 글자는 폭에 따라 줄 수가 달라지는데(word wrap), 폭이 바뀌어 줄 수가 바뀌어도
        QScrollArea가 안쪽 위젯 높이를 다시 잡아주지 않는 경우가 있다. 그러면 예전 높이가
        그대로 남아 **채팅 맨 아래에 빈 공간**이 생긴다(실측: 창 폭 880에서 57px,
        700으로 좁히면 837px). 대화가 길수록 어긋남도 커지고, 새 메시지가 오면 잠깐
        맞았다가 창을 만지면 다시 벌어져서 "됐다 안 됐다" 하는 것처럼 보였다.
        """
        content = self.widget()
        if content is None:
            return
        layout = content.layout()
        if layout is None:
            return
        # 실제로 배치된 높이로 맞춘다. 내용이 화면보다 짧으면 배경이 끊겨 보이지 않게
        # 화면 높이만큼은 채운다
        measured = content.measured_height() if hasattr(content, "measured_height") else 0
        needed = max(measured or content.sizeHint().height(), self.viewport().height())
        if content.height() != needed:
            content.resize(content.width(), needed)

    def _warn_if_blank(self):
        """메시지가 있는데 화면에는 하나도 안 보이는 상태를 발견하면 기록해둔다.

        "채팅이 다 사라지고 빈 공간만 보인다"는 증상이 재현이 안 돼서 오래 못 잡았다.
        원인 두 가지(높이 계산 어긋남, 참여자 목록 비워짐)는 고쳤지만 "휠을 올려도
        아무것도 없었다"는 제보는 그것만으로 설명되지 않는다. 다시 벌어지면 그때의
        숫자라도 남도록 해둔다. 화면당 한 번만 기록해서 로그가 불어나지 않게 한다.
        """
        if self._blank_reported or not self._messages:
            return
        bar = self.verticalScrollBar()
        if bar.value() < bar.maximum() - 4:
            return  # 사용자가 위쪽을 보고 있는 중 - 안 보이는 게 정상
        top = bar.value()
        bottom = top + self.viewport().height()
        for message in self._messages:
            box = message.geometry()
            if box.bottom() > top and box.top() < bottom:
                return
        self._blank_reported = True
        content = self.widget()
        last = self._messages[-1].geometry()
        error_log.log_text(
            f"채널 {self.channel_name}: 메시지 {len(self._messages)}개가 있는데 화면에는"
            f" 하나도 안 보임\n"
            f"  스크롤 {bar.value()}/{bar.maximum()} 보이는높이 {self.viewport().height()}\n"
            f"  내용위젯 {content.width()}x{content.height()}"
            f" (실측필요높이 {getattr(content, 'measured_height', lambda: -1)()})\n"
            f"  마지막 메시지 위치 {last.top()}~{last.bottom()} 폭 {last.width()}\n"
            f"  기준폭 {self._container_width} 뷰포트폭 {self.viewport().width()}",
            tag="빈 화면",
        )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # 사용자가 실제로 창 크기를 바꿀 때는 지금 보이는 탭 기준 실측값으로 보정
        self.refresh_wrap_widths()
