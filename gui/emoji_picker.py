"""이모티콘 보관함 창 - 저장해둔 이모티콘을 미리보기로 보고 골라 쓴다.

- **즐겨찾기**와 **전체** 두 칸. 저장된 이모티콘은 같은 채팅 서버를 쓰는 사람이면
  누구나 꺼내 쓸 수 있으므로 *전체*가 진짜 보관함이고, *즐겨찾기*는 그중 내가 자주 쓰는
  것만 따로 빼둔 목록이다(혼자 보려고 저장하는 게 아니므로 이 관계가 맞다)
- 격자로 작게 미리보기(움짤은 움직임)
- 한 쪽에 3x4=12개씩, 화살표로 페이지 넘김
- 내가 붙인 이름으로 검색
- 우클릭으로 이름 바꾸기 / 보관함에서 빼기

그림은 창이 살아있는 동안 기억한다 - **받아온 것과 받는 중인 것을 함께**(_Images).
받아온 것만 기억하면 답이 오기 전에 화면을 다시 그릴 때 같은 그림을 또 요청한다.
보관함에는 **주소만** 있고 그림 파일은 저장하지 않는다.
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QDialog, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                               QMenu, QPushButton, QVBoxLayout, QWidget)

import emoji_store
from gui.emoji_shared import SharedEmoji
from gui.link_preview import ImagePreview
from gui.theme import IS_WINDOWS
from gui.themed_dialogs import _MiniTitleBar

COLUMNS = 3
ROWS = 4
PER_PAGE = COLUMNS * ROWS
THUMB_PX = 104


class _Images:
    """이모티콘 그림을 받아오고 기억한다 - **받아온 것과 받는 중인 것을 함께.**

    받아온 것만 기억하면 답이 오기 전에 화면을 다시 그릴 때(칸을 옮기거나 검색하거나
    페이지를 넘길 때) 같은 그림을 또 요청한다. 즐겨찾기와 전체 양쪽에 있는 이모티콘이
    그래서 두 번씩 받아와졌다(실측 2026-09-30: 겹치는 11개가 전부 두 번).

    받는 중인 것에는 **줄만 선다.** 답이 오면 그때 기다리던 칸들에 한꺼번에 나눠준다.
    """

    def __init__(self, fetcher):
        self._fetcher = fetcher
        self._data: dict[str, bytes] = {}
        self._waiting: dict[str, list] = {}

    def want(self, url: str, cell):
        """이 칸이 그 그림을 원한다. 이미 있으면 바로 주고, 받는 중이면 줄을 세운다."""
        data = self._data.get(url)
        if data is not None:
            cell.show_image(data)
            return
        waiting = self._waiting.get(url)
        if waiting is not None:
            waiting.append(cell)
            return
        self._waiting[url] = [cell]
        if self._fetcher is not None:
            self._fetcher.fetch(url, lambda got, u=url: self._arrived(u, got))

    def _arrived(self, url: str, data):
        waiting = self._waiting.pop(url, [])
        if not data:
            return
        self._data[url] = data
        for cell in waiting:
            try:
                cell.show_image(data)
            except RuntimeError:
                # 기다리는 사이에 그 칸이 사라졌다(페이지를 넘겼거나 창을 닫았거나).
                # 받아온 그림은 위에서 이미 기억해뒀으므로 버려지는 것은 없다
                continue

    def __len__(self):
        return len(self._data)


class EmojiPicker(QDialog):
    """고른 이모티콘 주소를 emoji_chosen으로 알려줌"""

    emoji_chosen = Signal(str)

    def __init__(self, parent=None, fetcher=None, group=""):
        """group은 '누구와 같이 쓰는가' - 같은 채팅 서버를 쓰는 사람들(gui/emoji_shared.py).
        비어 있으면 같이 쓰는 칸을 아예 안 보여준다(어디에 물어야 할지 모르므로)."""
        super().__init__(parent)
        # 받아오기는 전부 _Images가 맡는다 - 칸은 '이 그림이 필요하다'만 말한다
        self._group = group
        self._images = _Images(fetcher)
        self._page = 0
        self._items: list[dict] = []
        self._shared_mode = False
        self._shared = SharedEmoji(self)
        self._shared.ready.connect(self._on_shared)
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

        # 두 칸을 위에 둔다 - 탭처럼 생긴 버튼 둘이면 충분하다
        tabs = QHBoxLayout()
        tabs.setSpacing(6)
        self.mine_btn = QPushButton("즐겨찾기")
        self.shared_btn = QPushButton("전체")
        for button in (self.mine_btn, self.shared_btn):
            button.setObjectName("emojiTabBtn")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            tabs.addWidget(button, 1)
        # **즐겨찾기가 비어 있으면 전체를 먼저 보여준다.** 처음 쓰는 사람에게 빈 화면을
        # 내밀면 이모티콘이 아예 없는 줄 안다
        start_shared = bool(group) and not emoji_store.load_emojis()
        self.mine_btn.setChecked(not start_shared)
        self.shared_btn.setChecked(start_shared)
        self._shared_mode = start_shared
        self.mine_btn.clicked.connect(lambda: self._switch(False))
        self.shared_btn.clicked.connect(lambda: self._switch(True))
        self.shared_btn.setToolTip("저장된 이모티콘 전부 - 누가 저장했든 꺼내 쓸 수 있습니다")
        self.mine_btn.setToolTip("전체에서 자주 쓰는 것만 빼둔 목록")
        self.shared_btn.setVisible(bool(group))
        self.mine_btn.setVisible(bool(group))
        body.addLayout(tabs)

        top_row = QHBoxLayout()
        top_row.setSpacing(6)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("이름으로 검색")
        self.search_input.textChanged.connect(self._on_search)
        self.add_btn = QPushButton("+ 추가")
        self.add_btn.setObjectName("emojiAddBtn")
        self.add_btn.setToolTip("주소와 이름을 직접 넣어서 추가")
        self.add_btn.clicked.connect(self._add_by_hand)
        top_row.addWidget(self.search_input, 1)
        top_row.addWidget(self.add_btn)
        body.addLayout(top_row)

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
        if self._shared_mode:
            # 전체 칸으로 열렸으면 목록을 받아와야 한다. 안 그러면 사람이 칸을 한 번
            # 눌러줄 때까지 텅 비어 보인다
            self._shared.fetch(self._group)

    # ---------------- 목록 ----------------

    def _switch(self, shared: bool):
        """즐겨찾기 <-> 전체."""
        self._shared_mode = shared
        self.mine_btn.setChecked(not shared)
        self.shared_btn.setChecked(shared)
        self.add_btn.setVisible(not shared)
        self._page = 0
        if shared:
            # 받아오는 동안에도 기억해둔 것을 먼저 보여준다(빈 화면이 깜빡이지 않게)
            self._items = self._filtered(self._shared.items)
            self._render()
            self._shared.fetch(self._group)
            return
        self.reload()

    def _filtered(self, items: list[dict]) -> list[dict]:
        keyword = self.search_input.text().strip().lower()
        if not keyword:
            return list(items)
        return [it for it in items if keyword in it.get("name", "").lower()]

    def _on_shared(self, items: list):
        if not self._shared_mode:
            return
        self._items = self._filtered(items)
        self._page = min(self._page, max(0, self.page_count() - 1))
        self._render()

    def reload(self):
        if self._shared_mode:
            self._items = self._filtered(self._shared.items)
        else:
            self._items = self._filtered(emoji_store.load_emojis())
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
                # **부모를 떼기 전에 반드시 숨긴다.** Qt에서 보이던 위젯의 부모를 떼면
                # 그 순간 '독립된 창'이 되어 화면에 잠깐 떴다가 사라진다 - 작은 빈 창이
                # 깜빡이는 것으로 보인다. 다시 그릴 때마다 칸 수만큼 반복된다
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()

        start = self._page * PER_PAGE
        for index, entry in enumerate(self._items[start:start + PER_PAGE]):
            cell = _EmojiCell(entry, self._images, self,
                              shared=self._shared_mode)
            cell.picked.connect(self._on_picked)
            cell.changed.connect(self.reload)
            self.grid.addWidget(cell, index // COLUMNS, index % COLUMNS)

        self.empty_label.setText(
            "아직 아무도 저장한 게 없습니다.\n채팅에 올라온 이미지를 우클릭해서 저장하면\n"
            "여기에 쌓이고, 다 같이 쓸 수 있습니다."
            if self._shared_mode else
            "즐겨찾기가 비어 있습니다.\n[전체]에서 자주 쓰는 것을 우클릭해\n"
            "즐겨찾기에 넣어보세요.")
        self.empty_label.setVisible(not self._items)
        self.grid_host.setVisible(bool(self._items))
        self.page_label.setText(f"{self._page + 1} / {self.page_count()}")
        self.prev_btn.setEnabled(self._page > 0)
        self.next_btn.setEnabled(self._page < self.page_count() - 1)

    def _on_picked(self, url: str):
        self.emoji_chosen.emit(url)
        self.accept()

    def _add_by_hand(self):
        """채팅에 그 그림이 없어도 주소를 직접 넣어 추가."""
        import gui_client  # 지연 import - 이유는 gui/pages.py 맨 위 설명 참고

        dialog = AddEmojiDialog(self)
        if not dialog.exec():
            return
        url, name = dialog.values()
        saved, text = emoji_store.add_emoji(url, name)
        if not saved:
            gui_client.themed_warning(self, "이모티콘 추가", text)
            return
        self.search_input.setText("")
        self._page = max(0, self.page_count() - 1)  # 방금 넣은 게 보이는 쪽으로
        self.reload()


class AddEmojiDialog(QDialog):
    """주소 + 이름을 직접 입력해서 이모티콘 추가"""

    def __init__(self, parent=None):
        super().__init__(parent)
        if IS_WINDOWS:
            self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(1, 1, 1, 1)
        outer.setSpacing(0)
        outer.addWidget(_MiniTitleBar(self, "이모티콘 추가"))

        host = QWidget()
        form = QVBoxLayout(host)
        form.setContentsMargins(16, 14, 16, 14)
        form.setSpacing(6)
        form.addWidget(QLabel("이미지 주소"))
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://... (png, gif, jpg 등)")
        form.addWidget(self.url_input)
        form.addWidget(QLabel("이름 (검색할 때 씀)"))
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("예: 웃는댕댕이")
        self.name_input.returnPressed.connect(self.accept)
        form.addWidget(self.name_input)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("취소")
        cancel.setObjectName("secondary")
        cancel.clicked.connect(self.reject)
        confirm = QPushButton("추가")
        confirm.clicked.connect(self.accept)
        buttons.addWidget(cancel)
        buttons.addWidget(confirm)
        form.addLayout(buttons)

        outer.addWidget(host)
        self.setMinimumWidth(360)

    def values(self) -> tuple[str, str]:
        return self.url_input.text().strip(), self.name_input.text().strip()


class _EmojiCell(QWidget):
    """격자 한 칸 - 미리보기 + 이름"""

    picked = Signal(str)
    changed = Signal()

    def __init__(self, entry: dict, images, parent=None, shared=False):
        super().__init__(parent)
        self.setObjectName("emojiCell")
        self._url = entry["url"]
        self._name = entry.get("name", "")
        # 전체 목록은 내 것이 아니다 - 여기서 이름을 바꾸거나 빼면 남의 것을 건드리는
        # 셈이 된다. 즐겨찾기에서만 그럴 수 있다
        self._shared = shared
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(self._name or self._url)

        column = QVBoxLayout(self)
        column.setContentsMargins(4, 4, 4, 3)
        column.setSpacing(1)
        # 그림 자리를 가운데로 몰아주고, 이름은 그림 바로 아래에 붙게 함.
        # (그림이 가로로 긴 경우 정사각 자리 안에서 위아래 여백이 생겨 이름이 멀어 보였음)
        self.preview = ImagePreview(self._url, self)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.set_max_width(THUMB_PX)
        self.preview.setFixedSize(THUMB_PX, THUMB_PX)
        # 미리보기 자체의 클릭은 '주소 열기'라서 고르기와 충돌함 - 이 칸에서는 막는다
        self.preview.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        # 늘어난 자리는 아래로 몰아준다. 가운데 정렬로 두면 칸 높이가 커질 때 그림이
        # 가운데로 밀려서 이름과 사이가 벌어져 보였음
        column.addWidget(self.preview, 0, Qt.AlignmentFlag.AlignHCenter)

        label = QLabel()
        label.setObjectName("emojiName")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setFixedWidth(THUMB_PX)
        # 전체 칸에서 즐겨찾기에 이미 있는 것은 별을 붙인다 - 안 그러면 두 칸에 같은
        # 그림이 나오는 것이 '중복'처럼 보인다(실제로 그렇게 보였다)
        shown = self._name
        if shared and emoji_store.has_emoji(self._url):
            shown = f"★ {shown}" if shown else "★"
        label.setText(label.fontMetrics().elidedText(
            shown, Qt.TextElideMode.ElideRight, THUMB_PX - 4))
        column.addWidget(label, 0, Qt.AlignmentFlag.AlignHCenter)
        column.addStretch(1)
        self._name_label = label

        # 받아오는 일은 창고가 한다 - 같은 그림을 두 번 요청하지 않게
        images.want(self._url, self)

    def show_image(self, data):
        """창고가 그림을 건네줄 때 부른다."""
        self._show(data)

    def _show(self, data):
        if not self.preview.set_image_data(data):
            return
        self.preview.set_max_width(THUMB_PX)
        # 그림이 실제 크기로 줄어들면 자리도 그만큼만 차지하게 해서 이름이 바로 밑에 붙게 함
        self.preview.setMinimumSize(0, 0)
        self.preview.setMaximumSize(THUMB_PX, THUMB_PX)
        self.preview.setFixedSize(self.preview.size())

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.picked.emit(self._url)
        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event):
        import gui_client  # 지연 import - 이유는 gui/pages.py 맨 위 설명 참고

        menu = QMenu(self)
        if self._shared:
            # 다 같이 보는 목록이라 여기서 이름을 바꾸거나 빼면 안 된다.
            # 자주 쓰는 것만 즐겨찾기로 빼둘 수 있게 한다
            already = emoji_store.has_emoji(self._url)
            keep = menu.addAction("이미 즐겨찾기에 있음" if already else "즐겨찾기에 넣기")
            keep.setEnabled(not already)
            if menu.exec(event.globalPos()) is keep:
                saved, text = emoji_store.add_emoji(self._url, self._name)
                if not saved:
                    gui_client.themed_warning(self, "이모티콘", text)
                else:
                    self.changed.emit()      # 별이 바로 붙게
            return

        rename = menu.addAction("이름 바꾸기")
        remove = menu.addAction("즐겨찾기에서 빼기")
        chosen = menu.exec(event.globalPos())
        if chosen is rename:
            name, ok = gui_client.themed_get_text(
                self, "이름 바꾸기", f"'{self._name or self._url}'의 새 이름")
            if ok:
                emoji_store.rename_emoji(self._url, name)
                self.changed.emit()
        elif chosen is remove:
            if gui_client.themed_question(self, "이모티콘", "즐겨찾기에서 뺄까요?"):
                emoji_store.remove_emoji(self._url)
                self.changed.emit()
