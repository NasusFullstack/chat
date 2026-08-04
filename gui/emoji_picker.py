"""이모티콘 보관함 창 - 저장해둔 이모티콘을 미리보기로 보고 골라 쓴다.

- 격자로 작게 미리보기(움짤은 움직임)
- 한 쪽에 12개씩, 화살표로 페이지 넘김
- 내가 붙인 이름으로 검색
- 우클릭으로 이름 바꾸기 / 보관함에서 빼기

그림은 창이 살아있는 동안 캐시한다(페이지를 오갈 때 같은 그림을 또 받지 않게).
보관함에는 **주소만** 있고 그림 파일은 저장하지 않는다.
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QDialog, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                               QMenu, QPushButton, QVBoxLayout, QWidget)

import emoji_store
from gui.link_preview import ImagePreview
from gui.theme import IS_WINDOWS
from gui.themed_dialogs import _MiniTitleBar

COLUMNS = 4
ROWS = 3
PER_PAGE = COLUMNS * ROWS
THUMB_PX = 84


class EmojiPicker(QDialog):
    """고른 이모티콘 주소를 emoji_chosen으로 알려줌"""

    emoji_chosen = Signal(str)

    def __init__(self, parent=None, fetcher=None):
        super().__init__(parent)
        self._fetcher = fetcher
        self._cache: dict[str, bytes] = {}
        self._page = 0
        self._items: list[dict] = []
        if IS_WINDOWS:
            self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(1, 1, 1, 1)
        outer.setSpacing(0)
        outer.addWidget(_MiniTitleBar(self, "이모티콘"))

        body_host = QWidget()
        body = QVBoxLayout(body_host)
        body.setContentsMargins(14, 10, 14, 12)
        body.setSpacing(8)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("이름으로 검색")
        self.search_input.textChanged.connect(self._on_search)
        body.addWidget(self.search_input)

        self.grid_host = QWidget()
        self.grid = QGridLayout(self.grid_host)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(6)
        body.addWidget(self.grid_host, 1)

        self.empty_label = QLabel(
            "보관함이 비어 있습니다.\n채팅에 올라온 이미지를 우클릭해서 저장해 보세요.")
        self.empty_label.setObjectName("emojiEmpty")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setWordWrap(True)
        body.addWidget(self.empty_label)

        nav = QHBoxLayout()
        self.prev_btn = QPushButton("◀")
        self.prev_btn.setObjectName("emojiNavBtn")
        self.prev_btn.setFixedWidth(38)
        self.prev_btn.clicked.connect(lambda: self._go(self._page - 1))
        self.page_label = QLabel("1 / 1")
        self.page_label.setObjectName("emojiPageLabel")
        self.page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.next_btn = QPushButton("▶")
        self.next_btn.setObjectName("emojiNavBtn")
        self.next_btn.setFixedWidth(38)
        self.next_btn.clicked.connect(lambda: self._go(self._page + 1))
        nav.addWidget(self.prev_btn)
        nav.addWidget(self.page_label, 1)
        nav.addWidget(self.next_btn)
        body.addLayout(nav)

        outer.addWidget(body_host)
        self.resize(THUMB_PX * COLUMNS + 90, THUMB_PX * ROWS + 190)
        self.reload()

    # ---------------- 목록 ----------------

    def reload(self):
        keyword = self.search_input.text().strip().lower()
        items = emoji_store.load_emojis()
        if keyword:
            items = [it for it in items if keyword in it.get("name", "").lower()]
        self._items = items
        self._page = min(self._page, max(0, self.page_count() - 1))
        self._render()

    def page_count(self) -> int:
        return max(1, (len(self._items) + PER_PAGE - 1) // PER_PAGE)

    def _on_search(self):
        self._page = 0
        self.reload()

    def _go(self, page: int):
        self._page = max(0, min(page, self.page_count() - 1))
        self._render()

    def _render(self):
        while self.grid.count():
            item = self.grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

        start = self._page * PER_PAGE
        for index, entry in enumerate(self._items[start:start + PER_PAGE]):
            cell = _EmojiCell(entry, self._fetcher, self._cache, self)
            cell.picked.connect(self._on_picked)
            cell.changed.connect(self.reload)
            self.grid.addWidget(cell, index // COLUMNS, index % COLUMNS)

        self.empty_label.setVisible(not self._items)
        self.grid_host.setVisible(bool(self._items))
        self.page_label.setText(f"{self._page + 1} / {self.page_count()}")
        self.prev_btn.setEnabled(self._page > 0)
        self.next_btn.setEnabled(self._page < self.page_count() - 1)

    def _on_picked(self, url: str):
        self.emoji_chosen.emit(url)
        self.accept()


class _EmojiCell(QWidget):
    """격자 한 칸 - 미리보기 + 이름"""

    picked = Signal(str)
    changed = Signal()

    def __init__(self, entry: dict, fetcher, cache: dict, parent=None):
        super().__init__(parent)
        self.setObjectName("emojiCell")
        self._url = entry["url"]
        self._name = entry.get("name", "")
        self._cache = cache
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(self._name or self._url)

        column = QVBoxLayout(self)
        column.setContentsMargins(2, 2, 2, 2)
        column.setSpacing(2)
        self.preview = ImagePreview(self._url, self)
        self.preview.set_max_width(THUMB_PX)
        self.preview.setFixedSize(THUMB_PX, THUMB_PX)
        # 미리보기 자체의 클릭은 '주소 열기'라서 고르기와 충돌함 - 이 칸에서는 막는다
        self.preview.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        column.addWidget(self.preview, 0, Qt.AlignmentFlag.AlignHCenter)

        label = QLabel()
        label.setObjectName("emojiName")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setFixedWidth(THUMB_PX)
        label.setText(label.fontMetrics().elidedText(
            self._name, Qt.TextElideMode.ElideRight, THUMB_PX - 4))
        column.addWidget(label, 0, Qt.AlignmentFlag.AlignHCenter)

        data = cache.get(self._url)
        if data is not None:
            self._show(data)
        elif fetcher is not None:
            fetcher.fetch(self._url, self._on_image)

    def _show(self, data):
        if self.preview.set_image_data(data):
            self.preview.set_max_width(THUMB_PX)

    def _on_image(self, data):
        if not data:
            return
        self._cache[self._url] = data
        self._show(data)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.picked.emit(self._url)
        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event):
        import gui_client  # 지연 import - 이유는 gui/pages.py 맨 위 설명 참고

        menu = QMenu(self)
        rename = menu.addAction("이름 바꾸기")
        remove = menu.addAction("보관함에서 빼기")
        chosen = menu.exec(event.globalPos())
        if chosen is rename:
            name, ok = gui_client.themed_get_text(
                self, "이름 바꾸기", f"'{self._name or self._url}'의 새 이름")
            if ok:
                emoji_store.rename_emoji(self._url, name)
                self.changed.emit()
        elif chosen is remove:
            if gui_client.themed_question(self, "이모티콘", "보관함에서 뺄까요?"):
                emoji_store.remove_emoji(self._url)
                self.changed.emit()
