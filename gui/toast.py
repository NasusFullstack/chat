"""새 메시지 알림 팝업 - 앱이 직접 그리는 창.

운영체제 기본 알림(QSystemTrayIcon.showMessage)을 쓰다가 이걸로 바꿨다. 기본 알림은
모양을 우리가 정할 수 없고, 윈도우 버전/설정에 따라 뜨는 위치와 지속 시간이 제각각이다.
카톡·라인처럼 "앱다운 알림"을 주려면 직접 그리는 편이 낫다.

지켜야 할 성질 세 가지:
- **포커스를 뺏지 않는다.** 알림이 뜰 때 쓰던 창이 뒤로 밀리면 최악이다
  (WA_ShowWithoutActivating + Qt.Tool).
- **작업표시줄에 안 나온다.** 알림은 창 목록에 낄 물건이 아니다(Qt.Tool).
- **여러 개 쌓지 않는다.** 하나만 두고 내용을 갈아끼운다 - 연달아 오는 대화에서 팝업이
  화면을 덮어버리지 않게. 묶는 일 자체는 TrayIcon이 하고 여기는 보여주기만 한다.
"""
from PySide6.QtCore import QPropertyAnimation, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from gui.styles.palette import colors

TOAST_WIDTH = 380
SCREEN_MARGIN = 8        # 화면 가장자리에서 띄울 간격(작업표시줄 영역은 이미 피해 있음)
SHOW_MS = 5000           # 이만큼 보여준 뒤 서서히 사라짐
FADE_MS = 350
ICON_PX = 44
CLOSE_PX = 16            # 닫기 버튼 - 내용을 가리지 않게 작게
CLOSE_MARK_PX = 4        # X 자의 팔 길이


class ToastPopup(QWidget):
    """오른쪽 아래에 잠깐 떠 있다 사라지는 알림. 누르면 clicked."""

    clicked = Signal()

    def __init__(self, icon=None, parent=None):
        super().__init__(parent)
        self.setObjectName("toast")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint       # 제목표시줄 없음
            | Qt.WindowType.WindowStaysOnTopHint    # 다른 창 위에
            | Qt.WindowType.Tool                    # 작업표시줄에 안 나옴
        )
        # 뜰 때 지금 쓰던 창에서 포커스를 뺏지 않게 함(이게 없으면 타이핑이 끊긴다)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setFixedWidth(TOAST_WIDTH)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        row = QHBoxLayout(self)
        row.setContentsMargins(16, 14, 12, 14)
        row.setSpacing(10)

        self.icon_label = QLabel()
        self.icon_label.setObjectName("toastIcon")
        self.icon_label.setFixedSize(ICON_PX, ICON_PX)
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if icon is not None and not icon.isNull():
            self.icon_label.setPixmap(icon.pixmap(ICON_PX, ICON_PX))
        row.addWidget(self.icon_label, 0, Qt.AlignmentFlag.AlignTop)

        column = QVBoxLayout()
        column.setSpacing(2)
        self.title_label = QLabel()
        self.title_label.setObjectName("toastTitle")
        column.addWidget(self.title_label)
        self.body_label = QLabel()
        self.body_label.setObjectName("toastBody")
        self.body_label.setWordWrap(True)
        column.addWidget(self.body_label)
        row.addLayout(column, 1)

        # 닫기 버튼. 알림은 5초 뒤 저절로 사라지지만, 지금 당장 치우고 싶을 때가 있다.
        # 글자 X 대신 선으로 그리는 이유는 손잡이(sidebar_handle.py)와 같다 - 글꼴에 따라
        # 크기와 정렬이 달라지지 않게. 색은 테마의 옅은 회색이라 디자인을 해치지 않는다
        self.close_btn = _CloseMark()
        self.close_btn.clicked.connect(self._dismiss)
        row.addWidget(self.close_btn, 0, Qt.AlignmentFlag.AlignTop)

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.fade_out)

        self._fade = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade.setDuration(FADE_MS)
        self._fade.finished.connect(self._on_fade_done)
        self._fading_out = False

    # ---------------- 보여주기 ----------------

    def show_message(self, title: str, body: str):
        """내용을 갈아끼우고 오른쪽 아래에 띄움. 이미 떠 있으면 시간만 다시 잰다."""
        self.title_label.setText(title)
        self.body_label.setText(body)
        self.adjustSize()
        self.setFixedWidth(TOAST_WIDTH)
        self._move_to_corner()

        self._fading_out = False
        self._fade.stop()
        self.setWindowOpacity(1.0)
        self.show()
        self.raise_()
        self._hide_timer.start(SHOW_MS)

    def _move_to_corner(self):
        """화면 오른쪽 아래. 작업표시줄을 침범하지 않는 영역(availableGeometry)을 쓴다."""
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        self.move(area.right() - self.width() - SCREEN_MARGIN,
                  area.bottom() - self.height() - SCREEN_MARGIN)

    def fade_out(self):
        if not self.isVisible():
            return
        self._fading_out = True
        self._fade.stop()
        self._fade.setStartValue(self.windowOpacity())
        self._fade.setEndValue(0.0)
        self._fade.start()

    def _on_fade_done(self):
        if self._fading_out:
            self.hide()
            self.setWindowOpacity(1.0)
            self._fading_out = False

    def _dismiss(self):
        """닫기 버튼 - 창을 열지 않고 알림만 치운다(clicked를 내보내지 않는 이유)."""
        self._hide_timer.stop()
        self._fade.stop()
        self.hide()
        self.setWindowOpacity(1.0)
        self._fading_out = False

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._hide_timer.stop()
            self.hide()
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def set_icon(self, icon):
        if icon is not None and not icon.isNull():
            self.icon_label.setPixmap(icon.pixmap(ICON_PX, ICON_PX))


class _CloseMark(QWidget):
    """옅은 회색 X. 마우스를 올리면 또렷해진다."""

    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(CLOSE_PX, CLOSE_PX)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("알림 닫기")
        self._hover = False

    def enterEvent(self, event):
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.pos()):
            self.clicked.emit()
        # 부모(알림 전체)의 클릭은 '창 열기'라서, 닫기를 눌렀을 때 창까지 열리면 안 된다
        event.accept()

    def paintEvent(self, _event):
        theme = colors()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if self._hover:
            # 눌러도 되는 자리라는 걸 알려주는 옅은 동그라미(평소엔 X만 보임)
            circle = QPainterPath()
            circle.addEllipse(QRectF(self.rect()))
            painter.fillPath(circle, QColor(theme["BG_ITEM_HOVER"]))
        pen = QPen(QColor(theme["TEXT_SOFT" if self._hover else "TEXT_FAINT"]), 1.4)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        cx, cy, arm = self.width() / 2, self.height() / 2, CLOSE_MARK_PX / 2 * 1.6
        painter.drawLine(int(cx - arm), int(cy - arm), int(cx + arm), int(cy + arm))
        painter.drawLine(int(cx + arm), int(cy - arm), int(cx - arm), int(cy + arm))
