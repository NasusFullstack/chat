"""환경설정 창 - 트레이 아이콘 메뉴에서 연다.

지금 담는 것은 알림(표시 여부·내용 숨김) / 닫기 동작 / 테마다. 앱 전체 설정이 늘어나면 여기에 줄을 추가한다.
로그인 정보는 여기서 다루지 않는다 - 그건 로그인 화면 소관이고 저장 파일도 따로다.
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFrame, QHBoxLayout, QLabel,
                               QPushButton, QVBoxLayout, QWidget)

import app_prefs
from gui.styles.palette import DEFAULT_THEME, theme_choices
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

        self.preview_check = QCheckBox("알림에 보낸 사람과 내용 표시")
        self.preview_check.setChecked(prefs["notify_preview"])
        self.preview_check.setEnabled(prefs["notifications"])
        # 알림 자체를 끄면 이 설정은 의미가 없으므로 같이 잠근다
        self.notify_check.toggled.connect(self.preview_check.setEnabled)
        body.addWidget(self.preview_check)
        preview_hint = QLabel("끄면 \"새 메시지가 도착했습니다\"만 뜹니다. "
                              "남이 화면을 볼 수 있는 자리에서 대화 내용이 노출되지 않습니다.")
        preview_hint.setObjectName("hint")
        preview_hint.setWordWrap(True)
        body.addWidget(preview_hint)

        self.tray_check = QCheckBox("창을 닫아도 종료하지 않고 트레이에 두기")
        self.tray_check.setChecked(prefs["close_to_tray"])
        body.addWidget(self.tray_check)
        tray_hint = QLabel("끄면 창을 닫을 때 프로그램이 완전히 종료됩니다. "
                           "켜두면 작업표시줄 오른쪽 아이콘에서 '종료'를 눌러야 끝납니다.")
        tray_hint.setObjectName("hint")
        tray_hint.setWordWrap(True)
        body.addWidget(tray_hint)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setObjectName("settingsDivider")
        body.addWidget(line)

        theme_row = QHBoxLayout()
        theme_row.addWidget(QLabel("테마"))
        self.theme_box = QComboBox()
        for key, label in theme_choices():
            self.theme_box.addItem(label, key)
        saved_theme = prefs.get("theme", DEFAULT_THEME)
        index = self.theme_box.findData(saved_theme)
        self.theme_box.setCurrentIndex(index if index >= 0 else 0)
        theme_row.addWidget(self.theme_box, 1)
        body.addLayout(theme_row)
        theme_hint = QLabel("지금은 기본 테마 하나입니다. 색 구성은 이미 테마 단위로 묶여 "
                            "있어서, 다음 버전에서 테마가 추가되면 여기서 바로 고를 수 있습니다.")
        theme_hint.setObjectName("hint")
        theme_hint.setWordWrap(True)
        body.addWidget(theme_hint)

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
        prefs = app_prefs.load()
        prefs.update({
            "notifications": self.notify_check.isChecked(),
            "notify_preview": self.preview_check.isChecked(),
            "close_to_tray": self.tray_check.isChecked(),
            "theme": self.theme_box.currentData(),
        })
        # 접힘 상태처럼 이 창에서 안 다루는 설정은 그대로 둬야 함(load 후 갱신하는 이유)
        app_prefs.save(prefs)
        self.accept()
