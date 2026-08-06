"""참여자가 무슨 프로그램으로 접속했는지 보여주는 작은 로고.

상대가 CTCP VERSION으로 돌려준 문자열("WeeChat 4.4.2" 같은 것)을 보고 어느 프로그램인지
알아낸 뒤, 그 프로그램 로고를 참여자 목록 오른쪽 끝에 아주 작게 그린다.

로고를 어디서 가져오는가:
1. 우리 앱은 우리 아이콘 파일(icon.png)을 그대로 쓴다.
2. 나머지는 각 프로그램 공식 사이트의 파비콘을 **한 번만** 받아서 로컬에 저장한다.
   저장소에 남의 로고를 넣어두지 않으려는 것이기도 하다(상표 문제).
3. 못 받았거나 처음 보는 프로그램이면 **글자 배지**를 그린다(W, H, i ...).
   그래서 인터넷이 없어도 목록이 비어 보이지 않는다.

받아온 로고는 `client_logos.json`에 담아두므로 다음 실행부터는 바로 뜬다.
"""
import base64
import json
import os
import re
import sys

from PySide6.QtCore import QBuffer, QByteArray, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPixmap

from gui.helpers import _find_logo_image

# 닉네임 글자보다 커지면 안 된다. 줄 높이 24px, 글자 높이가 15px 남짓이라 12px로 둔다
CLIENT_BADGE_PX = 12
# 받아올 로고는 어차피 이 크기로 줄일 것이므로 큰 파일은 받을 이유가 없다
LOGO_FETCH_LIMIT_BYTES = 512 * 1024


class ClientSpec:
    """프로그램 하나를 알아보는 방법과, 그것을 어떻게 보여줄지.

    새 프로그램을 추가하려면 아래 CLIENT_SPECS에 한 줄 더하면 된다 - 이 파일 말고는
    아무 데도 안 고쳐도 된다.
    """

    def __init__(self, key: str, label: str, pattern: str, letter: str, color: str,
                 logo_url: str = ""):
        self.key = key
        self.label = label            # 사람에게 보여줄 이름(툴팁)
        self.regex = re.compile(pattern, re.IGNORECASE)
        self.letter = letter          # 로고를 못 구했을 때 그릴 글자
        self.color = color            # 그 프로그램의 대표색
        self.logo_url = logo_url

    def matches(self, version: str) -> bool:
        return bool(self.regex.search(version))


# 순서가 곧 우선순위다 - 위에서부터 먼저 맞는 것을 쓴다.
# (예: 디스코드 다리(matterbridge)는 WeeChat이라고 답하는 경우가 있어 위에 둔다)
CLIENT_SPECS = [
    ClientSpec("chupchat", "춥채팅", r"chupchat|춥채팅", "춥", "#7c6cf0"),
    ClientSpec("discord", "Discord", r"discord|matterbridge|bridge", "D", "#5865F2",
               "https://assets-global.website-files.com/6257adef93867e50d84d30e2/"
               "636e0a6a49cf127bf92de1e2_icon_clyde_blurple_RGB.png"),
    ClientSpec("weechat", "WeeChat", r"weechat", "W", "#57a64a",
               "https://weechat.org/favicon.ico"),
    ClientSpec("hexchat", "HexChat", r"hexchat", "H", "#3a7bd5",
               "https://hexchat.github.io/favicon.ico"),
    ClientSpec("irssi", "irssi", r"irssi", "i", "#c4a000",
               "https://irssi.org/favicon.ico"),
    ClientSpec("mirc", "mIRC", r"\bmirc\b", "m", "#d24726",
               "https://www.mirc.com/favicon.ico"),
    ClientSpec("thelounge", "The Lounge", r"the ?lounge", "L", "#31a2f2",
               "https://thelounge.chat/favicon.ico"),
    ClientSpec("kiwi", "Kiwi IRC", r"kiwi", "K", "#42b3a5",
               "https://kiwiirc.com/favicon.ico"),
    ClientSpec("textual", "Textual", r"textual", "T", "#4f8ef7"),
    ClientSpec("quassel", "Quassel", r"quassel", "Q", "#8a6fbf"),
    ClientSpec("konversation", "Konversation", r"konversation", "K", "#1d99f3"),
    ClientSpec("kvirc", "KVIrc", r"kvirc", "K", "#c0392b"),
    ClientSpec("halloy", "Halloy", r"halloy", "h", "#e6a44b"),
    ClientSpec("goguma", "Goguma", r"goguma", "g", "#e07a5f"),
    ClientSpec("senpai", "senpai", r"senpai", "s", "#9b5de5"),
    ClientSpec("znc", "ZNC", r"\bznc\b", "Z", "#6b7079"),
]
UNKNOWN_COLOR = "#6e7185"


def spec_for(version: str) -> ClientSpec | None:
    """응답 문자열에서 어느 프로그램인지 알아낸다. 모르면 None."""
    if not version:
        return None
    for spec in CLIENT_SPECS:
        if spec.matches(version):
            return spec
    return None


# 닉네임만 보고 짐작해도 되는 것들. 다리(bridge) 계정은 보통 이름 자체가 Discord다.
# 응답으로 알아내지 못했을 때만 쓰는 보조 수단이라 아주 확실한 것만 넣는다
NICK_HINTS = (("discord", "discord"), ("matterbridge", "discord"))


def spec_for_nick(nick: str) -> ClientSpec | None:
    """이름만 보고 짐작. 응답으로 못 알아냈을 때만 쓴다."""
    if not nick:
        return None
    lowered = nick.lower()
    for needle, key in NICK_HINTS:
        if needle in lowered:
            for spec in CLIENT_SPECS:
                if spec.key == key:
                    return spec
    return None


def resolve_spec(version: str, nick: str = "") -> ClientSpec | None:
    """어느 프로그램인지 판단. **이름 힌트를 먼저 본다.**

    다리(bridge) 계정은 CTCP에 자기가 쓰는 라이브러리 이름을 답한다 - 실측하니
    디스코드 다리가 "girc (github.com/lrstanley/girc) using go1.19.5"라고 답했다.
    그 답을 그대로 믿으면 "girc"라는 낯선 이름이 뜨므로, 이름이 Discord인 계정은
    이름 쪽을 믿는다.
    """
    return spec_for_nick(nick) or spec_for(version)


def short_label(version: str, nick: str = "") -> str:
    """툴팁에 쓸 짧은 이름. 아는 프로그램이면 그 이름, 모르면 응답의 첫 낱말."""
    spec = resolve_spec(version, nick)
    if spec is not None:
        return spec.label
    return version.split()[0] if version.split() else version


def _initial(version: str) -> str:
    """모르는 프로그램의 배지에 쓸 한 글자 - 응답의 첫 글자(없으면 물결표)."""
    stripped = (version or "").strip()
    return stripped[0].upper() if stripped else "~"


def _app_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


LOGO_STORE_FILE = os.path.join(_app_dir(), "client_logos.json")


class ClientBadges:
    """프로그램별 작은 로고를 만들어 주는 곳(받아오기 + 저장 + 그리기).

    화면 부품이 아니라 '그림을 구해다 주는 사람'이다. 로고가 나중에 도착하면
    on_ready(키)로 알려주고, 그리는 쪽은 그때 다시 그리기만 하면 된다.
    """

    def __init__(self, fetcher=None, on_ready=None):
        self._fetcher = fetcher
        self._on_ready = on_ready
        self._pixmaps: dict[str, QPixmap] = {}    # 키 -> 이미 만들어 둔 배지
        self._requested: set[str] = set()          # 이미 받아오기를 시도한 것
        self._stored = _load_stored()

    def badge(self, version: str, size: int = CLIENT_BADGE_PX,
              nick: str = "") -> QPixmap | None:
        """그 사람의 프로그램 로고. 모르면 글자 배지, 그것도 안 되면 None."""
        spec = resolve_spec(version, nick)
        # 모르는 프로그램이면 응답의 첫 글자를 쓴다. 예전엔 물음표를 그렸는데 12px에서
        # 곡선이 뭉개져 숫자 7처럼 보였다(실제로 그렇게 보인다는 신고를 받음).
        # 첫 글자를 쓰면 뭉개져도 최소한 무엇의 앞글자인지는 짐작할 수 있다
        key = spec.key if spec is not None else f"unknown:{_initial(version)}"
        cached = self._pixmaps.get((key, size))
        if cached is not None:
            return cached

        pixmap = self._build(spec, key, size, version)
        if pixmap is not None:
            self._pixmaps[(key, size)] = pixmap
        return pixmap

    def _build(self, spec, key: str, size: int, version: str = "") -> QPixmap | None:
        if key == "chupchat":
            ours = _our_icon(size)
            if ours is not None:
                return ours
        stored = self._stored.get(key)
        if stored:
            pixmap = _pixmap_from_b64(stored, size)
            if pixmap is not None:
                return pixmap
        if spec is not None:
            self._fetch_logo(spec)
            return _letter_badge(spec.letter, spec.color, size)
        return _letter_badge(_initial(version), UNKNOWN_COLOR, size)

    def _fetch_logo(self, spec: ClientSpec):
        """공식 사이트에서 로고를 한 번만 받아온다(다음 실행부터는 저장된 것을 씀)."""
        if (self._fetcher is None or not spec.logo_url or spec.key in self._requested
                or spec.key in self._stored):
            return
        self._requested.add(spec.key)

        def done(data):
            if not data:
                return
            pixmap = QPixmap()
            if not pixmap.loadFromData(data) or pixmap.isNull():
                return
            self._stored[spec.key] = _b64_from_pixmap(pixmap)
            _save_stored(self._stored)
            self._pixmaps.clear()      # 글자 배지로 만들어 둔 것을 버리고 다시 만들게 함
            if self._on_ready is not None:
                self._on_ready(spec.key)

        self._fetcher.fetch(spec.logo_url, done, limit=LOGO_FETCH_LIMIT_BYTES)


def _our_icon(size: int) -> QPixmap | None:
    path = _find_logo_image()
    if not path:
        return None
    pixmap = QPixmap(path)
    if pixmap.isNull():
        return None
    return pixmap.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                         Qt.TransformationMode.SmoothTransformation)


def _letter_badge(letter: str, color: str, size: int) -> QPixmap:
    """로고를 못 구했을 때 쓰는, 글자 한 자짜리 둥근 배지."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    path = QPainterPath()
    path.addRoundedRect(QRectF(0.5, 0.5, size - 1, size - 1), size / 4, size / 4)
    painter.fillPath(path, QColor(color))
    font = QFont()
    font.setPixelSize(max(7, int(size * 0.66)))
    font.setBold(True)
    painter.setFont(font)
    painter.setPen(QColor("#ffffff"))
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, letter[:1])
    painter.end()
    return pixmap


def _pixmap_from_b64(data_b64: str, size: int) -> QPixmap | None:
    try:
        raw = base64.b64decode(data_b64.encode("ascii"))
    except (ValueError, UnicodeEncodeError):
        return None
    pixmap = QPixmap()
    if not pixmap.loadFromData(raw) or pixmap.isNull():
        return None
    return pixmap.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                         Qt.TransformationMode.SmoothTransformation)


def _b64_from_pixmap(pixmap: QPixmap) -> str:
    """받은 그림을 저장용 문자열로. 배지 크기보다 조금 크게만 남겨 파일이 안 커지게 한다."""
    # 12px로 그릴 것이지만 저장은 64px로 - 원본을 한 번에 12px로 줄이면 뭉개진다.
    # 큰 것을 두고 그릴 때 부드럽게 줄이는 편이 훨씬 깔끔하다
    small = pixmap.scaled(64, 64, Qt.AspectRatioMode.KeepAspectRatio,
                          Qt.TransformationMode.SmoothTransformation)
    buffer = QBuffer()       # QBuffer(QByteArray())처럼 임시 객체를 넘기면 접근 위반으로 죽는다
    buffer.open(QBuffer.OpenModeFlag.WriteOnly)
    small.save(buffer, "PNG")
    return base64.b64encode(bytes(buffer.data())).decode("ascii")


def _load_stored() -> dict:
    if not os.path.exists(LOGO_STORE_FILE):
        return {}
    try:
        with open(LOGO_STORE_FILE, "r", encoding="utf-8") as fp:
            data = json.load(fp)
    except (json.JSONDecodeError, OSError):
        return {}
    return {k: v for k, v in data.items() if isinstance(v, str)} if isinstance(data, dict) else {}


def _save_stored(store: dict) -> None:
    try:
        with open(LOGO_STORE_FILE, "w", encoding="utf-8") as fp:
            json.dump(store, fp)
    except OSError:
        pass
