"""프로필(닉네임 + 16x16 픽셀아트 아이콘) 편집 다이얼로그 + 색상 선택 다이얼로그.

themed_warning은 테스트가 g.themed_warning = fake로 직접 몽키패치하는 대상이라, 여기서는
호출하는 메서드 본문 안에서 `import gui_client`를 한 뒤 `gui_client.themed_warning(...)`
처럼 모듈 속성으로 조회해서 호출함. 이 import를 파일 맨 위에 두면 PyInstaller로 빌드한
실행 파일에서 순환참조 크래시가 남(로컬 CPython에서는 통과하지만 프로즌 임포터는 버전에
따라 덜 관대함 - 실제로 사고가 났었음) - 자세한 이유는 gui_client.py 상단 주석 참고.
ProfileDialog 클래스 자체는 몽키패치 대상이 아니라(패치되는 건 인스턴스의 exec 메서드)
자유롭게 재수출해도 안전함.
"""
import base64

from PySide6.QtCore import Qt, QBuffer, QIODevice
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QVBoxLayout, QWidget,
)

from gui.helpers import _decode_avatar_pixmap
from gui.theme import AVATAR_CELL_PX, AVATAR_GRID_SIZE, AVATAR_MAX_B64_CHARS, IS_WINDOWS, NICKNAME_MAX_LEN
from gui.themed_dialogs import _MiniTitleBar


class ColorPickerDialog(QDialog):
    """Qt 기본 QColorDialog는 'HTML' 같은 영어 라벨이 그대로 나와서, 한글 라벨의 간단한 색상 선택창을 직접 만듦"""

    _PALETTE = [
        "#ff6b6b", "#ffa94d", "#ffd43b", "#69db7c", "#38d9a9",
        "#4dabf7", "#748ffc", "#9775fa", "#f783ac", "#e6e6e6",
        "#adb5bd", "#495057", "#16171f", "#7c6cf0", "#ffffff",
    ]

    def __init__(self, initial: QColor, parent=None):
        super().__init__(parent)
        self.setWindowTitle("색상 선택")
        self.selected_color = QColor(initial)

        if IS_WINDOWS:
            self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(1, 1, 1, 1)
        outer.setSpacing(0)
        outer.addWidget(_MiniTitleBar(self, "색상 선택"))

        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(16, 14, 16, 14)
        outer.addWidget(body)

        grid_widget = QWidget()
        grid = QGridLayout(grid_widget)
        grid.setSpacing(4)
        for i, hex_color in enumerate(self._PALETTE):
            swatch = QPushButton()
            swatch.setFixedSize(24, 24)
            swatch.setStyleSheet(f"background-color: {hex_color}; border: 1px solid #3d3f52; border-radius: 0px;")
            swatch.clicked.connect(lambda checked=False, c=hex_color: self._pick(QColor(c)))
            grid.addWidget(swatch, i // 5, i % 5)
        layout.addWidget(grid_widget)

        code_row = QHBoxLayout()
        code_row.addWidget(QLabel("색상 코드:"))
        self.code_input = QLineEdit(self.selected_color.name())
        self.code_input.setPlaceholderText("#rrggbb")
        self.code_input.editingFinished.connect(self._on_code_entered)
        code_row.addWidget(self.code_input)
        layout.addLayout(code_row)

        self.preview = QLabel()
        self.preview.setFixedHeight(24)
        layout.addWidget(self.preview)
        self._update_preview()

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.button(QDialogButtonBox.StandardButton.Ok).setText("확인")
        button_box.button(QDialogButtonBox.StandardButton.Cancel).setText("취소")
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _pick(self, color: QColor):
        self.selected_color = color
        self.code_input.setText(color.name())
        self._update_preview()

    def _on_code_entered(self):
        color = QColor(self.code_input.text().strip())
        if color.isValid():
            self.selected_color = color
        else:
            self.code_input.setText(self.selected_color.name())
        self._update_preview()

    def _update_preview(self):
        self.preview.setStyleSheet(f"background-color: {self.selected_color.name()}; border: 1px solid #3d3f52; border-radius: 0px;")


class _AvatarGridWidget(QWidget):
    """아이콘 그리기 격자 - 마우스를 누른 채로 드래그하면 지나가는 칸을 전부 칠함
    (QPushButton의 clicked 신호만으로는 한 번에 한 칸씩만 클릭해야 해서, 격자 위젯이
    직접 마우스 이벤트를 받아 좌표를 계산하는 방식으로 구현. 자식 버튼들은
    WA_TransparentForMouseEvents로 마우스 이벤트를 무시하게 하고 시각적 표시 용도로만 씀)"""

    def __init__(self, cell_px: int, grid_size: int, on_paint, parent=None):
        super().__init__(parent)
        self._cell_px = cell_px
        self._grid_size = grid_size
        self._on_paint = on_paint
        self._painting = False

    def _cell_at(self, pos) -> tuple[int, int] | None:
        x = int(pos.x()) // self._cell_px
        y = int(pos.y()) // self._cell_px
        if 0 <= x < self._grid_size and 0 <= y < self._grid_size:
            return x, y
        return None

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self._painting = True
        cell = self._cell_at(event.position())
        if cell:
            self._on_paint(*cell)

    def mouseMoveEvent(self, event):
        if not self._painting:
            return
        cell = self._cell_at(event.position())
        if cell:
            self._on_paint(*cell)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._painting = False


class ProfileDialog(QDialog):
    """프로필(닉네임 + 16x16 픽셀아트 아이콘) 편집 - 드래그로 여러 칸 칠하기, 지우개, 전체 지우기 지원"""

    def __init__(self, initial_base64: str | None = None, initial_nickname: str = "", is_irc: bool = False, parent=None):
        super().__init__(parent)
        self.setWindowTitle("프로필 변경")
        self.result_base64 = ""
        self.result_nickname = ""
        self._current_color = QColor("#7c6cf0")
        self._eraser = False
        self._cell_colors: dict[tuple[int, int], QColor | None] = {}
        self._buttons: dict[tuple[int, int], QPushButton] = {}

        if IS_WINDOWS:
            self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(1, 1, 1, 1)
        outer.setSpacing(0)
        outer.addWidget(_MiniTitleBar(self, "프로필 변경"))

        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(16, 14, 16, 14)
        outer.addWidget(body)

        nick_row = QHBoxLayout()
        nick_row.addWidget(QLabel("닉네임"))
        self._nickname_input = QLineEdit(initial_nickname)
        self._nickname_input.setMaxLength(NICKNAME_MAX_LEN)
        placeholder = (
            "IRC 서버가 정한 접속 닉네임" if is_irc
            else "표시할 닉네임 (비우면 아이디로 표시)"
        )
        self._nickname_input.setPlaceholderText(placeholder)
        nick_row.addWidget(self._nickname_input)
        layout.addLayout(nick_row)
        if is_irc:
            irc_hint = QLabel("※ 실제 IRC 서버에서는 닉네임이 곧 접속 아이디예요. 다른 사람이 이미 쓰고 있으면 변경이 거부될 수 있어요.")
            irc_hint.setObjectName("hint")
            irc_hint.setWordWrap(True)
            layout.addWidget(irc_hint)

        grid_widget = _AvatarGridWidget(AVATAR_CELL_PX, AVATAR_GRID_SIZE, self._paint_cell)
        self._grid_widget = grid_widget
        grid = QGridLayout(grid_widget)
        grid.setSpacing(0)
        grid.setContentsMargins(0, 0, 0, 0)
        for y in range(AVATAR_GRID_SIZE):
            for x in range(AVATAR_GRID_SIZE):
                btn = QPushButton()
                btn.setFixedSize(AVATAR_CELL_PX, AVATAR_CELL_PX)
                btn.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
                btn.setStyleSheet("background-color: transparent; border: 1px solid #3d3f52; border-radius: 0px;")
                grid.addWidget(btn, y, x)
                self._buttons[(x, y)] = btn
        layout.addWidget(grid_widget)

        tool_row = QHBoxLayout()
        color_btn = QPushButton("색상 선택")
        color_btn.setObjectName("secondary")
        color_btn.clicked.connect(self._choose_color)
        tool_row.addWidget(color_btn)
        self._eraser_btn = QPushButton("지우개")
        self._eraser_btn.setObjectName("secondary")
        self._eraser_btn.setCheckable(True)
        self._eraser_btn.toggled.connect(self._toggle_eraser)
        tool_row.addWidget(self._eraser_btn)
        clear_btn = QPushButton("전체 지우기")
        clear_btn.setObjectName("secondary")
        clear_btn.clicked.connect(self._clear_all)
        tool_row.addWidget(clear_btn)
        layout.addLayout(tool_row)

        if initial_base64:
            self._load_initial(initial_base64)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        button_box.button(QDialogButtonBox.StandardButton.Save).setText("저장")
        button_box.button(QDialogButtonBox.StandardButton.Cancel).setText("취소")
        button_box.accepted.connect(self._on_save)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _load_initial(self, avatar_b64: str):
        pixmap = _decode_avatar_pixmap(avatar_b64)
        if pixmap is None:
            return
        image = pixmap.toImage()
        for y in range(min(AVATAR_GRID_SIZE, image.height())):
            for x in range(min(AVATAR_GRID_SIZE, image.width())):
                color = image.pixelColor(x, y)
                if color.alpha() == 0:
                    continue
                self._cell_colors[(x, y)] = color
                self._buttons[(x, y)].setStyleSheet(f"background-color: {color.name()}; border: 1px solid #3d3f52; border-radius: 0px;")

    def _paint_cell(self, x: int, y: int):
        if self._eraser:
            self._cell_colors[(x, y)] = None
            self._buttons[(x, y)].setStyleSheet("background-color: transparent; border: 1px solid #3d3f52; border-radius: 0px;")
        else:
            self._cell_colors[(x, y)] = QColor(self._current_color)
            self._buttons[(x, y)].setStyleSheet(
                f"background-color: {self._current_color.name()}; border: 1px solid #3d3f52; border-radius: 0px;"
            )

    def _choose_color(self):
        dlg = ColorPickerDialog(self._current_color, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._current_color = dlg.selected_color
            self._eraser_btn.setChecked(False)

    def _toggle_eraser(self, checked: bool):
        self._eraser = checked

    def _clear_all(self):
        self._cell_colors.clear()
        for btn in self._buttons.values():
            btn.setStyleSheet("background-color: transparent; border: 1px solid #3d3f52; border-radius: 0px;")

    def to_base64_png(self) -> str:
        image = QImage(AVATAR_GRID_SIZE, AVATAR_GRID_SIZE, QImage.Format.Format_ARGB32)
        image.fill(0)
        for (x, y), color in self._cell_colors.items():
            if color is not None:
                image.setPixelColor(x, y, color)
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        image.save(buffer, "PNG")
        return base64.b64encode(bytes(buffer.data())).decode("ascii")

    def _on_save(self):
        import gui_client  # 지연 import - 이유는 파일 맨 위 docstring 참고
        b64 = self.to_base64_png()
        if len(b64) > AVATAR_MAX_B64_CHARS:
            gui_client.themed_warning(self, "저장 실패", "아이콘 데이터가 너무 큽니다. 더 단순하게 그려주세요.")
            return
        self.result_base64 = b64
        self.result_nickname = self._nickname_input.text().strip()
        self.accept()
