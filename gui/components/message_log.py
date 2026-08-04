"""채널 하나의 대화 목록 - 메시지 위젯을 세로로 쌓는 스크롤 영역.

여기서 가장 조심할 것은 **안쪽 위젯의 높이**다. 계산식(sizeHint/heightForWidth)이 실제
배치와 어긋나면 그 차이가 그대로 채팅 맨 아래 빈 공간이 되고, 심하면 맨 아래에서 메시지가
하나도 안 보인다. 자세한 사고 이력과 실측값은 _ChatLogContent 주석과 CLAUDE.md 참고.
"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QFrame, QLabel, QScrollArea, QVBoxLayout, QWidget

import error_log
from chat_core.commands import KIND_CHAT
from gui.components.message_item import MessageWidget, _build_system_label

# 맨 아래에서 이만큼 안쪽까지는 "맨 아래를 보고 있는 중"으로 친다(한 줄 남짓).
# 딱 맞아떨어질 때만 따라가게 하면 새 메시지가 오는 순간의 오차로 따라가기가 자꾸 끊긴다
STICK_TO_BOTTOM_SLACK_PX = 40



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

        # QTimer.singleShot(0, ...)로 "다음 틱에 맨 아래로" 하는 방식은 레이아웃이 새 위젯
        # 크기를 계산하기 전에 실행될 때가 있어 스크롤이 씹혔다. rangeChanged는 스크롤 범위가
        # 실제로 확정된 그 순간에 울리므로 안정적이다.
        self.verticalScrollBar().rangeChanged.connect(self._follow_bottom)
        # 사용자가 위쪽 지난 대화를 보고 있는 중이면 새 메시지가 와도 끌어내리지 않는다.
        # 스크롤을 움직일 때마다 "지금 맨 아래를 보고 있나"를 기억해둔다
        # 메시지를 넣는 도중에 스크롤 최대값을 물어보면 그 자체가 범위 갱신을 부르고,
        # 그게 다시 이 신호를 부르면서 스택이 넘쳤다(실측: 메시지 120건에서 죽음).
        # 그래서 **신호가 넘겨주는 값과 지금 위치만** 쓴다
        self._last_maximum = 0

    def _follow_bottom(self, minimum: int, maximum: int):
        """대화가 길어져 스크롤 범위가 늘어났을 때 따라 내려갈지 정한다.

        범위가 늘기 직전에 '예전 맨 아래'에 붙어 있었다면 사용자는 최신 대화를 보고 있던
        것이므로 따라간다. 위쪽 지난 대화를 읽고 있었다면 읽던 자리를 그대로 둔다.
        """
        bar = self.verticalScrollBar()
        was_at_bottom = bar.value() >= self._last_maximum - STICK_TO_BOTTOM_SLACK_PX
        self._last_maximum = maximum
        if was_at_bottom:
            bar.setValue(maximum)

    def _at_bottom(self) -> bool:
        bar = self.verticalScrollBar()
        return bar.value() >= bar.maximum() - STICK_TO_BOTTOM_SLACK_PX

    def scroll_to_bottom(self):
        """맨 아래로 내려감(채널을 새로 열 때 등)."""
        bar = self.verticalScrollBar()
        self._last_maximum = bar.maximum()
        bar.setValue(bar.maximum())

    def is_following_bottom(self) -> bool:
        """지금 최신 대화를 보고 있는가(= 새 메시지가 오면 따라 내려갈 상태인가)."""
        return self._at_bottom()

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
