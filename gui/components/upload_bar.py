"""지금 올리는 중인 파일을 보여주는 줄 - 이름, 진행률, 그리고 취소.

## 왜 따로 두나
1GB까지 올릴 수 있게 되면서 올리는 데 몇 분씩 걸린다. 그동안 아무 표시가 없으면 멈춘
줄 알고, 잘못 고른 것을 되돌릴 방법도 없다. 입력창 안내 문구로 %를 보여주던 때는
글자를 치기 시작하면 그마저 안 보였다.

입력줄 바로 위에 붙어서, 올리는 동안만 나타난다.

## 스스로 아무것도 정하지 않는다
취소를 누르면 `cancelled`만 알린다. 실제로 무엇을 멈출지는 화면이 정한다
(부품은 자기 일만 안다 - CLAUDE.md의 SRP 항목).
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QProgressBar, QPushButton, QWidget

BAR_HEIGHT = 30


def readable(size: int) -> str:
    for unit, step in (("GB", 1024 ** 3), ("MB", 1024 ** 2), ("KB", 1024)):
        if size >= step:
            return f"{size / step:.1f}{unit}"
    return f"{size}B"


class UploadBar(QWidget):
    """올리는 중에만 보이는 줄."""

    cancelled = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("uploadBar")
        row = QHBoxLayout(self)
        row.setContentsMargins(10, 4, 8, 4)
        row.setSpacing(8)

        self.name_label = QLabel()
        self.name_label.setObjectName("uploadBarName")
        row.addWidget(self.name_label, 0)

        self.bar = QProgressBar()
        self.bar.setObjectName("uploadBarProgress")
        self.bar.setRange(0, 100)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(8)
        row.addWidget(self.bar, 1)

        self.percent_label = QLabel("0%")
        self.percent_label.setObjectName("uploadBarPercent")
        self.percent_label.setAlignment(Qt.AlignmentFlag.AlignRight
                                        | Qt.AlignmentFlag.AlignVCenter)
        # 숫자가 바뀔 때 줄이 들썩이지 않게 자리를 미리 잡아둔다
        self.percent_label.setFixedWidth(
            self.percent_label.fontMetrics().horizontalAdvance("100%") + 4)
        row.addWidget(self.percent_label, 0)

        self.cancel_btn = QPushButton("취소")
        self.cancel_btn.setObjectName("uploadBarCancel")
        self.cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_btn.clicked.connect(self.cancelled.emit)
        row.addWidget(self.cancel_btn, 0)

        self.setFixedHeight(BAR_HEIGHT)
        self.hide()

    # ------------------------------------------------------------------
    def start(self, name: str):
        """올리기 시작. 크기를 아직 모르므로 0%부터."""
        self.name_label.setText(name)
        self.bar.setRange(0, 0)      # 첫 진행이 오기 전까지는 '움직이는' 막대
        self.percent_label.setText("")
        self.cancel_btn.setEnabled(True)
        self.show()

    def set_progress(self, sent: int, total: int):
        if total <= 0:
            return
        if self.bar.maximum() == 0:
            self.bar.setRange(0, 100)
        percent = min(100, sent * 100 // total)
        self.bar.setValue(percent)
        self.percent_label.setText(f"{percent}%")
        self.name_label.setToolTip(f"{readable(sent)} / {readable(total)}")

    def stop(self):
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        self.hide()
