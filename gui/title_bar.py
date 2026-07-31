"""OS 기본 타이틀바 대신 쓰는 커스텀 타이틀바."""
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QHBoxLayout, QLabel, QMainWindow, QPushButton, QWidget

from gui.helpers import _titlebar_icon
from gui.theme import APP_TITLE


class TitleBar(QWidget):
    """OS 기본 타이틀바 대신 쓰는 커스텀 타이틀바 - 프로그램 아이콘/이름과
    테마에 맞춘 최소화/최대화/닫기 버튼을 보여줌. 드래그 이동/더블클릭 최대화는
    QWindow.startSystemMove()로 OS의 네이티브 이동 루프를 그대로 넘겨받아 처리하므로
    에어로 스냅 등 기본 동작이 자연히 따라옴. 버튼 위 클릭은 자식 위젯(버튼)이 먼저
    가로채므로 이 위젯의 mousePressEvent까지 안 내려와 별도 예외 처리가 필요 없음"""

    TITLEBAR_HEIGHT = 36

    def __init__(self, window: QMainWindow, parent=None):
        super().__init__(parent)
        self._window = window
        self.setObjectName("titleBar")
        self.setFixedHeight(self.TITLEBAR_HEIGHT)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 0, 0)
        layout.setSpacing(8)

        self.icon_label = QLabel()
        self.icon_label.setFixedSize(18, 18)
        self.icon_label.setScaledContents(True)
        layout.addWidget(self.icon_label)

        self.title_label = QLabel(APP_TITLE)
        self.title_label.setObjectName("titleBarText")
        layout.addWidget(self.title_label)

        layout.addStretch(1)

        self.min_btn = self._make_button("titleBarMinBtn", _titlebar_icon("minimize"), "최소화")
        self.min_btn.clicked.connect(window.showMinimized)
        layout.addWidget(self.min_btn)

        self.max_btn = self._make_button("titleBarMaxBtn", _titlebar_icon("maximize"), "최대화")
        self.max_btn.clicked.connect(self._toggle_maximize)
        layout.addWidget(self.max_btn)

        self.close_btn = self._make_button("titleBarCloseBtn", _titlebar_icon("close"), "닫기")
        self.close_btn.clicked.connect(window.close)
        layout.addWidget(self.close_btn)

    def _make_button(self, object_name: str, icon: QIcon, tooltip: str) -> QPushButton:
        btn = QPushButton()
        btn.setObjectName(object_name)
        btn.setIcon(icon)
        btn.setIconSize(QSize(10, 10))
        btn.setFixedSize(44, self.TITLEBAR_HEIGHT)
        btn.setToolTip(tooltip)
        btn.setCursor(Qt.CursorShape.ArrowCursor)
        return btn

    def set_icon(self, icon: QIcon):
        self.icon_label.setPixmap(icon.pixmap(18, 18))

    def set_maximized(self, is_maximized: bool):
        self.max_btn.setIcon(_titlebar_icon("restore" if is_maximized else "maximize"))
        self.max_btn.setToolTip("이전 크기로" if is_maximized else "최대화")

    def _toggle_maximize(self):
        if self._window.isMaximized():
            self._window.showNormal()
        else:
            self._window.showMaximized()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            handle = self._window.windowHandle()
            if handle is not None:
                handle.startSystemMove()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._toggle_maximize()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)
