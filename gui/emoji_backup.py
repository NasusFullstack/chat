"""보관함에 이미 있는 이모티콘을 중계 서버로 옮겨 담기(백업).

## 왜 필요한가
보관함은 지금까지 **주소만** 적어뒀다. 그 주소들은 남의 사이트나 채팅에 올라온 그림을
가리키는데, 그림이 사라지면 이모티콘도 같이 깨진다. 이미 쓰고 있던 것들이라 더 아깝다.

그래서 한 번 훑으면서 그림을 받아 서버에 이모티콘으로 등록하고, 보관함이 그 새 주소를
보게 바꾼다. 원래 주소는 `from`에 남는다.

## 조용히, 천천히
사람이 시켜서 하는 일이 아니므로 방해하면 안 된다:
- **한 번에 하나씩**, 사이를 두고 한다. 200개를 한꺼번에 받으면 채팅이 버벅인다
- 이미 우리 서버를 가리키는 것은 건너뛴다. 그래서 몇 번을 다시 돌려도 헛일을 안 한다
- 실패해도 그냥 넘어간다. 다음에 켤 때 다시 해보면 된다(원본이 살아 있는 한)
- 아무것도 옮길 게 없으면 시작조차 안 한다

## 왜 다 끝난 뒤에 한 번만 알리나
하나 옮길 때마다 채팅에 한 줄씩 남기면 그게 더 시끄럽다. 끝나고 몇 개를 챙겼는지만
한 줄로 알린다.
"""
from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest

import emoji_store
import link_meta
import relay
from gui.uploader import Uploader

# 하나 끝내고 다음까지 쉬는 시간. 서두를 이유가 전혀 없는 일이다
GAP_MS = 2_500

# 채팅을 열고 이만큼 지난 뒤에 시작한다(들어가자마자는 화면 그리느라 바쁘다)
START_DELAY_MS = 20_000

DOWNLOAD_TIMEOUT_MS = 20_000

# 받아볼 원본 그림의 크기 상한. 이모티콘으로 쓰던 것이라 클 이유가 없고,
# 엉뚱하게 큰 것을 받다가 오래 매달리지 않게 한다
MAX_SOURCE_BYTES = 32 * 1024 * 1024


def needs_backup(item: dict) -> bool:
    """이 항목을 서버로 옮겨야 하는가."""
    url = (item.get("url") or "").strip()
    if not url or url.startswith(f"{relay.SERVER}/files/"):
        return False       # 이미 우리 서버에 있다
    return link_meta.is_safe_public_url(url)


class EmojiBackup(QObject):
    """보관함을 훑으며 하나씩 서버로 옮긴다."""

    finished = Signal(int, int)    # 옮긴 개수, 옮기려 했던 개수

    def __init__(self, parent=None):
        super().__init__(parent)
        self._manager = QNetworkAccessManager(self)
        self._uploader = Uploader(self)
        self._uploader.finished.connect(self._uploaded)
        self._todo: list[dict] = []
        self._total = 0
        self._moved = 0
        self._current = None
        self._running = False

    def start_later(self):
        """옮길 게 있으면 조금 뒤에 시작한다."""
        if self._running:
            return
        self._todo = [item for item in emoji_store.load_emojis() if needs_backup(item)]
        if not self._todo:
            return
        self._total = len(self._todo)
        self._moved = 0
        self._running = True
        QTimer.singleShot(START_DELAY_MS, self._next)

    def _next(self):
        if not self._todo:
            self._running = False
            # 옮겨 담고 나면 같은 그림이 둘이 될 수 있다 - 주소가 달라서 따로 들어와
            # 있던 것들이 서버에서 같은 주소로 합쳐지기 때문이다
            emoji_store.dedupe()
            self.finished.emit(self._moved, self._total)
            return
        self._current = self._todo.pop(0)
        self._download(self._current["url"])

    def _later(self):
        """이번 건은 끝났다(됐든 안 됐든). 쉬었다가 다음 것."""
        QTimer.singleShot(GAP_MS, self._next)

    # ------------------------------------------------------------ 받기
    def _download(self, url: str):
        reply = self._manager.get(QNetworkRequest(QUrl(url)))
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(reply.abort)
        timer.start(DOWNLOAD_TIMEOUT_MS)

        def got():
            timer.stop()
            data = bytes(reply.readAll()) if reply.error() == reply.NetworkError.NoError else b""
            reply.deleteLater()
            # 원본이 이미 사라졌으면 어쩔 수 없다. 보관함에는 그대로 두고 넘어간다
            # (지우면 사람이 "왜 없어졌지" 하게 된다)
            if not data or len(data) > MAX_SOURCE_BYTES or not link_meta.looks_like_image(data):
                self._later()
                return
            name = (self._current.get("name") or "이모티콘")
            self._uploader.upload_bytes(data, f"{name}.png", kind="emoji")

        reply.finished.connect(got)

    # ------------------------------------------------------------ 올리기
    def _uploaded(self, url: str, _note: str):
        if url and self._current:
            if emoji_store.replace_url(self._current["url"], url):
                self._moved += 1
        self._later()
