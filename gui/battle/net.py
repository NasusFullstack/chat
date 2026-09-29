"""중계 서버와 주고받기 - 전투 중에만 연결한다.

**평소에는 아무 연결도 없다.** '배틀크루저 전투'를 친 순간에 붙었다가 판이 끝나면 끊는다.

인증서는 **보통의 CA 검증**을 쓴다. IRC 서버(`trusted_certs.py`)에 쓴 지문 고정(TOFU)을
여기 갖다 쓰면 안 된다 - 중계 서버는 Let's Encrypt 정식 인증서라 그럴 이유가 없고,
백신이 HTTPS를 가로채는 PC(ESET 등)에서는 지문이 사람마다 달라져 전부 막힌다.

받은 것은 **무조건 `battle_protocol.decode()`를 거친다.** 서버가 보낸 것도 남이 정한 값이다.
"""
from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtNetwork import QAbstractSocket
from PySide6.QtWebSockets import QWebSocket

import battle_protocol as bp

import relay

RELAY_URL = relay.BATTLE_URL

# 이 안에 못 붙으면 포기한다. 방화벽이 조용히 버리면 성공도 실패도 안 오고 매달린다
CONNECT_TIMEOUT_MS = 12_000


class BattleLink(QObject):
    """중계 서버와의 연결 하나. 소켓 사정은 전부 여기서 끝내고 위로는 신호만 올린다."""

    # 대기방
    joined = Signal(int, int, int, list, int)  # 내 자리, 색, 정원, 참가자, 연습 상대 수
    peer_joined = Signal(int, str, int)    # 자리, 이름, 색
    peer_left = Signal(int)                # 자리
    started = Signal()

    # 전투
    peer_input = Signal(int, int, int)     # 자리, 틱, 키
    peer_hit = Signal(int, int, int)       # 맞은 자리, 쏜 자리, 남은 체력
    peer_dead = Signal(int, int)           # 격추된 자리, 쏜 자리

    # 잘 안 됐을 때 - 조용히 실패하면 사람이 이유를 모른다
    refused = Signal(str)                  # 서버가 거절함(정원 참/이미 시작 등)
    failed = Signal(str)                   # 못 붙었거나 끊김

    def __init__(self, parent=None):
        super().__init__(parent)
        self._socket = QWebSocket()
        self._socket.connected.connect(self._on_connected)
        self._socket.textMessageReceived.connect(self._on_text)
        self._socket.disconnected.connect(self._on_disconnected)
        self._socket.errorOccurred.connect(self._on_error)
        self._timeout = QTimer(self)
        self._timeout.setSingleShot(True)
        self._timeout.timeout.connect(self._on_timeout)
        self._room = ""
        self._nick = ""
        self._color = 0
        self._cap = bp.MAX_HUMANS
        self._bots = 0
        self._my_slot = -1
        self._closing = False
        self._rejoining = False

    # ------------------------------------------------------------------
    @property
    def my_slot(self) -> int:
        """내 자리 번호. 아직 못 들어갔으면 -1."""
        return self._my_slot

    @property
    def room(self) -> str:
        return self._room

    def is_open(self) -> bool:
        return self._socket.state() == QAbstractSocket.SocketState.ConnectedState

    def join(self, room: str, nick: str, color: int = 0, cap: int = bp.MAX_HUMANS,
             bots: int = 0):
        """방에 들어간다. 여기서 비로소 연결이 생긴다."""
        self._room = room
        self._nick = nick
        self._color = color
        self._cap = cap
        self._bots = bots
        self._closing = False
        self._my_slot = -1
        self._timeout.start(CONNECT_TIMEOUT_MS)
        self._socket.open(QUrl(RELAY_URL))

    def rejoin(self, room: str, nick: str, color: int = 0, cap: int = bp.MAX_HUMANS,
               bots: int = 0):
        """자리를 다시 잡는다(색/정원을 바꿀 때). **끊김을 사고로 안 본다.**

        `leave()` 뒤에 바로 `join()`을 부르면, 뒤늦게 오는 '끊겼다'가 새 연결의 사고로
        읽혀 전투가 통째로 취소된다(실제로 그랬다). 다시 붙는 중이라는 표시를 두고
        그 구간의 끊김은 조용히 넘긴다.
        """
        self._rejoining = True
        if self.is_open():
            self._send({"t": bp.BYE})
        self._socket.abort()          # close()는 비동기라 신호가 새 연결 뒤에 온다
        self._rejoining = False
        self.join(room, nick, color=color, cap=cap, bots=bots)

    def leave(self):
        """판이 끝났다 - 확실히 닫는다(열어둔 채 잊히지 않게)."""
        self._closing = True
        self._timeout.stop()
        if self.is_open():
            self._send({"t": bp.BYE})
        self._socket.close()
        self._my_slot = -1

    # ------------------------------------------------------------------
    def start_battle(self):
        """시작하자(방을 연 사람만 먹힌다 - 서버가 판단한다)."""
        self._send({"t": bp.START})

    def send_input(self, tick: int, keys: int):
        """누른 키. **자리 번호는 안 보낸다** - 서버가 어느 연결로 왔는지 보고 붙인다."""
        self._send({"t": bp.INPUT, "tick": int(tick), "keys": int(keys) & bp.KEY_MASK})

    def send_hit(self, by: int, hp: int):
        """맞았다 - **남은 체력을 같이 보낸다**(받는 쪽이 얼마나 깎을지 몰라도 되게)."""
        self._send({"t": bp.HIT, "by": int(by), "hp": max(0, int(hp))})

    def send_dead(self, by: int):
        self._send({"t": bp.DEAD, "by": int(by), "hp": 0})

    # ---- 연습 상대(AI) - **방장만 보낸다.** 서버가 0번 자리인지 확인한다 ----
    def send_bot_input(self, slot: int, tick: int, keys: int):
        self._send({"t": bp.BOT_INPUT, "slot": int(slot), "tick": int(tick),
                    "keys": int(keys) & bp.KEY_MASK})

    def send_bot_hit(self, slot: int, by: int, hp: int):
        self._send({"t": bp.BOT_HIT, "slot": int(slot), "by": int(by),
                    "hp": max(0, int(hp))})

    def send_bot_dead(self, slot: int, by: int):
        self._send({"t": bp.BOT_DEAD, "slot": int(slot), "by": int(by), "hp": 0})

    # ------------------------------------------------------------------
    def _send(self, message: dict):
        if not self.is_open():
            return
        payload = bp.encode(message)
        if payload:
            self._socket.sendTextMessage(payload.decode("utf-8").rstrip("\n"))

    def _on_connected(self):
        self._timeout.stop()
        self._send({"t": bp.JOIN, "room": self._room, "nick": self._nick,
                    "color": self._color, "cap": self._cap, "bots": self._bots})

    def _on_timeout(self):
        if self.is_open():
            return
        self._socket.abort()
        self.failed.emit("전투 서버에 연결하지 못했습니다. 잠시 뒤 다시 시도해 주세요.")

    def _on_error(self, _error):
        if self._closing or self._rejoining:
            return
        self._timeout.stop()
        self.failed.emit(f"전투 서버 연결에 실패했습니다: {self._socket.errorString()}")

    def _on_disconnected(self):
        # 일부러 끊은 것(나가기/자리 다시 잡기)은 사고가 아니다.
        # **여기서 타임아웃을 끄면 안 된다** - 자리를 다시 잡는 중이면 새 연결의
        # 시간 제한까지 같이 꺼져서, 안 붙어도 영영 안 알려준다
        if self._closing or self._rejoining:
            return
        self._timeout.stop()
        self.failed.emit("전투 서버와의 연결이 끊겼습니다.")

    def _on_text(self, text: str):
        """받은 줄 하나. **반드시 규약 검사를 거친다** - 서버 말도 그대로 믿지 않는다."""
        message = bp.decode(text.encode("utf-8"))
        if message is None:
            return                     # 모르는 값은 조용히 버린다
        handler = self._HANDLERS.get(message["t"])
        if handler is not None:
            handler(self, message)

    # 새 종류가 생기면 여기 한 줄만 추가한다(if/elif 사슬을 만들지 않는다 - 코어와 같은 규칙)
    def _handle_welcome(self, message):
        self._my_slot = message["slot"]
        self._color = message["color"]
        self._cap = message["cap"]
        self._bots = message.get("bots", 0)
        self.joined.emit(message["slot"], message["color"], message["cap"],
                         message["players"], self._bots)
        if message["started"]:
            self.started.emit()

    def _handle_deny(self, message):
        self._closing = True
        self.refused.emit(message["why"])
        self._socket.close()

    def _handle_joined(self, message):
        self.peer_joined.emit(message["slot"], message["nick"], message["color"])

    def _handle_left(self, message):
        self.peer_left.emit(message["slot"])

    def _handle_started(self, _message):
        self.started.emit()

    def _handle_peer_input(self, message):
        self.peer_input.emit(message["slot"], message["tick"], message["keys"])

    def _handle_peer_hit(self, message):
        self.peer_hit.emit(message["slot"], message["by"], message["hp"])

    def _handle_peer_dead(self, message):
        self.peer_dead.emit(message["slot"], message["by"])

    _HANDLERS = {
        bp.WELCOME: _handle_welcome,
        bp.DENY: _handle_deny,
        bp.JOINED: _handle_joined,
        bp.LEFT: _handle_left,
        bp.STARTED: _handle_started,
        bp.PEER_INPUT: _handle_peer_input,
        bp.PEER_HIT: _handle_peer_hit,
        bp.PEER_DEAD: _handle_peer_dead,
    }
