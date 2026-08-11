"""업데이트가 끝난 뒤 "이번에 뭐가 바뀌었는지"를 한 번 보여주는 창.

패치는 조용히 끝나기 때문에, 사용자는 무엇이 달라졌는지 알 방법이 없었다(저장소의
CHANGELOG.md는 앱을 쓰는 사람이 볼 곳이 아니다).

지켜야 할 것 두 가지:
- **한 버전당 한 번만.** 켤 때마다 뜨면 성가시다. 이미 보여준 버전을 app_prefs에 적어둔다
- **저절로 닫히지 않는다.** 읽는 중에 사라지면 다시 볼 방법이 없다. 닫는 건 사람이 한다
"""
import os
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QPushButton, QScrollArea,
                               QVBoxLayout, QWidget)

import app_prefs
from gui.helpers import _find_logo_image
from gui.theme import APP_TITLE, INFO_LOGO_PX, IS_WINDOWS
from gui.themed_dialogs import _MiniTitleBar
from version import APP_VERSION, RELEASE_DATE

CHANGELOG_FILENAME = "CHANGELOG.md"
# 이미 보여준 버전을 적어두는 설정 이름
SHOWN_KEY = "changelog_shown_version"

DIALOG_WIDTH = 460
DIALOG_MAX_HEIGHT = 520


def _find_changelog() -> str:
    """변경 내역 파일 위치. 배포본에서는 PyInstaller가 풀어놓은 폴더에도 있다."""
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    candidates = [os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else here,
                  getattr(sys, "_MEIPASS", ""), here]
    for directory in candidates:
        if not directory:
            continue
        path = os.path.join(directory, CHANGELOG_FILENAME)
        if os.path.exists(path):
            return path
    return ""


def section_for(text: str, version: str) -> str:
    """CHANGELOG.md에서 그 버전 부분만 잘라낸다. 없으면 빈 글자.

    파일 형식은 `## v2.0.11` 로 시작하는 문단들이다. 다음 `## v`가 나오면 거기까지.
    """
    marker = f"## v{version}"
    start = text.find(marker)
    if start < 0:
        return ""
    body_start = start + len(marker)
    end = text.find("\n## v", body_start)
    body = text[body_start:end if end > 0 else len(text)]
    return body.strip()


def load_notes(version: str = APP_VERSION) -> str:
    path = _find_changelog()
    if not path:
        return ""
    try:
        with open(path, "r", encoding="utf-8") as fp:
            return section_for(fp.read(), version)
    except OSError:
        return ""


def should_show(version: str = APP_VERSION) -> bool:
    """이 버전의 내역을 아직 안 보여줬는가.

    처음 설치한 경우(기록이 아예 없음)에는 보여주지 않는다 - 방금 깔았는데 '변경 내역'이
    뜨는 건 뜬금없다. 조용히 지금 버전을 적어두고, 다음 패치부터 보여준다.
    """
    shown = app_prefs.get(SHOWN_KEY)
    if not shown:
        app_prefs.set_value(SHOWN_KEY, version)
        return False
    return shown != version


def mark_shown(version: str = APP_VERSION):
    app_prefs.set_value(SHOWN_KEY, version)


def _to_html(markdown_text: str) -> str:
    """변경 내역의 간단한 표기만 HTML로 바꾼다(굵게, 목록, 소제목).

    제대로 된 마크다운 변환기를 끌어오지 않는 이유: 우리가 쓰는 표기가 몇 개뿐이고,
    외부 의존성을 하나 늘리면 빌드도 그만큼 커진다.
    """
    import html
    import re

    lines = []
    for raw in markdown_text.splitlines():
        line = html.escape(raw.strip())
        if not line:
            lines.append("<br>")
            continue
        line = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", line)
        line = re.sub(r"`(.+?)`", r"<code>\1</code>", line)
        if line.startswith("- "):
            lines.append(f"<div style='margin:3px 0 3px 10px;'>· {line[2:]}</div>")
        elif line.startswith("  - "):
            lines.append(f"<div style='margin:2px 0 2px 26px;'>- {line[4:]}</div>")
        else:
            lines.append(f"<div style='margin:4px 0;'>{line}</div>")
    return "".join(lines)


class ChangelogDialog(QDialog):
    """이번 버전의 변경 내역. 닫기 전에는 안 사라진다."""

    def __init__(self, notes: str, parent=None):
        super().__init__(parent)
        if IS_WINDOWS:
            self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(1, 1, 1, 1)
        outer.setSpacing(0)
        outer.addWidget(_MiniTitleBar(self, "업데이트 완료"))

        host = QWidget()
        body = QVBoxLayout(host)
        body.setContentsMargins(18, 14, 18, 14)
        body.setSpacing(8)

        logo_path = _find_logo_image()
        if logo_path:
            logo = QLabel()
            logo.setObjectName("infoLogo")
            logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
            logo.setPixmap(QPixmap(logo_path).scaled(
                INFO_LOGO_PX, INFO_LOGO_PX, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation))
            body.addWidget(logo, 0, Qt.AlignmentFlag.AlignHCenter)

        title = QLabel(f"{APP_TITLE}이 v{APP_VERSION}(으)로 업데이트되었습니다")
        title.setObjectName("infoTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setWordWrap(True)
        body.addWidget(title)

        when = QLabel(f"{RELEASE_DATE} 릴리즈")
        when.setObjectName("infoVersion")
        when.setAlignment(Qt.AlignmentFlag.AlignCenter)
        body.addWidget(when)
        body.addSpacing(4)

        # 내역이 길 수 있으므로 스크롤 영역에 담는다(창이 화면 밖으로 자라지 않게)
        content = QLabel(_to_html(notes))
        content.setObjectName("changelogBody")
        content.setWordWrap(True)
        content.setTextFormat(Qt.TextFormat.RichText)
        content.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        area = QScrollArea()
        area.setObjectName("changelogArea")
        area.setWidgetResizable(True)
        area.setWidget(content)
        body.addWidget(area, 1)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        close = QPushButton("확인")
        close.setDefault(True)
        close.clicked.connect(self.accept)
        buttons.addWidget(close)
        body.addLayout(buttons)

        outer.addWidget(host)
        self.setFixedWidth(DIALOG_WIDTH)
        self.setMaximumHeight(DIALOG_MAX_HEIGHT)


def show_if_updated(parent=None) -> bool:
    """업데이트 뒤 처음 켠 것이면 내역을 보여준다. 보여줬으면 True.

    **저절로 닫히지 않는다** - 타이머를 걸지 않고, 사람이 닫을 때까지 떠 있는다.
    """
    if not should_show():
        return False
    notes = load_notes()
    mark_shown()          # 내역 파일이 없어 못 보여줘도 다음 실행에 또 시도하지 않게
    if not notes:
        return False
    ChangelogDialog(notes, parent).exec()
    return True
