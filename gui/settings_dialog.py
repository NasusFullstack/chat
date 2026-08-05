"""환경설정 창 - 트레이 아이콘 메뉴와 채널 목록 아래 톱니바퀴에서 연다.

탭을 셋으로 나눈다: 알림 / 테마 / 정보. 예전엔 한 장에 다 늘어놨는데, 항목이 늘면서
"무엇을 찾으려면 어디를 봐야 하는지"가 없어졌다.

알림 설정은 **계층**이다 - 위가 꺼지면 아래는 의미가 없다:

    새 메시지 알림 표시
      └ 알림에 보낸 사람과 내용 표시
          └ (끄면) 사람만 / 메시지만 / 모두 숨김 중 하나

그래서 위 항목이 꺼지면 아래 항목은 회색으로 흐려지고 눌리지 않는다(숨기지는 않는다 -
사라지면 그런 설정이 있다는 것 자체를 모르게 된다).

로그인 정보는 여기서 다루지 않는다 - 그건 로그인 화면 소관이고 저장 파일도 따로다.
"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QDialog, QFrame,
                               QHBoxLayout, QLabel, QPushButton, QRadioButton,
                               QTabWidget, QVBoxLayout, QWidget)

import app_prefs
from gui.helpers import _find_logo_image
from gui.styles.palette import DEFAULT_THEME, colors, theme_choices
from gui.theme import (APP_TITLE, COPYRIGHT_YEAR, DEVELOPER_EMAIL, DEVELOPER_GITHUB,
                       DEVELOPER_NAME, GITHUB_URL, INFO_LOGO_PX, IS_WINDOWS)
from gui.themed_dialogs import _MiniTitleBar
from version import APP_VERSION, RELEASE_DATE

# 한 단계 들여쓸 때의 폭. 계층이 눈에 보이게 하는 유일한 장치라 충분히 들여쓴다
INDENT_PX = 26

# 알림에서 무엇까지 보여줄지(보낸 사람과 내용 표시를 껐을 때 고르는 값)
DETAIL_CHOICES = (
    ("sender", "사람만 표시", "누가 보냈는지만 뜨고 내용은 가려집니다."),
    ("message", "메시지만 표시", "내용만 뜨고 누가 보냈는지는 가려집니다."),
    ("none", "모두 숨김", "\"새 메시지가 도착했습니다\"만 뜹니다."),
)


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
        body.setContentsMargins(14, 12, 14, 12)
        body.setSpacing(10)

        tabs = QTabWidget()
        tabs.setObjectName("settingsTabs")
        tabs.addTab(self._build_notify_tab(prefs), "알림")
        tabs.addTab(self._build_theme_tab(prefs), "테마")
        tabs.addTab(self._build_info_tab(), "정보")
        body.addWidget(tabs)

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
        self.setMinimumWidth(420)

    # ---------------- 탭 ----------------

    def _build_notify_tab(self, prefs: dict) -> QWidget:
        tab = QWidget()
        column = QVBoxLayout(tab)
        column.setContentsMargins(16, 14, 16, 12)
        column.setSpacing(6)

        self.notify_check = QCheckBox("새 메시지 알림 표시")
        self.notify_check.setChecked(prefs["notifications"])
        column.addWidget(self.notify_check)
        column.addWidget(_hint("창을 보고 있지 않을 때만 오른쪽 아래에 뜹니다."))

        # 1단계 들여쓰기 - "알림 표시"에 딸린 설정
        self.preview_check = QCheckBox("알림에 보낸 사람과 내용 표시")
        self.preview_check.setChecked(prefs["notify_preview"])
        column.addLayout(_indented(self.preview_check, 1))
        self.preview_hint = _hint("끄면 아래에서 고른 만큼만 보여줍니다.")
        column.addLayout(_indented(self.preview_hint, 1))

        # 2단계 들여쓰기 - 위를 껐을 때 무엇까지 보여줄지
        self._detail_group = QButtonGroup(self)
        self._detail_radios = []
        saved_detail = prefs.get("notify_detail", "none")
        for value, label, tip in DETAIL_CHOICES:
            radio = QRadioButton(label)
            radio.setToolTip(tip)
            radio.setProperty("detail", value)
            radio.setChecked(value == saved_detail)
            self._detail_group.addButton(radio)
            self._detail_radios.append(radio)
            column.addLayout(_indented(radio, 2))
        if not any(r.isChecked() for r in self._detail_radios):
            self._detail_radios[-1].setChecked(True)   # 모르는 값이면 가장 조용한 쪽으로

        column.addSpacing(6)
        column.addWidget(_divider())
        self.tray_check = QCheckBox("창을 닫아도 종료하지 않고 트레이에 두기")
        self.tray_check.setChecked(prefs["close_to_tray"])
        column.addWidget(self.tray_check)
        column.addWidget(_hint("끄면 창을 닫을 때 프로그램이 완전히 종료됩니다. "
                               "켜두면 작업표시줄 오른쪽 아이콘에서 '종료'를 눌러야 끝납니다."))
        column.addStretch(1)

        self.notify_check.toggled.connect(self._sync_enabled)
        self.preview_check.toggled.connect(self._sync_enabled)
        self._sync_enabled()
        return tab

    def _build_theme_tab(self, prefs: dict) -> QWidget:
        tab = QWidget()
        column = QVBoxLayout(tab)
        column.setContentsMargins(16, 14, 16, 12)
        column.setSpacing(8)

        row = QHBoxLayout()
        row.addWidget(QLabel("테마"))
        self.theme_box = QComboBox()
        for key, label in theme_choices():
            self.theme_box.addItem(label, key)
        index = self.theme_box.findData(prefs.get("theme", DEFAULT_THEME))
        self.theme_box.setCurrentIndex(index if index >= 0 else 0)
        row.addWidget(self.theme_box, 1)
        column.addLayout(row)
        column.addWidget(_hint("지금은 기본 테마 하나입니다. 색 구성은 이미 테마 단위로 묶여 "
                               "있어서, 다음 버전에서 테마가 추가되면 여기서 바로 고를 수 있습니다."))
        column.addStretch(1)
        return tab

    def _build_info_tab(self) -> QWidget:
        """앱/만든이 정보. 값은 전부 theme.py와 version.py 한 곳에서 온다(따로 적지 않음)."""
        tab = QWidget()
        column = QVBoxLayout(tab)
        column.setContentsMargins(16, 16, 16, 12)
        column.setSpacing(4)

        logo_path = _find_logo_image()
        if logo_path:
            logo = QLabel()
            logo.setObjectName("infoLogo")
            logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
            logo.setPixmap(QPixmap(logo_path).scaled(
                INFO_LOGO_PX, INFO_LOGO_PX, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation))
            column.addWidget(logo, 0, Qt.AlignmentFlag.AlignHCenter)
            column.addSpacing(6)

        name = QLabel(APP_TITLE)
        name.setObjectName("infoTitle")
        name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        column.addWidget(name)

        version = QLabel(f"v{APP_VERSION}  ·  {RELEASE_DATE} 릴리즈")
        version.setObjectName("infoVersion")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        column.addWidget(version)
        column.addSpacing(10)

        # 링크 색은 인라인으로 준다 - QSS에는 <a> 태그를 겨냥할 선택자가 없어서,
        # 그냥 두면 브라우저 기본 파란색이 나와 테마와 따로 논다
        link_color = colors()["ACCENT"]
        column.addWidget(_info_row("만든 사람", DEVELOPER_NAME))
        column.addWidget(_info_row("메일", _link(f"mailto:{DEVELOPER_EMAIL}",
                                                 DEVELOPER_EMAIL, link_color), link=True))
        column.addWidget(_info_row("GitHub", _link(GITHUB_URL, f"@{DEVELOPER_GITHUB}",
                                                   link_color), link=True))

        column.addStretch(1)
        copyright_label = QLabel(
            f"Copyright © {COPYRIGHT_YEAR} {DEVELOPER_NAME}. All rights reserved.")
        copyright_label.setObjectName("infoCopyright")
        copyright_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        column.addWidget(copyright_label)
        return tab

    # ---------------- 계층 흐리기 ----------------

    def _sync_enabled(self):
        """위 항목이 꺼져 있으면 그에 딸린 것들을 흐리게 만든다."""
        notifying = self.notify_check.isChecked()
        self.preview_check.setEnabled(notifying)
        self.preview_hint.setEnabled(notifying)
        # 보낸 사람과 내용을 다 보여주는 중이면 "무엇까지 보여줄까"는 고를 필요가 없다
        detail_usable = notifying and not self.preview_check.isChecked()
        for radio in self._detail_radios:
            radio.setEnabled(detail_usable)

    # ---------------- 저장 ----------------

    def selected_detail(self) -> str:
        for radio in self._detail_radios:
            if radio.isChecked():
                return radio.property("detail")
        return "none"

    def _save(self):
        # 이 창에서 안 다루는 설정(채널 목록 접힘 등)은 그대로 둬야 하므로 읽고 갱신한다
        prefs = app_prefs.load()
        prefs.update({
            "notifications": self.notify_check.isChecked(),
            "notify_preview": self.preview_check.isChecked(),
            "notify_detail": self.selected_detail(),
            "close_to_tray": self.tray_check.isChecked(),
            "theme": self.theme_box.currentData(),
        })
        app_prefs.save(prefs)
        self.accept()


def _link(url: str, text: str, color: str) -> str:
    return f'<a href="{url}" style="color:{color}; text-decoration:none;">{text}</a>'


def _hint(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("hint")
    label.setWordWrap(True)
    return label


def _divider() -> QFrame:
    line = QFrame()
    line.setObjectName("settingsDivider")
    line.setFrameShape(QFrame.Shape.HLine)
    return line


def _indented(widget: QWidget, level: int) -> QHBoxLayout:
    """왼쪽을 level만큼 들여쓴 줄. 계층을 눈에 보이게 하는 장치."""
    row = QHBoxLayout()
    row.setContentsMargins(INDENT_PX * level, 0, 0, 0)
    row.addWidget(widget, 1)
    return row


def _info_row(label: str, value: str, link: bool = False) -> QWidget:
    """'항목  값' 한 줄. 값이 링크면 눌러서 열 수 있게 한다."""
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    key = QLabel(label)
    key.setObjectName("infoKey")
    key.setFixedWidth(74)
    layout.addWidget(key)
    val = QLabel(value)
    val.setObjectName("infoValue")
    if link:
        val.setTextFormat(Qt.TextFormat.RichText)
        val.setOpenExternalLinks(True)
    layout.addWidget(val, 1)
    return row
