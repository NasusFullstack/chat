"""참여자 프로필을 중계 서버로 주고받기 - 상대가 없어도 얼굴이 보이게.

## 무엇을 푸는가
아이콘은 지금까지 **채팅 통로로** 오갔다. IRC는 한 줄이 512바이트를 못 넘어서 아이콘
하나를 300자씩 쪼개 보내야 했고(CLAUDE.md 2-2), 조각이 하나라도 빠지면 아무것도 안 떴다.
게다가 **상대가 접속해 있어야만** 받을 수 있어서, 새로 들어온 사람이 생길 때마다 모두가
자기 아이콘을 다시 뿌려야 했다.

여기 두면 조각낼 일이 없고, 그 사람이 지금 없어도 얼굴을 볼 수 있다.

## 채팅으로 주고받는 길은 그대로 둔다
`chat_core/protocols/irc.py`의 CTCP 아바타 코드는 **하나도 안 건드렸다.** 중계 서버가
내려갔거나 상대가 옛 버전이면 지금처럼 동작해야 하고, 나중에 다시 쓸 수도 있다.
둘 다 들어오면 나중에 온 것이 이긴다 - 둘 다 그 사람이 스스로 올린 것이라 우열이 없다.

## 내 얼굴을 남이 못 바꾸게
중계 서버에는 계정이 없다. 채팅 통로로 주고받을 때는 IRC 서버가 닉네임을 지켜줬는데,
여기로 옮기면서 그 보호가 사라진다. 그래서 처음 올릴 때 서버가 주는 표(token)를 받아
**내 컴퓨터에 적어두고** 다음부터 같이 보낸다. 표가 없으면 서버가 안 고쳐준다.

## 물어보는 횟수를 아낀다
참여자 여섯이면 요청도 여섯 번이 된다. 한 번에 묶어 묻고, **한 번 받아온 사람은 다시
묻지 않는다**(CTCP VERSION을 아껴 묻는 것과 같은 이유).
"""
import json
import os

from PySide6.QtCore import QByteArray, QObject, QTimer, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest

import app_paths
import relay

TOKEN_FILE = os.path.join(app_paths.data_dir(), "profile_tokens.json")

# 서버가 한 번에 받아주는 수(features/profiles.py의 batch_size와 맞춘 값)
MAX_LOOKUP = 60

REQUEST_TIMEOUT_MS = 15_000

# 참여자 목록이 바뀔 때마다 곧바로 묻지 않고 조금 모은다(들락거릴 때 요청이 쏟아진다)
LOOKUP_DELAY_MS = 900


def load_tokens() -> dict[str, str]:
    try:
        with open(TOKEN_FILE, encoding="utf-8") as fp:
            saved = json.load(fp)
        return saved if isinstance(saved, dict) else {}
    except (OSError, ValueError):
        return {}


def save_token(who: str, token: str):
    """표를 잃으면 내 얼굴을 내가 못 고치게 되므로 반드시 남긴다."""
    if not who or not token:
        return
    tokens = load_tokens()
    if tokens.get(who) == token:
        return
    tokens[who] = token
    try:
        os.makedirs(os.path.dirname(TOKEN_FILE), exist_ok=True)
        with open(TOKEN_FILE, "w", encoding="utf-8") as fp:
            json.dump(tokens, fp)
    except OSError:
        pass


class ProfileSync(QObject):
    """내 프로필을 올리고, 남의 프로필을 받아온다."""

    profile_known = Signal(str, str, str)   # 닉네임, 아이콘(base64), 표시이름

    def __init__(self, protocol: str, host: str, port: int, parent=None):
        super().__init__(parent)
        self._protocol = protocol
        self._host = host
        self._port = port
        self._manager = QNetworkAccessManager(self)
        self._asked: set[str] = set()      # 이미 물어본 사람 - 다시 안 묻는다
        self._pending: list[str] = []
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(LOOKUP_DELAY_MS)
        self._timer.timeout.connect(self._ask_now)

    # ------------------------------------------------------------ 올리기
    def publish(self, nick: str, avatar_b64: str):
        """내 프로필을 올린다. 처음이면 서버가 주는 표를 받아 적어둔다."""
        if not nick:
            return
        who = self._who(nick)
        body = {"nick": nick, "avatar": avatar_b64 or "",
                "token": load_tokens().get(who, "")}
        request = QNetworkRequest(QUrl(f"{relay.PROFILES_URL}/{who}"))
        request.setHeader(QNetworkRequest.KnownHeaders.ContentTypeHeader, "application/json")
        reply = self._manager.put(
            request, QByteArray(json.dumps(body, ensure_ascii=False).encode("utf-8")))
        self._guard(reply)

        def done():
            if reply.error() == reply.NetworkError.NoError:
                try:
                    answer = json.loads(bytes(reply.readAll()).decode("utf-8"))
                except (ValueError, UnicodeDecodeError):
                    answer = {}
                save_token(who, answer.get("token", ""))
            reply.deleteLater()

        reply.finished.connect(done)

    # ---------------------------------------------------------- 받아오기
    def want(self, nicks):
        """이 사람들 얼굴이 필요하다. 이미 물어본 사람은 알아서 건너뛴다."""
        fresh = [nick for nick in nicks
                 if nick and nick not in self._asked and nick not in self._pending]
        if not fresh:
            return
        self._pending.extend(fresh)
        self._timer.start()

    def forget(self, nick: str):
        """그 사람 얼굴을 다시 물어보게 한다(프로필을 바꿨다는 걸 알았을 때)."""
        self._asked.discard(nick)

    def _ask_now(self):
        batch, self._pending = self._pending[:MAX_LOOKUP], self._pending[MAX_LOOKUP:]
        if not batch:
            return
        self._asked.update(batch)
        by_id = {self._who(nick): nick for nick in batch}
        request = QNetworkRequest(QUrl(f"{relay.PROFILES_URL}/lookup"))
        request.setHeader(QNetworkRequest.KnownHeaders.ContentTypeHeader, "application/json")
        body = QByteArray(json.dumps({"who": list(by_id)}).encode("utf-8"))
        reply = self._manager.post(request, body)
        self._guard(reply)

        def done():
            if reply.error() == reply.NetworkError.NoError:
                try:
                    answer = json.loads(bytes(reply.readAll()).decode("utf-8"))
                    found = answer.get("profiles", {})
                except (ValueError, UnicodeDecodeError):
                    found = {}
                if isinstance(found, dict):
                    for who, profile in found.items():
                        nick = by_id.get(who)
                        if nick and isinstance(profile, dict) and profile.get("avatar"):
                            self.profile_known.emit(nick, profile["avatar"],
                                                    profile.get("nick", ""))
            reply.deleteLater()
            if self._pending:
                self._timer.start()

        reply.finished.connect(done)

    # ------------------------------------------------------------ 도구
    def _who(self, nick: str) -> str:
        return relay.who_id(self._protocol, self._host, self._port, nick)

    def _guard(self, reply):
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(reply.abort)
        timer.start(REQUEST_TIMEOUT_MS)
        reply.finished.connect(timer.stop)
