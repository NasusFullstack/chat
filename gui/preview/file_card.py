"""채팅에 뜬 파일을 카드로 - 이름·크기·언제까지 받을 수 있는지, 그리고 받기 버튼.

## 왜 카드로 그리나
주소 한 줄만 있으면 그게 무슨 파일인지, 얼마나 큰지, 아직 살아 있기는 한지 알 수가 없다.
게다가 우리 주소는 이름이 부호화돼 있어 눈으로 읽기도 어렵다. 카톡이나 라인처럼
**무엇인지 보고 누르는** 모양이 맞다.

## 받는 것은 브라우저에 맡긴다
앱이 직접 받으면 채팅 안에서 진행률을 보여줄 수는 있지만, 끊겼을 때 이어받기·바이러스
검사·"인터넷에서 받은 파일" 표시를 전부 우리가 다시 만들어야 한다. 브라우저는 그걸 이미
다 한다. 그래서 받기는 브라우저로 넘긴다.

## 내가 올린 것만 내릴 수 있다
올릴 때 서버가 준 표를 갖고 있으면 내 것이다(file_tokens.py). 그때만 '내리기'가 보인다.
"""
import json
import time

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout,
                               QWidget)

import file_tokens
import relay

CARD_MAX_WIDTH = 380
ICON_PX = 38


def readable_size(size: int) -> str:
    for unit, step in (("GB", 1024 ** 3), ("MB", 1024 ** 2), ("KB", 1024)):
        if size >= step:
            return f"{size / step:.1f}{unit}"
    return f"{size}B"


def remaining_text(expires: float, now: float | None = None) -> str:
    """언제까지 받을 수 있는지를 사람 말로.

    남은 시각을 그대로 보여주면(2026-09-30 14:22) 얼마나 급한지 감이 안 온다.
    '3시간 뒤 사라짐'이면 지금 받아야 하는지 바로 안다.
    """
    if not expires:
        return ""          # 이모티콘처럼 기한이 없는 것
    left = expires - (time.time() if now is None else now)
    if left <= 0:
        return "기간이 지나 사라졌습니다"
    if left < 3600:
        return f"{max(1, int(left // 60))}분 뒤 사라짐"
    if left < 86400:
        return f"{int(left // 3600)}시간 뒤 사라짐"
    return f"{int(left // 86400)}일 뒤 사라짐"


def parse_meta(data: bytes) -> dict | None:
    """서버가 알려준 파일 정보. 못 읽거나 없는 파일이면 None."""
    try:
        info = json.loads(data.decode("utf-8"))
    except (ValueError, UnicodeDecodeError, AttributeError):
        return None
    if not isinstance(info, dict) or info.get("error") or not info.get("name"):
        return None
    return info


class FileCard(QWidget):
    """파일 하나를 나타내는 칸."""

    taken_back = Signal(str)     # 내가 내린 파일의 id

    def __init__(self, url: str, info: dict, parent=None):
        super().__init__(parent)
        self.setObjectName("fileCard")
        self._url = url
        self._file_id = info.get("id", "") or relay.file_id_from(url)
        self._name = info.get("name", "파일")
        self.setMaximumWidth(CARD_MAX_WIDTH)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)

        row = QHBoxLayout(self)
        row.setContentsMargins(10, 8, 10, 8)
        row.setSpacing(9)

        icon = QLabel("📄")
        icon.setObjectName("fileCardIcon")
        icon.setFixedSize(ICON_PX, ICON_PX)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)

        column = QVBoxLayout()
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(1)

        self.name_label = QLabel(self._name)
        self.name_label.setObjectName("fileCardName")
        self.name_label.setWordWrap(True)
        column.addWidget(self.name_label)

        parts = [readable_size(int(info.get("size", 0)))]
        left = remaining_text(float(info.get("expires", 0) or 0))
        if left:
            parts.append(left)
        self.info_label = QLabel(" · ".join(parts))
        self.info_label.setObjectName("fileCardInfo")
        column.addWidget(self.info_label)
        row.addLayout(column, 1)

        buttons = QVBoxLayout()
        buttons.setContentsMargins(0, 0, 0, 0)
        buttons.setSpacing(3)
        self.get_btn = QPushButton("받기")
        self.get_btn.setObjectName("fileCardBtn")
        self.get_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.get_btn.clicked.connect(self._download)
        buttons.addWidget(self.get_btn)

        # 내가 올린 것만 내릴 수 있다 - 표가 있으면 내 것이다
        self.drop_btn = QPushButton("내리기")
        self.drop_btn.setObjectName("fileCardDropBtn")
        self.drop_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.drop_btn.setToolTip("서버에서 지웁니다. 남들도 더 이상 못 받습니다")
        self.drop_btn.clicked.connect(self._take_back)
        self.drop_btn.setVisible(file_tokens.is_mine(self._file_id))
        buttons.addWidget(self.drop_btn)
        row.addLayout(buttons, 0)

    # ------------------------------------------------------------------
    def _download(self):
        """받기는 브라우저에 맡긴다(이유는 파일 맨 위 설명 참고)."""
        QDesktopServices.openUrl(QUrl(self._url))

    def _take_back(self):
        import gui_client  # 지연 import - 이유는 CLAUDE.md 1번 규칙

        if not gui_client.themed_question(
                self, "파일 내리기",
                f"'{self._name}'을(를) 서버에서 지울까요?\n"
                "받은 사람은 그대로지만, 아직 안 받은 사람은 못 받게 됩니다."):
            return
        from gui.file_actions import take_back

        take_back(self._file_id, self._on_taken_back)

    def _on_taken_back(self, ok: bool, note: str):
        import gui_client

        if not ok:
            gui_client.themed_warning(self, "파일 내리기", note)
            return
        self.get_btn.setEnabled(False)
        self.drop_btn.setVisible(False)
        self.info_label.setText("내렸습니다 - 더 이상 받을 수 없습니다")
        self.name_label.setEnabled(False)
        self.taken_back.emit(self._file_id)
