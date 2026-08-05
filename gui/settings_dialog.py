"""환경설정 창 - 트레이 아이콘 메뉴에서 연다.

지금 담는 것은 두 가지뿐이다(알림, 닫기 동작). 앱 전체 설정이 늘어나면 여기에 줄을 추가한다.
로그인 정보는 여기서 다루지 않는다 - 그건 로그인 화면 소관이고 저장 파일도 따로다.
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QDialog, QHBoxLayout, QLabel, QPushButton,
                               QVBoxLayout, QWidget)

import app_prefs
from gui.theme import IS_WINDOWS
from gui.themed_dialogs import _MiniTitleBar


class SettingsDialog(QDialog):
    """확인을 누르면 그때 저장한다(취소하면 아무 것도 안 바뀜)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        if IS_WINDOWS:
            self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        prefs = app_prefs.load()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(1, 1, 1, 1)
        outer.setSpacing(0)
        outer.addWidget(_MiniTitleBar(self, "환경설정"))

        host = QWidget()
        body = QVBoxLayout(host)
        body.setContentsMargins(18, 16, 18, 14)
        body.setSpacing(10)

        self.notify_check = QCheckBox("새 메시지 알림 표시")
        self.notify_check.setChecked(prefs["notifications"])
        body.addWidget(self.notify_check)
        hint = QLabel("창을 보고 있지 않을 때만 오른쪽 아래에 뜹니다.")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        body.addWidget(hint)

        self.tray_check = QCheckBox("창을 닫아도 종료하지 않고 트레이에 두기")
        self.tray_check.setChecked(prefs["close_to_tray"])
        body.addWidget(self.tray_check)
        tray_hint = QLabel("끄면 창을 닫을 때 프로그램이 완전히 종료됩니다. "
                           "켜두면 작업표시줄 오른쪽 아이콘에서 '종료'를 눌러야 끝납니다.")
        tray_hint.setObjectName("hint")
        tray_hint.setWordWrap(True)
        body.addWidget(tray_hint)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("취소")
        cancel.setObjectName("secondary")
        cancel.clicked.connect(self.reject)
        confirm = QPushButton("확인")
        confirm.clicked.connect(self._save)
        buttons.addWidget(cancel)
        buttons.addWidget(confirm)
        body.addLayout(buttons)

        outer.addWidget(host)
        self.setMinimumWidth(380)

    def _save(self):
        app_prefs.save({
            "notifications": self.notify_check.isChecked(),
            "close_to_tray": self.tray_check.isChecked(),
        })
        self.accept()
