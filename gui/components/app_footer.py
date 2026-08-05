"""만든이 표시 - 로고 / 앱 이름·버전 / 메일 / GitHub / 저작권.

원래는 왼쪽 채널 사이드바 아래에 있었는데, 채널 목록은 접었다 펼 수 있게 되면서
"접으면 만든이 표시가 통째로 사라지는" 문제가 생겼다. 그래서 항상 펼쳐져 있는
오른쪽(참여자) 열 맨 아래로 옮기고, 어느 쪽에 붙어도 되도록 부품으로 뺐다.

이 부품은 아무것도 모른다 - 채널도, 참여자도, 접힘 상태도. 그냥 고정된 정보를 그린다.
"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from gui.helpers import _find_logo_image
from gui.theme import (APP_TITLE, COPYRIGHT_YEAR, DEVELOPER_EMAIL, DEVELOPER_GITHUB,
                       DEVELOPER_NAME, FOOTER_LOGO_PX, GITHUB_URL)
from version import APP_VERSION


class AppFooter(QWidget):
    """앱 정보와 만든 사람. 열 맨 아래에 붙는다."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("appFooter")
        column = QVBoxLayout(self)
        column.setContentsMargins(10, 10, 10, 12)
        column.setSpacing(2)

        logo_path = _find_logo_image()
        if logo_path:
            logo = QLabel()
            logo.setObjectName("footerLogo")
            logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
            logo.setPixmap(QPixmap(logo_path).scaled(
                FOOTER_LOGO_PX, FOOTER_LOGO_PX, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation))
            column.addWidget(logo, 0, Qt.AlignmentFlag.AlignHCenter)

        title = QLabel(f"{APP_TITLE}  <span style='color:#7f8296'>v{APP_VERSION}</span>")
        title.setObjectName("footerTitle")
        title.setTextFormat(Qt.TextFormat.RichText)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        column.addWidget(title)

        maker = QLabel(
            f'<a href="mailto:{DEVELOPER_EMAIL}" style="color:#8f92a6; text-decoration:none;">'
            f"{DEVELOPER_EMAIL}</a>")
        maker.setObjectName("footerMaker")
        maker.setTextFormat(Qt.TextFormat.RichText)
        maker.setAlignment(Qt.AlignmentFlag.AlignCenter)
        maker.setOpenExternalLinks(True)
        maker.setToolTip("만든 사람에게 메일 보내기")
        column.addWidget(maker)

        # 만든 사람 이름만 있으면 그게 깃허브 계정인지 알 수 없어서, 아이콘 대신 글자로
        # 밝히고 저장소로 바로 갈 수 있게 링크를 건다
        github = QLabel(
            f'<a href="{GITHUB_URL}" style="color:#8f92a6; text-decoration:none;">'
            f"GitHub @{DEVELOPER_GITHUB}</a>")
        github.setObjectName("footerGithub")
        github.setTextFormat(Qt.TextFormat.RichText)
        github.setAlignment(Qt.AlignmentFlag.AlignCenter)
        github.setOpenExternalLinks(True)
        github.setToolTip(GITHUB_URL)
        column.addWidget(github)

        copyright_label = QLabel(f"© {COPYRIGHT_YEAR} {DEVELOPER_NAME}")
        copyright_label.setObjectName("footerCopyright")
        copyright_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        column.addWidget(copyright_label)
