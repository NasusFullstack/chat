"""순수 헬퍼 함수 모음 - 전부 몽키패치 대상이 아니라 어디서든 자유롭게 직접 import해도 안전함
(gui_client.py의 순환참조 노트 참고 - 패치되는 건 다른 5개 함수뿐)."""
import base64
import binascii
import datetime
import hashlib
import os
import re
import sys

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap

from gui.theme import AVATAR_GRID_SIZE, UNREAD_DOT_PX

_MENTION_TOKEN_RE = re.compile(r"@([^\s@]+)")


def _app_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    # 이 파일은 gui/helpers.py라 저장소 루트(gui_client.py가 있는 곳)보다 한 단계 아래에
    # 있음 - 원래 gui_client.py에 있을 때는 os.path.dirname(os.path.abspath(__file__))
    # 한 번이면 됐지만, 여기서는 한 번 더 올라가야 저장소 루트가 나옴
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _find_default_cert() -> str:
    candidate = os.path.join(_app_dir(), "cert.pem")
    return candidate if os.path.exists(candidate) else ""


def _format_ts(ts: float) -> str:
    return datetime.datetime.fromtimestamp(ts).strftime("%H:%M")


_URL_PATTERN = re.compile(r'((?:https?://|www\.)[^\s<>"]+)')

# 한 메시지에서 미리보기를 만들 최대 개수. 링크를 잔뜩 붙인 메시지 하나가 채팅창을
# 통째로 차지하거나 네트워크 요청을 몰아치게 하지 않도록 상한을 둠
MAX_PREVIEW_URLS = 3


def text_is_only_urls(text: str) -> bool:
    """메시지가 링크(들)로만 이루어져 있는지.

    이런 메시지는 미리보기가 뜨고 나면 주소 문자열을 굳이 같이 보여줄 이유가 없다
    (긴 주소가 몇 줄씩 차지하기만 함). 미리보기 그림/카드를 눌러 열 수 있으므로
    주소를 지워도 못 여는 일은 없다."""
    stripped = text.strip()
    if not stripped:
        return False
    return not _URL_PATTERN.sub(" ", stripped).strip()


def extract_urls(text: str) -> list[str]:
    """원문(이스케이프 전) 텍스트에서 미리보기를 시도할 URL들을 뽑음.

    _linkify와 같은 패턴을 쓰되, 문장 끝의 마침표/괄호는 링크에서 떼어냄
    (안 떼면 '...입니다.' 같은 문장에서 마침표까지 주소에 붙어 요청이 실패함).
    """
    urls = []
    for raw in _URL_PATTERN.findall(text):
        while raw and raw[-1] in ".,!?)]}'\"":
            raw = raw[:-1]
        if not raw:
            continue
        url = raw if raw.startswith("http") else f"http://{raw}"
        if url not in urls:
            urls.append(url)
        if len(urls) >= MAX_PREVIEW_URLS:
            break
    return urls


def _linkify(escaped_text: str) -> str:
    """이미 &lt;/&gt;로 이스케이프된 텍스트 안의 URL을 클릭 가능한 링크로 감쌈."""

    def repl(match: re.Match) -> str:
        raw = match.group(1)
        trailing = ""
        while raw and raw[-1] in ".,!?)]}'\"":
            trailing = raw[-1] + trailing
            raw = raw[:-1]
        if not raw:
            return match.group(0)
        href = raw if raw.startswith("http") else f"http://{raw}"
        return f'<a href="{href}" style="color:#7ec8ff; text-decoration:underline;">{raw}</a>{trailing}'

    return _URL_PATTERN.sub(repl, escaped_text)


# Qt(Schannel)가 인증서를 신뢰 못 할 때 내는 원본 오류 메시지에 등장하는 키워드들.
# 개인/소규모 서버는 자체 서명 인증서를 쓰는 경우가 흔해서 이 실패가 가장 잦은
# SSL 연결 실패 원인이므로, 원인과 해결 방법을 한글로 명확히 안내한다.
_SSL_TRUST_ERROR_KEYWORDS = (
    "root ca", "not trusted", "self signed", "self-signed",
    "certificate", "untrusted", "unable to verify",
)


def _friendly_connection_error(err: str, use_ssl: bool, cert_pinned: bool) -> str:
    if use_ssl and not cert_pinned and any(k in err.lower() for k in _SSL_TRUST_ERROR_KEYWORDS):
        return (
            "SSL 인증서를 신뢰할 수 없어 연결에 실패했습니다. "
            "개인 서버는 정식 인증기관이 아닌 자체 서명(self-signed) 인증서를 쓰는 경우가 많아요. "
            "서버 관리자에게 cert.pem 파일을 받아 위 'cert.pem 경로'에 등록하면 해결됩니다. "
            "그럴 수 없고 서버를 신뢰한다면 SSL을 끄고 평문 포트로 접속해보세요. "
            f"(원본 오류: {err})"
        )
    return f"연결 실패: {err}"


def _decode_avatar_pixmap(avatar_b64: str) -> QPixmap | None:
    """base64 PNG를 QPixmap으로. 형식이 잘못됐거나 비어있으면 None (호출부가 기본 도트로 대체)."""
    if not avatar_b64:
        return None
    try:
        raw = base64.b64decode(avatar_b64, validate=True)
    except (binascii.Error, ValueError):
        return None
    pixmap = QPixmap()
    if not pixmap.loadFromData(raw, "PNG"):
        return None
    return pixmap


def _hashed_avatar_pixmap(user_id: str) -> QPixmap:
    """아이콘을 안 그린 사람용 기본 도트 - 아이디로부터 안정적인 색상을 계산해 사람마다 다르게."""
    digest = hashlib.md5(user_id.encode("utf-8")).digest()
    hue = digest[0] / 255 * 359
    color = QColor.fromHsl(int(hue), 160, 130)

    size = AVATAR_GRID_SIZE
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(color)
    painter.drawEllipse(0, 0, size, size)
    painter.end()
    return pixmap


def _build_unread_dot_icon(color: str) -> QIcon:
    """탭 안 읽음 표시용 점 아이콘. QTabBar::tab { color: ... }를 QSS에 못박아둬서
    QTabBar.setTabTextColor()로는 글자색이 절대 안 바뀌길래(스타일시트가 항상 우선함),
    스타일시트 영향을 안 받는 아이콘으로 깜빡이게 함"""
    pixmap = QPixmap(UNREAD_DOT_PX, UNREAD_DOT_PX)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(color))
    painter.drawEllipse(0, 0, UNREAD_DOT_PX, UNREAD_DOT_PX)
    painter.end()
    return QIcon(pixmap)


def _titlebar_icon(kind: str, color: str = "#cfd0da") -> QIcon:
    """타이틀바 버튼 아이콘을 직접 그림 - 글꼴에 따라 유니코드 기호가 없거나 다르게
    보이는 걸 피하려고 최소화/최대화/복원/닫기 아이콘을 전부 벡터 선으로 그림"""
    size = 10
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
    pen = QPen(QColor(color))
    pen.setWidth(1)
    painter.setPen(pen)
    if kind == "minimize":
        painter.drawLine(0, size - 1, size - 1, size - 1)
    elif kind == "maximize":
        painter.drawRect(0, 0, size - 1, size - 1)
    elif kind == "restore":
        painter.drawRect(2, 0, size - 3, size - 3)
        painter.drawRect(0, 2, size - 3, size - 3)
    elif kind == "close":
        painter.drawLine(0, 0, size - 1, size - 1)
        painter.drawLine(0, size - 1, size - 1, 0)
    painter.end()
    return QIcon(pixmap)


def _smiley_icon(size: int = 20, color: str = "#c8cad8") -> QIcon:
    """이모티콘 버튼용 웃는 얼굴. 글꼴에 있는 기호를 쓰면 환경마다 모양이 달라져서 직접 그림."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pen = QPen(QColor(color))
    pen.setWidthF(max(1.4, size / 13))
    painter.setPen(pen)
    inset = pen.widthF()
    painter.drawEllipse(QRectF(inset, inset, size - inset * 2, size - inset * 2))
    # 눈 - 작은 점 두 개
    eye = max(1.4, size / 9)
    painter.setBrush(QColor(color))
    painter.drawEllipse(QRectF(size * 0.32 - eye / 2, size * 0.38 - eye / 2, eye, eye))
    painter.drawEllipse(QRectF(size * 0.68 - eye / 2, size * 0.38 - eye / 2, eye, eye))
    # 입 - 아래쪽 반원
    painter.setBrush(Qt.BrushStyle.NoBrush)
    mouth = QRectF(size * 0.26, size * 0.36, size * 0.48, size * 0.42)
    painter.drawArc(mouth, 200 * 16, 140 * 16)
    painter.end()
    return QIcon(pixmap)


def _find_logo_image() -> str:
    """시작화면에 크게 띄울 로고용 - png를 우선으로 찾음.

    _find_app_icon()은 창/작업표시줄 아이콘용이라 icon.ico를 먼저 고르는데, 그 ico는
    16x16이라 크게 키우면 뭉개짐. 큰 로고는 1024px짜리 icon.png를 써야 함.
    """
    return _find_image_in_app_dirs(("icon.png", "icon.ico"))


def _find_image_in_app_dirs(names: tuple[str, ...]) -> str:
    search_dirs = [_app_dir()]
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        search_dirs.append(meipass)
    for directory in search_dirs:
        for name in names:
            candidate = os.path.join(directory, name)
            if os.path.exists(candidate):
                return candidate
    return ""


def _find_app_icon() -> str:
    # exe에 내장된 아이콘 리소스는 탐색기 파일 아이콘에는 반영되지만, 실행 중인 창의
    # 타이틀바/작업표시줄 아이콘은 Qt가 setWindowIcon()을 직접 호출해야 반영됨 - 그래서
    # exe 옆에 icon.ico가 없어도 항상 찾을 수 있도록 PyInstaller onefile 번들이 풀리는
    # 임시 폴더(sys._MEIPASS)도 함께 찾아봄 (빌드 스크립트가 --add-data로 그 안에 넣어둠)
    search_dirs = [_app_dir()]
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        search_dirs.append(meipass)
    for directory in search_dirs:
        for name in ("icon.ico", "icon.png"):
            candidate = os.path.join(directory, name)
            if os.path.exists(candidate):
                return candidate
    return ""
