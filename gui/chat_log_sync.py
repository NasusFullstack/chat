"""놓친 대화 따라잡기 - 받아본 줄을 중계 서버에 올리고, 다시 켤 때 빈 자리를 받아온다.

## 무엇을 푸는가
지금까지 대화는 **자기 컴퓨터에만** 쌓였다(history.json). 그래서 앱을 꺼둔 동안 오간
이야기는 다시 켜도 볼 수 없다 - 그 시간만 통째로 비어 있다.

여기서 하는 일은 둘뿐이다:
  올리기   내가 받아본 줄을 모아서 이따금 한 번에 올린다
  받아오기 채널에 들어갈 때, 내가 마지막으로 본 시각 뒤엣것만 받아온다

## 모아서 올리는 이유
말 한마디마다 요청을 하나씩 보내면 수다 떨 때 서버로 나가는 요청이 그대로 대화 속도가
된다. 몇 초 모았다가 한 번에 보낸다. 앱을 닫을 때는 모아둔 것을 마지막으로 한 번 밀어낸다
(안 그러면 방금 나눈 대화가 통째로 안 올라간다).

## 내가 보낸 말도 올린다
내 말이 빠지면 남이 받아갈 기록에 구멍이 생긴다("쟤 혼자 떠들었네"처럼 보인다).

## 같은 말을 연달아 두 번 한 경우
서버는 짧은 시간 안의 같은 말을 한 줄로 본다(사람마다 받은 시각이 다르기 때문). 그래서
"ㅋㅋ"를 두 번 치면 한 줄로 뭉칠 수 있다 - 창 안에서 몇 번째로 본 같은 말인지를 `seq`로
붙여 보낸다. 두 번 본 사람은 0,1을 붙이고 한 번 본 사람은 0을 붙이므로 서로 어긋나지 않는다.

## 못 올려도 아무 일도 안 일어나야 한다
중계 서버는 있으면 좋은 것이지 없으면 안 되는 것이 아니다. 실패는 조용히 넘어가고
채팅은 그대로 돌아간다.
"""
import json
import time

from PySide6.QtCore import QByteArray, QObject, QTimer, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest

import relay

# 모아서 보내는 간격과, 기다리지 않고 바로 보내는 줄 수
FLUSH_MS = 6_000
FLUSH_LINES = 40

# 서버가 한 번에 받아주는 줄 수(features/logs.py의 post_lines와 맞춘 값)
MAX_LINES_PER_POST = 200

# 올리려고 들고 있을 수 있는 최대 줄 수. 서버가 오래 닫혀 있어도 메모리가 늘지 않게
QUEUE_LIMIT = 1000

REQUEST_TIMEOUT_MS = 15_000

# 서버가 같은 줄로 보는 시간 창(features/logs.py의 same_line_seconds와 맞춘 값).
# 이 안에 든 같은 말에만 seq를 매긴다
SAME_LINE_SECONDS = 5.0


class ChatLogSync(QObject):
    """채널별로 올리고 받아온다. 화면은 신호로만 안다."""

    missed = Signal(str, list)     # 채널, 놓쳤던 줄들(시간 순)

    def __init__(self, protocol: str, host: str, port: int, parent=None):
        super().__init__(parent)
        self._protocol = protocol
        self._host = host
        self._port = port
        self._manager = QNetworkAccessManager(self)
        self._queued: dict[str, list[dict]] = {}
        self._recent: dict[str, list[dict]] = {}   # seq를 매기려고 최근 줄만 기억
        self._timer = QTimer(self)
        self._timer.setInterval(FLUSH_MS)
        self._timer.timeout.connect(self.flush)

    # ------------------------------------------------------------ 올리기
    def record(self, channel: str, sender: str, text: str, ts: float | None = None):
        """받아본 줄 하나를 올릴 목록에 넣는다."""
        if not channel or not sender or not text:
            return
        when = time.time() if ts is None else float(ts)
        line = {"ts": when, "sender": sender, "text": text,
                "seq": self._seq_for(channel, sender, text, when)}
        queue = self._queued.setdefault(channel, [])
        queue.append(line)
        if len(queue) > QUEUE_LIMIT:
            # 넘치면 **오래된 것부터** 버린다. 최근 것이 따라잡는 데 더 쓸모 있다
            del queue[:len(queue) - QUEUE_LIMIT]
        if len(queue) >= FLUSH_LINES:
            self.flush()
        elif not self._timer.isActive():
            self._timer.start()

    def _seq_for(self, channel: str, sender: str, text: str, when: float) -> int:
        """창 안에서 몇 번째로 본 같은 말인가.

        서버가 짧은 시간 안의 같은 말을 한 줄로 보기 때문에 필요하다(사람마다 받은 시각이
        다르므로 시각으로는 못 가른다). 이 번호는 **받은 순서만** 타므로, 같은 대화를 본
        사람들은 서로 같은 번호를 매긴다.
        """
        recent = self._recent.setdefault(channel, [])
        cutoff = when - SAME_LINE_SECONDS
        recent[:] = [line for line in recent if line["ts"] >= cutoff]
        seq = sum(1 for line in recent
                  if line["sender"] == sender and line["text"] == text)
        recent.append({"ts": when, "sender": sender, "text": text})
        return min(seq, 99)

    def flush(self):
        """모아둔 것을 채널마다 한 번씩 보낸다."""
        self._timer.stop()
        for channel, queue in list(self._queued.items()):
            if not queue:
                continue
            batch, self._queued[channel] = queue[:MAX_LINES_PER_POST], queue[MAX_LINES_PER_POST:]
            self._post(channel, batch)
            if self._queued[channel]:
                self._timer.start()   # 남은 것은 다음 차례에

    def _post(self, channel: str, lines: list[dict]):
        url = f"{relay.LOGS_URL}/{self._room(channel)}"
        request = QNetworkRequest(QUrl(url))
        request.setHeader(QNetworkRequest.KnownHeaders.ContentTypeHeader, "application/json")
        body = QByteArray(json.dumps({"lines": lines}, ensure_ascii=False).encode("utf-8"))
        reply = self._manager.post(request, body)
        self._guard(reply)
        # 올리기는 **결과를 안 본다.** 실패해도 사람이 할 수 있는 일이 없고, 안내를
        # 띄우면 서버가 잠깐 닫힐 때마다 채팅창이 경고로 덮인다
        reply.finished.connect(reply.deleteLater)

    # ---------------------------------------------------------- 받아오기
    def fetch(self, channel: str, since: float):
        """마지막으로 본 시각 뒤엣것을 받아온다. 끝나면 missed(채널, 줄들)."""
        url = f"{relay.LOGS_URL}/{self._room(channel)}?since={since:.3f}"
        reply = self._manager.get(QNetworkRequest(QUrl(url)))
        self._guard(reply)

        def done():
            lines = []
            if reply.error() == reply.NetworkError.NoError:
                try:
                    answer = json.loads(bytes(reply.readAll()).decode("utf-8"))
                    lines = [line for line in answer.get("lines", [])
                             if isinstance(line, dict) and line.get("text")]
                except (ValueError, UnicodeDecodeError):
                    lines = []
            reply.deleteLater()
            if lines:
                lines.sort(key=lambda line: line.get("ts", 0))
                self.missed.emit(channel, lines)

        reply.finished.connect(done)

    # ------------------------------------------------------------ 도구
    def _room(self, channel: str) -> str:
        return relay.room_id(self._protocol, self._host, self._port, channel)

    def _guard(self, reply):
        """매달려 있지 않게 시간 제한을 건다."""
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(reply.abort)
        timer.start(REQUEST_TIMEOUT_MS)
        reply.finished.connect(timer.stop)

    def stop(self):
        """앱을 닫을 때 - 모아둔 것을 마지막으로 밀어낸다."""
        self.flush()
