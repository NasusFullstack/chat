"""메시지 입력줄 - 이모티콘 버튼 + 입력창 + 전송 버튼, 그리고 자동완성.

`@닉네임`과 `/명령` 자동완성이 여기 함께 있는 이유: 둘 다 "입력창에 지금 치고 있는 토큰"을
보고 판단하는 일이라, 입력창과 떨어뜨려 두면 서로의 상태(커서 위치, 팝업이 떠 있는지)를
계속 주고받아야 한다.

이 컴포넌트는 후보를 **직접 만들지 않는다.** 참여자 목록도 명령 목록도 모르기 때문에,
후보를 돌려주는 함수를 바깥에서 받아 쓴다(candidate_source). 그래서 채널이 바뀌든
참여자가 들락거리든 이 파일은 손댈 일이 없다.

바깥으로 나가는 신호:
  submitted(글자)   Enter 또는 전송 버튼
"""
from PySide6.QtCore import QSize, QStringListModel, Qt, Signal
from PySide6.QtWidgets import QCompleter, QHBoxLayout, QLineEdit, QPushButton, QWidget

from chat_core.commands import COMMAND_PREFIX, format_emoji
from gui.helpers import _smiley_icon

# 입력창과 같은 높이의 정사각형 버튼. 글자 버튼("이모티콘")은 폭을 많이 먹고 높이도 안 맞았음
EMOJI_BTN_PX = 34
EMOJI_BTN_ICON_PX = 20

MENTION_PREFIX = "@"


class MessageInput(QWidget):
    """한 줄 입력 + 이모티콘 버튼 + 전송 버튼."""

    submitted = Signal(str)
    emoji_requested = Signal()

    def __init__(self, candidate_source, parent=None):
        """candidate_source(트리거문자) -> 후보 목록. 트리거는 '@' 또는 '/'."""
        super().__init__(parent)
        self._candidate_source = candidate_source
        self._completion_start = -1

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)

        self.emoji_btn = QPushButton()
        self.emoji_btn.setObjectName("emojiBtn")
        self.emoji_btn.setIcon(_smiley_icon(EMOJI_BTN_ICON_PX))
        self.emoji_btn.setIconSize(QSize(EMOJI_BTN_ICON_PX, EMOJI_BTN_ICON_PX))
        self.emoji_btn.setFixedSize(EMOJI_BTN_PX, EMOJI_BTN_PX)
        self.emoji_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.emoji_btn.setToolTip("이모티콘")
        self.emoji_btn.clicked.connect(self.emoji_requested.emit)
        row.addWidget(self.emoji_btn)

        self.line = QLineEdit()
        self.line.setFixedHeight(EMOJI_BTN_PX)
        self.line.setPlaceholderText("메시지 입력 후 Enter (@닉네임으로 호출 가능)")
        self.line.returnPressed.connect(self.submit)
        row.addWidget(self.line)

        self.send_btn = QPushButton("전송")
        self.send_btn.clicked.connect(self.submit)
        row.addWidget(self.send_btn)

        # QCompleter는 원래 "위젯 전체 텍스트"를 접두사로 보기 때문에 문장 중간의 @토큰에는
        # 그대로 쓸 수 없다. 지금 입력 중인 토큰만 setCompletionPrefix()로 직접 넘기고
        # complete()로 팝업을 띄우는 방식으로 쓴다.
        # 한글도 일반 접두사 매칭은 그대로 동작함("몽"->"몽키"). 못 하는 건 초성 검색뿐.
        self._model = QStringListModel([], self)
        self._completer = QCompleter(self._model, self)
        self._completer.setWidget(self.line)
        self._completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self._completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._completer.setFilterMode(Qt.MatchFlag.MatchStartsWith)
        self._completer.activated.connect(self._insert_completion)
        self.line.textEdited.connect(self._update_completer)

    # ---------------- 입력 ----------------

    def text(self) -> str:
        return self.line.text()

    def set_text(self, text: str):
        self.line.setText(text)
        self.line.setCursorPosition(len(text))

    def clear(self):
        self.line.clear()

    def set_enabled(self, enabled: bool):
        self.line.setEnabled(enabled)

    def focus(self):
        self.line.setFocus()

    def insert_emoji(self, url: str):
        """고른 이모티콘을 '표시로 감싼 주소'로 넣음(주소 글자는 대화에 안 보임)."""
        if not url:
            return
        text = self.line.text()
        if text and not text.endswith(" "):
            text += " "
        self.set_text(text + format_emoji(url))

    def submit(self):
        """Enter/전송. 자동완성 팝업이 떠 있으면 그 Enter는 '후보 선택'이지 '전송'이 아니다.

        이 가드가 없으면 Enter 한 번에 후보 선택과 전송이 같이 일어나서 완성 전 상태의
        글자("@Mo")가 그대로 나간다(실제 키 이벤트 테스트로 발견한 버그).
        """
        if self._completer.popup().isVisible():
            return
        text = self.line.text().strip()
        if not text:
            return
        self.submitted.emit(text)

    # ---------------- 자동완성 ----------------

    def completion_token(self) -> tuple[int, str] | None:
        """커서 바로 앞에서 입력 중인 토큰이 자동완성 대상이면 (시작위치, 토큰).

        - '@'는 문장 어디서든(앞이 공백이거나 맨 앞일 때만 - 이메일 주소 오인 방지)
        - '/'는 맨 앞에서만(명령은 줄 맨 앞에만 올 수 있음)
        - 토큰 안에 공백이 들어가면 더 이상 완성 대상이 아님
        """
        text = self.line.text()
        head = text[:self.line.cursorPosition()]
        for trigger in (MENTION_PREFIX, COMMAND_PREFIX):
            start = head.rfind(trigger)
            if start < 0:
                continue
            token = head[start:]
            if " " in token:
                continue
            if trigger == COMMAND_PREFIX and start != 0:
                continue
            if trigger == MENTION_PREFIX and start > 0 and not head[start - 1].isspace():
                continue
            return start, token
        return None

    def _update_completer(self, _text: str = ""):
        found = self.completion_token()
        if found is None:
            self._hide_popup()
            return
        start, token = found
        candidates = self._candidate_source(token[0])
        if not candidates:
            self._hide_popup()
            return
        self._completion_start = start
        # 후보 목록을 매번 새로 세팅해야 참여자가 들어오고 나간 게 바로 반영됨
        self._model.setStringList(candidates)
        self._completer.setCompletionPrefix(token)
        if self._completer.completionCount() == 0:
            self._hide_popup()
            return
        popup = self._completer.popup()
        popup.setCurrentIndex(self._completer.completionModel().index(0, 0))
        self._completer.complete()

    def _hide_popup(self):
        self._completion_start = -1
        self._completer.popup().hide()

    def _insert_completion(self, chosen: str):
        """팝업에서 고른 항목으로 입력 중이던 토큰을 교체하고 뒤에 공백 하나를 붙임"""
        if self._completion_start < 0:
            return
        text = self.line.text()
        cursor = self.line.cursorPosition()
        new_text = text[:self._completion_start] + chosen + " " + text[cursor:]
        self.line.setText(new_text)
        self.line.setCursorPosition(self._completion_start + len(chosen) + 1)
        self._completion_start = -1

    def popup_visible(self) -> bool:
        return self._completer.popup().isVisible()
