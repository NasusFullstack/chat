"""다 같이 쓰는 이모티콘 목록 받아오기.

## 왜 같이 쓰나
이모티콘은 혼자 보려고 저장하는 게 아니라 **대화에 쓰려고** 저장하는 것이다. 한 사람이
좋은 짤을 챙겨두면 나머지는 그냥 꺼내 쓰면 되는데, 지금까지는 각자 따로 저장해야 했다.

## 어디까지 같이 쓰나 - 같은 채팅 서버를 쓰는 사람들
무리(group)는 (프로토콜, 호스트, 포트)를 해시한 24자다. 그래서 다른 서버를 쓰는 사람들
것이 섞이지 않고, 빌려 쓰는 중계 서버에 우리가 어디에 접속하는지 적히지도 않는다.

**이 목록은 그 값을 계산할 수 있는 사람이면 누구나 볼 수 있다.** 그건 같은 채팅 서버
주소를 아는 사람, 즉 같은 방에 들어올 수 있는 사람과 같은 범위다. 계정이 없는 중계
서버에서 그보다 좁히는 방법은 없으므로, **남에게 보이면 곤란한 그림은 저장하지 말 것.**

## 자주 묻지 않는다
이모티콘 창을 열 때마다 서버에 묻지 않고 잠깐 기억해둔다. 목록이 몇 분 늦게 바뀌어도
아무 문제가 없는 종류의 정보다.
"""
import json
import time

from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest

import relay

# 이 시간 안에 또 물으면 기억해둔 것을 그대로 쓴다
CACHE_SECONDS = 120

REQUEST_TIMEOUT_MS = 12_000


class SharedEmoji(QObject):
    """무리가 같이 쓰는 이모티콘 목록."""

    ready = Signal(list)       # [{"url": 주소, "name": 이름}, ...] 최근 것부터

    def __init__(self, parent=None):
        super().__init__(parent)
        self._manager = QNetworkAccessManager(self)
        self._items: list[dict] = []
        self._fetched_at = 0.0
        self._busy = False

    @property
    def items(self) -> list[dict]:
        return list(self._items)

    def fetch(self, group: str, force: bool = False):
        """목록을 받아온다. 방금 받아왔으면 그대로 돌려준다."""
        if not group:
            self.ready.emit([])
            return
        if not force and self._items and time.time() - self._fetched_at < CACHE_SECONDS:
            self.ready.emit(self.items)
            return
        if self._busy:
            return
        self._busy = True

        url = f"{relay.FILES_URL}/emoji?group={group}&limit=300"
        reply = self._manager.get(QNetworkRequest(QUrl(url)))
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(reply.abort)
        timer.start(REQUEST_TIMEOUT_MS)

        def done():
            timer.stop()
            self._busy = False
            items = []
            if reply.error() == reply.NetworkError.NoError:
                try:
                    answer = json.loads(bytes(reply.readAll()).decode("utf-8"))
                except (ValueError, UnicodeDecodeError):
                    answer = {}
                for entry in answer.get("emoji", []) or []:
                    if not isinstance(entry, dict) or not entry.get("url"):
                        continue
                    # 서버는 자기 안에서의 경로만 준다 - 여기서 온전한 주소로 만든다
                    items.append({"url": relay.SERVER + entry["url"],
                                  "name": _short(entry.get("name", ""))})
            reply.deleteLater()
            if items:
                self._items = items
                self._fetched_at = time.time()
            # 못 받아왔으면 **기억해둔 것을 그대로 보여준다.** 서버가 잠깐 닫혔다고
            # 목록이 텅 비어 보이면 저장한 게 날아간 줄 안다
            self.ready.emit(self.items)

        reply.finished.connect(done)


def _short(name: str) -> str:
    """보여줄 이름. 확장자는 떼어낸다(칸이 좁아서 이름이 잘린다)."""
    name = (name or "").strip()
    for suffix in (".png", ".gif", ".jpg", ".jpeg", ".webp"):
        if name.lower().endswith(suffix):
            return name[:-len(suffix)]
    return name
