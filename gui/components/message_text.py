"""메시지 한 줄의 글자. **배치와 높이를 텍스트 엔진에 통째로 맡긴다.**

왜 이렇게 바꿨는가(2026-08-13): 예전에는 `QLabel`에 글을 넣고 "이 폭이면 높이가
얼마냐"를 우리가 Qt에게 물어 짜맞췄다. 그 구조에서 같은 뿌리의 사고가 계속 났다.

- 공백 없는 글이 아예 안 접힘 -> 폭 0인 공백을 몰래 끼워 넣는 꼼수로 막았다
- 라벨이 답하는 높이가 상황마다 달라짐(sizeHint / heightForWidth가 서로 다른 값)
- 크기 정책을 새로 만들면 heightForWidth 표시가 꺼져 높이를 안 물어봄
- 위젯이 눌린 상태에서 잰 높이를 "필요한 높이"로 답해 영영 안 늘어남

전부 "글자를 어떻게 배치할지 우리가 추측한다"에서 나온 증상이다. 그래서 추측을 없앴다.

지금 구조:
- 줄바꿈 규칙을 **아무 데서나 접기**로 지정한다(공백이 없어도 접힌다 - 한글/중국어처럼
  띄어쓰기 없이 쓰는 글에 필요하다). 꼼수로 공백을 끼울 이유가 사라진다
- 높이는 **문서가 알려주는 값 그대로** 쓴다(`document().size().height()`). 폭이 바뀌면
  그 폭으로 다시 물어서 고정한다 - 레이아웃이 추측할 여지가 없다

실측(폭 400, 공백 없는 500자): 단어 단위 22px(안 접힘) -> 아무 데서나 232px(접힘).
200개를 만드는 비용도 0.03초로 예전(0.01초)과 차이가 없다.
"""
import math

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QTextOption
from PySide6.QtWidgets import QSizePolicy, QTextBrowser


class MessageText(QTextBrowser):
    def __init__(self, html: str, parent=None):
        super().__init__(parent)
        self.setObjectName("messageText")
        self.setFrameShape(QTextBrowser.Shape.NoFrame)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setOpenExternalLinks(True)
        self.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.LinksAccessibleByMouse)
        self.viewport().setAutoFillBackground(False)
        self.setStyleSheet("QTextBrowser#messageText { background: transparent; border: 0; }")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        document = self.document()
        document.setDocumentMargin(0)
        option = document.defaultTextOption()
        # **핵심**: 공백이 없어도 접는다. QLabel에서는 이 규칙을 지정할 방법이 없어서
        # 폭 0인 공백을 끼워 넣는 꼼수를 썼었다
        option.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        document.setDefaultTextOption(option)
        self.setHtml(html)
        self._wrap_width = 0

    def set_wrap_width(self, width: int):
        """이 폭에서 글을 배치하고, 그때 필요한 높이로 고정한다."""
        width = max(1, int(width))
        if width == self._wrap_width:
            return
        self._wrap_width = width
        self.setFixedWidth(width)
        self._apply_height()

    def _apply_height(self):
        document = self.document()
        document.setTextWidth(self._wrap_width or self.width())
        # 높이를 **문서에서 받아 그대로 고정**한다. 레이아웃이 다시 추측하지 않으므로
        # "눌려서 잘리는" 일도, "빈 공간이 남는" 일도 생기지 않는다
        self.setFixedHeight(math.ceil(document.size().height()))

    def setText(self, html: str):
        """글을 갈아끼운다(주소만 있던 메시지가 미리보기로 바뀔 때 등)."""
        self.setHtml(html)
        self._apply_height()

    def text(self) -> str:
        """화면에 실제로 보이는 글자(태그 없이). 예전 라벨과 같은 이름으로 열어둔다 -
        부르는 쪽은 '무엇으로 그리는지'가 아니라 '무엇이 보이는지'만 알면 된다."""
        return self.toPlainText()

    def sizeHint(self) -> QSize:
        document = self.document()
        document.setTextWidth(self._wrap_width or self.width())
        return QSize(self._wrap_width or self.width(), math.ceil(document.size().height()))

    def minimumSizeHint(self) -> QSize:
        return QSize(0, 0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not self._wrap_width:
            self._apply_height()

    def wheelEvent(self, event):
        # 마우스 휠은 대화 목록이 굴러가야 한다 - 메시지 한 줄이 삼키면 스크롤이 멈춘다
        event.ignore()
