"""앱 테마와 일치하는 프레임 없는 확인/경고/입력 팝업 (QMessageBox/QInputDialog 대체).

themed_question/themed_warning/themed_get_text는 테스트가 g.themed_question = fake처럼
직접 몽키패치하는 대상임 - 이 셋을 호출하는 다른 모듈(pages.py, profile_dialog.py,
main_window.py)은 호출하는 메서드 "본문 안에서" `import gui_client`를 한 뒤
`gui_client.themed_question(...)`처럼 모듈 속성으로 조회해서 호출해야 몽키패치가 실제로
먹힘. `from gui.themed_dialogs import themed_question`처럼 직접 바인딩하거나 파일 맨
위에서 `import gui_client`를 하면 안 됨(둘 다 PyInstaller 빌드에서 순환참조 크래시가
나거나 몽키패치가 무효화됨) - 자세한 이유는 gui_client.py 상단 주석 참고.
"""
from PySide6.QtCore import Qt, QSize
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

from gui.helpers import _titlebar_icon
from gui.theme import IS_WINDOWS


class _MiniTitleBar(QWidget):
    """확인/경고 팝업용 - 최소화/최대화 없이 제목과 닫기만 있는 얇은 타이틀바
    (QMessageBox 기본 창틀이 OS 기본 흰색이라 앱 테마와 안 맞아서 대체용으로 만듦)"""

    def __init__(self, dialog: QDialog, title: str, parent=None):
        super().__init__(parent)
        self._dialog = dialog
        self.setObjectName("titleBar")
        self.setFixedHeight(32)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 0, 0)
        layout.setSpacing(8)

        label = QLabel(title)
        label.setObjectName("titleBarText")
        layout.addWidget(label)
        layout.addStretch(1)

        close_btn = QPushButton()
        close_btn.setObjectName("titleBarCloseBtn")
        close_btn.setIcon(_titlebar_icon("close"))
        close_btn.setIconSize(QSize(10, 10))
        close_btn.setFixedSize(40, 32)
        close_btn.setCursor(Qt.CursorShape.ArrowCursor)
        close_btn.clicked.connect(dialog.reject)
        layout.addWidget(close_btn)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            handle = self._dialog.windowHandle()
            if handle is not None:
                handle.startSystemMove()
            event.accept()
            return
        super().mousePressEvent(event)


class ThemedDialog(QDialog):
    """QMessageBox.question()/warning() 대신 쓰는, 앱 테마와 일치하는 프레임 없는
    확인/경고 팝업. buttons는 (버튼 글자, 반환값) 목록 - 예: [("아니오", False), ("예", True)]"""

    def __init__(self, title: str, text: str, buttons: list[tuple[str, object]], default_value=None, parent=None):
        super().__init__(parent)
        self.result_value = default_value
        if IS_WINDOWS:
            self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(1, 1, 1, 1)
        outer.setSpacing(0)
        outer.addWidget(_MiniTitleBar(self, title))

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(16, 14, 16, 14)
        text_label = QLabel(text)
        text_label.setWordWrap(True)
        body_layout.addWidget(text_label)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        for label, value in buttons:
            btn = QPushButton(label)
            if value in (False, None):
                btn.setObjectName("secondary")
            btn.clicked.connect(lambda checked=False, v=value: self._finish(v))
            btn_row.addWidget(btn)
        body_layout.addLayout(btn_row)
        outer.addWidget(body)

        self.setMinimumWidth(340)

    def _finish(self, value):
        self.result_value = value
        self.accept()


def themed_question(parent, title: str, text: str) -> bool:
    dlg = ThemedDialog(title, text, [("아니오", False), ("예", True)], default_value=False, parent=parent)
    dlg.exec()
    return bool(dlg.result_value)


def themed_warning(parent, title: str, text: str):
    dlg = ThemedDialog(title, text, [("확인", None)], parent=parent)
    dlg.exec()


class ThemedInputDialog(QDialog):
    """QInputDialog.getText() 대신 쓰는, 앱 테마와 일치하는 프레임 없는 한 줄 입력창"""

    def __init__(self, title: str, label: str, echo_mode=QLineEdit.EchoMode.Normal, parent=None):
        super().__init__(parent)
        self.result_text = ""
        self.accepted_value = False
        if IS_WINDOWS:
            self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(1, 1, 1, 1)
        outer.setSpacing(0)
        outer.addWidget(_MiniTitleBar(self, title))

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(16, 14, 16, 14)
        label_widget = QLabel(label)
        label_widget.setWordWrap(True)
        body_layout.addWidget(label_widget)

        self._input = QLineEdit()
        self._input.setEchoMode(echo_mode)
        self._input.returnPressed.connect(self._on_ok)
        body_layout.addWidget(self._input)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        cancel_btn = QPushButton("취소")
        cancel_btn.setObjectName("secondary")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        ok_btn = QPushButton("확인")
        ok_btn.clicked.connect(self._on_ok)
        btn_row.addWidget(ok_btn)
        body_layout.addLayout(btn_row)
        outer.addWidget(body)

        self.setMinimumWidth(320)
        self._input.setFocus()

    def _on_ok(self):
        self.result_text = self._input.text()
        self.accepted_value = True
        self.accept()


def themed_get_text(parent, title: str, label: str, echo_mode=QLineEdit.EchoMode.Normal) -> tuple[str, bool]:
    dlg = ThemedInputDialog(title, label, echo_mode, parent=parent)
    dlg.exec()
    return dlg.result_text, dlg.accepted_value
