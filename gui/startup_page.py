"""앱을 켰을 때 가장 먼저 보이는 시작 화면 - 큰 로고 + 진행 상태.

예전에는 로그인 화면이 먼저 뜨고 그 위에 업데이트 진행 모달이 따로 튀어나오는 구조라
흐름이 어색했음(사용자 입장에선 "로그인하라며?" 하다가 갑자기 창이 덮임). 지금은
   시작화면(로고) -> 업데이트 확인/적용 -> 로그인
순서로 한 화면 안에서 자연스럽게 이어지고, 업데이트 진행 상황도 이 화면에 표시함.
"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QLabel, QProgressBar, QVBoxLayout, QWidget

from gui.helpers import _find_logo_image
from gui.theme import APP_TITLE
from version import APP_VERSION

LOGO_PX = 200


class StartupPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(14)

        self.logo_label = QLabel()
        self.logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_path = _find_logo_image()
        if icon_path:
            pixmap = QPixmap(icon_path)
            if not pixmap.isNull():
                # 1024px 원본이라 부드럽게 줄여야 깔끔함(픽셀아트 아바타와 달리 여긴 SmoothTransformation)
                self.logo_label.setPixmap(pixmap.scaled(
                    LOGO_PX, LOGO_PX,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                ))
        layout.addWidget(self.logo_label)

        self.name_label = QLabel(APP_TITLE)
        self.name_label.setObjectName("startupTitle")
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.name_label)

        self.version_label = QLabel(f"v{APP_VERSION}")
        self.version_label.setObjectName("hint")
        self.version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.version_label)

        self.status_label = QLabel("시작하는 중...")
        self.status_label.setObjectName("hint")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)

        # 업데이트를 실제로 받을 때만 보여줌(평소엔 숨김 - 빈 막대가 떠 있으면 지저분함)
        self.progress = QProgressBar()
        self.progress.setFixedWidth(260)
        self.progress.setTextVisible(False)
        self.progress.setVisible(False)
        layout.addWidget(self.progress, alignment=Qt.AlignmentFlag.AlignCenter)

    def set_status(self, text: str):
        self.status_label.setText(text)

    def show_progress(self, percent: int):
        self.progress.setVisible(True)
        self.progress.setValue(max(0, min(100, percent)))

    def hide_progress(self):
        self.progress.setVisible(False)
