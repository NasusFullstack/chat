"""
친구 채팅 - GUI 클라이언트 (PySide6)
실행: python gui_client.py
- 진짜 OS 텍스트 입력창을 쓰기 때문에 한글 조합(쌍자음 등) 문제가 없음
- QSslSocket으로 TLS 통신 (asyncio 대신 Qt 자체 네트워킹 사용 - 이벤트 루프 충돌 방지)
"""
import base64
import binascii
import datetime
import hashlib
import json
import os
import sys
import time

from PySide6.QtCore import Qt, QBuffer, QIODevice, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPixmap
from PySide6.QtNetwork import QSslSocket, QSslCertificate, QSslConfiguration, QSslError
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QStackedWidget, QWidget, QVBoxLayout,
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QListWidget, QListWidgetItem,
    QFileDialog, QMessageBox, QFrame, QComboBox, QInputDialog, QCheckBox,
    QTabWidget, QScrollArea, QGridLayout, QColorDialog, QDialog, QDialogButtonBox,
)

import server_registry
import irc_protocol
import history_store

CONNECT_TIMEOUT_MS = 10_000
DEFAULT_SSL_PORT = "6697"
DEFAULT_PLAIN_PORT = "6667"

# 말풍선 시간 배지: 지금 기준 폰트(STYLE_SHEET의 14px)의 절반을 고정값으로 씀 -
# 나중에 앱 기본 폰트 크기가 바뀌어도 이 값 자체는 따라 커지지 않음
TIMESTAMP_BADGE_FONT_PX = 7
TIMESTAMP_BADGE_HEIGHT_PX = 14

UNREAD_DOT_PX = 9
UNREAD_DOT_COLOR = "#ff6b6b"

AVATAR_LIST_PX = 16
AVATAR_MSG_PX = 32
AVATAR_GRID_SIZE = 16
# store.py의 AVATAR_MAX_B64_CHARS와 값을 맞춰야 함
AVATAR_MAX_B64_CHARS = 2000

APP_TITLE = "친구 채팅"

STYLE_SHEET = """
QWidget {
    background-color: #1e1f29;
    color: #e6e6e6;
    font-family: "Malgun Gothic", "맑은 고딕", sans-serif;
    font-size: 14px;
}
QLineEdit {
    background-color: #2a2b38;
    border: 1px solid #3d3f52;
    border-radius: 8px;
    padding: 8px;
    color: #ffffff;
}
QLineEdit:focus {
    border: 1px solid #7c6cf0;
}
QPushButton {
    background-color: #7c6cf0;
    border: none;
    border-radius: 8px;
    padding: 10px 16px;
    color: white;
    font-weight: bold;
}
QPushButton:hover {
    background-color: #6a5be0;
}
QPushButton:pressed {
    background-color: #5a4bd0;
}
QPushButton#secondary {
    background-color: #3d3f52;
}
QPushButton#secondary:hover {
    background-color: #4a4d63;
}
QScrollArea {
    background-color: #16171f;
    border: 1px solid #3d3f52;
    border-radius: 8px;
}
QListWidget {
    background-color: #16171f;
    border: 1px solid #3d3f52;
    border-radius: 8px;
    padding: 4px;
}
QLabel#title {
    font-size: 20px;
    font-weight: bold;
    padding-bottom: 8px;
}
QLabel#hint {
    color: #9a9cad;
    font-size: 12px;
}
QLabel#status_err {
    color: #ff6b6b;
}
/* font-size 값은 TIMESTAMP_BADGE_FONT_PX 상수와 반드시 일치시킬 것 (QSS는 상수 참조 불가) */
QLabel#timestampBadge {
    background-color: rgba(154, 156, 173, 100);
    color: #cfd0da;
    font-size: 7px;
    border-radius: 7px;
    padding: 0px 7px;
}
QTabWidget::pane {
    border: 1px solid #3d3f52;
    border-radius: 8px;
    top: -1px;
}
QTabBar::tab {
    background-color: #2a2b38;
    color: #cfd0da;
    padding: 6px 14px;
    border: 1px solid #3d3f52;
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    margin-right: 2px;
}
QTabBar::tab:selected {
    background-color: #16171f;
    color: #ffffff;
}
QTabBar::tab:hover {
    background-color: #3d3f52;
}
"""


def _app_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _find_default_cert() -> str:
    candidate = os.path.join(_app_dir(), "cert.pem")
    return candidate if os.path.exists(candidate) else ""


def _format_ts(ts: float) -> str:
    return datetime.datetime.fromtimestamp(ts).strftime("%H:%M")


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


def _build_unread_icon() -> QIcon:
    size = UNREAD_DOT_PX
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(UNREAD_DOT_COLOR))
    painter.drawEllipse(0, 0, size, size)
    painter.end()
    return QIcon(pixmap)


_UNREAD_ICON: QIcon | None = None


def _unread_icon() -> QIcon:
    global _UNREAD_ICON
    if _UNREAD_ICON is None:
        _UNREAD_ICON = _build_unread_icon()
    return _UNREAD_ICON


class ChatClient(QSslSocket):
    """서버와의 TLS 소켓 통신 + 라인 프로토콜 파싱을 담당 (커스텀 JSON 프로토콜 / 실제 IRC 프로토콜 둘 다 지원)"""

    message_received = Signal(dict)
    irc_line_received = Signal(object)
    connection_failed = Signal(str)

    def __init__(self):
        super().__init__()
        self._buffer = b""
        self._mode = "custom"
        self._pinned_cert = False
        self.readyRead.connect(self._on_ready_read)
        self.errorOccurred.connect(self._on_error)
        self.sslErrors.connect(self._on_ssl_errors)

    def set_mode(self, mode: str):
        """연결 시작 전에 호출: "custom"(친구 채팅 서버 JSON) 또는 "irc"(실제 IRC 서버)"""
        self._mode = mode

    def connect_to_server(self, host: str, port: int, cert_path: str, use_ssl: bool):
        if not use_ssl:
            self.connectToHost(host, port)
            return
        self._pinned_cert = bool(cert_path)
        config = QSslConfiguration.defaultConfiguration()
        if cert_path:
            certs = QSslCertificate.fromPath(cert_path)
            if not certs:
                self.connection_failed.emit(f"인증서 파일을 읽을 수 없습니다: {cert_path}")
                return
            config.setCaCertificates(certs)
        # setSslConfiguration()이 peerVerifyMode를 기본값으로 되돌려버리므로,
        # 반드시 setSslConfiguration() 이후에 setPeerVerifyMode()를 호출해야 함
        # (먼저 호출하면 아래에서 덮어써져 무시됨).
        self.setSslConfiguration(config)
        if cert_path or self._mode == "irc":
            # cert.pem을 지정한 경우(우리 서버, 자체 서명 인증서 핀닝) 뿐 아니라
            # 실제 IRC 서버 모드도 표준 방식으로 검증한다 (실제 서버는 보통 정식
            # CA 인증서를 쓰므로 시스템 신뢰 저장소로 검증해야 위조 인증서를 걸러냄).
            self.setPeerVerifyMode(QSslSocket.PeerVerifyMode.VerifyPeer)
        else:
            # Windows 기본 TLS 백엔드(Schannel)는 QueryPeer + ignoreSslErrors()로
            # "루트 인증서 미신뢰" 오류를 무시하지 못하고 핸드셰이크를 그대로 실패시킴.
            # 인증서 검증 자체를 생략하는 VerifyNone을 써야 암호화만 하는 접속이 실제로 됨.
            self.setPeerVerifyMode(QSslSocket.PeerVerifyMode.VerifyNone)
        self.connectToHostEncrypted(host, port)

    def send_cmd(self, payload: dict):
        if self.state() != QSslSocket.SocketState.ConnectedState:
            return
        data = (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")
        self.write(data)

    def send_irc(self, line: str):
        if self.state() != QSslSocket.SocketState.ConnectedState:
            return
        self.write(irc_protocol.encode_line(line))

    def _on_ready_read(self):
        self._buffer += bytes(self.readAll())
        if self._mode == "irc":
            self._process_irc_buffer()
        else:
            self._process_custom_buffer()

    def _process_custom_buffer(self):
        while b"\n" in self._buffer:
            line, self._buffer = self._buffer.split(b"\n", 1)
            if not line.strip():
                continue
            try:
                msg = json.loads(line.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            self.message_received.emit(msg)

    def _process_irc_buffer(self):
        while b"\n" in self._buffer:
            line, self._buffer = self._buffer.split(b"\n", 1)
            text = line.decode("utf-8", errors="replace")
            if not text.strip():
                continue
            msg = irc_protocol.parse_line(text)
            if msg.command == "PING":
                # 연결 유지의 핵심 - UI 상태와 무관하게 즉시 응답해야 서버가 끊지 않음
                self.write(irc_protocol.encode_line(irc_protocol.format_pong(msg.trailing)))
                continue
            self.irc_line_received.emit(msg)

    def _on_error(self, _error):
        # state()는 handshake 실패 시점에도 여전히 ConnectedState를 보고하는 경우가 있어
        # (Qt가 Closing/Unconnected로 전이하기 전에 errorOccurred를 먼저 emit) 상태로
        # 판단하지 않고 항상 알림. 로그인 이후 발생하는 에러는 MainWindow 쪽에서
        # _connecting 플래그로 걸러낸다.
        self.connection_failed.emit(self.errorString())

    def _on_ssl_errors(self, errors: list[QSslError]):
        if self.peerVerifyMode() == QSslSocket.PeerVerifyMode.VerifyNone:
            # cert.pem 없이 접속: 암호화만 하고 신원 검증은 생략
            self.ignoreSslErrors()
            return
        if not self._pinned_cert:
            # cert.pem 지정 없이 VerifyPeer인 경우 = 실제 IRC 서버 표준 검증 모드.
            # 우리가 지정한 CA 목록이 없으므로 시스템 신뢰 판단을 그대로 따른다
            # (아무것도 무시하지 않음 - 위조/무효 인증서는 그대로 거부되어야 정상).
            return
        # cert.pem으로 검증하는 경우: CaCertificates에 등록해둔 바로 그 인증서와
        # 일치하는지는 반드시 확인하되, 다음 두 오류만 무시한다.
        # - HostNameMismatch: 자체 서명 인증서라 IP/도메인이 뭐든 같은 인증서를 씀
        # - SelfSignedCertificate: 우리가 CaCertificates로 정확히 이 인증서를 이미
        #   신뢰 목록에 넣었으므로 자체 서명이라는 사실 자체는 문제가 아님
        # (다른/가짜 인증서를 준 경우엔 CertificateUntrusted 등 다른 오류가 남기 때문에
        # 여전히 거부됨 - 등록한 인증서와 다르면 접속이 실패해야 정상)
        ignorable = {QSslError.SslError.HostNameMismatch, QSslError.SslError.SelfSignedCertificate}
        real_errors = [e for e in errors if e.error() not in ignorable]
        if not real_errors:
            self.ignoreSslErrors()


class LoginPage(QWidget):
    def __init__(self, on_submit, on_cancel):
        super().__init__()
        self.on_submit = on_submit
        self.on_cancel = on_cancel
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(10)

        box = QVBoxLayout()
        box.setSpacing(8)
        title = QLabel("채팅 프로그램 접속")
        title.setObjectName("title")
        box.addWidget(title)

        self.protocol_combo = QComboBox()
        self.protocol_combo.addItem("친구 채팅 서버 (커스텀)", "custom")
        self.protocol_combo.addItem("실제 IRC 서버", "irc")
        self.protocol_combo.currentIndexChanged.connect(self._on_protocol_changed)
        box.addWidget(self.protocol_combo)

        self.server_combo = QComboBox()
        self.server_combo.currentIndexChanged.connect(self._on_server_selected)
        box.addWidget(self.server_combo)

        server_btn_row = QHBoxLayout()
        register_server_btn = QPushButton("공용서버 등록")
        register_server_btn.setObjectName("secondary")
        register_server_btn.clicked.connect(self._register_server)
        delete_server_btn = QPushButton("선택 서버 삭제")
        delete_server_btn.setObjectName("secondary")
        delete_server_btn.clicked.connect(self._delete_server)
        server_btn_row.addWidget(register_server_btn)
        server_btn_row.addWidget(delete_server_btn)
        box.addLayout(server_btn_row)

        self.host_input = QLineEdit("127.0.0.1")
        self.host_input.setPlaceholderText("서버 주소")
        box.addWidget(self.host_input)

        self.port_input = QLineEdit(DEFAULT_SSL_PORT)
        self.port_input.setPlaceholderText("포트")
        box.addWidget(self.port_input)

        self.ssl_checkbox = QCheckBox("SSL 암호화 사용 (권장, 포트 6697)")
        self.ssl_checkbox.setChecked(True)
        self.ssl_checkbox.toggled.connect(self._on_ssl_toggled)
        box.addWidget(self.ssl_checkbox)

        cert_row = QHBoxLayout()
        self.cert_input = QLineEdit(_find_default_cert())
        self.cert_input.setPlaceholderText("cert.pem 경로 (없으면 비워둠)")
        self.cert_browse_btn = QPushButton("찾아보기")
        self.cert_browse_btn.setObjectName("secondary")
        self.cert_browse_btn.clicked.connect(self._browse_cert)
        cert_row.addWidget(self.cert_input)
        cert_row.addWidget(self.cert_browse_btn)
        box.addLayout(cert_row)

        hint = QLabel(
            "※ SSL을 끄면 암호화 없이 평문(포트 6667)으로 접속해요. "
            "목록에서 공용서버를 고르거나, 주소를 직접 입력한 뒤 '공용서버 등록'으로 저장해두면 다음부터 목록에서 바로 고를 수 있어요"
        )
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        box.addWidget(hint)

        self.user_input = QLineEdit()
        self.user_input.setPlaceholderText("아이디")
        box.addWidget(self.user_input)

        self.pw_input = QLineEdit()
        self.pw_input.setPlaceholderText("비밀번호")
        self.pw_input.setEchoMode(QLineEdit.EchoMode.Password)
        box.addWidget(self.pw_input)

        btn_row = QHBoxLayout()
        self.login_btn = QPushButton("로그인")
        self.login_btn.clicked.connect(lambda: self.on_submit("login"))
        self.register_btn = QPushButton("회원가입")
        self.register_btn.setObjectName("secondary")
        self.register_btn.clicked.connect(lambda: self.on_submit("register"))
        self.cancel_btn = QPushButton("연결 취소")
        self.cancel_btn.setObjectName("secondary")
        self.cancel_btn.clicked.connect(self.on_cancel)
        self.cancel_btn.setVisible(False)
        btn_row.addWidget(self.login_btn)
        btn_row.addWidget(self.register_btn)
        btn_row.addWidget(self.cancel_btn)
        box.addLayout(btn_row)

        self.status_label = QLabel("")
        self.status_label.setObjectName("status_err")
        self.status_label.setWordWrap(True)
        box.addWidget(self.status_label)

        container = QFrame()
        container.setLayout(box)
        container.setFixedWidth(360)
        layout.addWidget(container)
        self.setLayout(layout)

        self._reload_servers()

    def _reload_servers(self, select_name: str | None = None):
        self.server_combo.blockSignals(True)
        self.server_combo.clear()
        self.server_combo.addItem("직접 입력", None)
        select_index = 0
        for i, s in enumerate(server_registry.load_servers(), start=1):
            self.server_combo.addItem(f"{s['name']} ({s['host']}:{s['port']})", s)
            if select_name and s["name"] == select_name:
                select_index = i
        self.server_combo.setCurrentIndex(select_index)
        self.server_combo.blockSignals(False)

    def _on_protocol_changed(self, index: int):
        is_irc = self.protocol_combo.itemData(index) == "irc"
        if is_irc:
            self.user_input.setPlaceholderText("닉네임")
            self.pw_input.setPlaceholderText("서버/NickServ 비밀번호 (선택, 보통 비워둠)")
        else:
            self.user_input.setPlaceholderText("아이디")
            self.pw_input.setPlaceholderText("비밀번호")
        self.register_btn.setVisible(not is_irc)
        self.login_btn.setText("접속" if is_irc else "로그인")

    def _on_server_selected(self, index: int):
        data = self.server_combo.itemData(index)
        if data:
            self.host_input.setText(data["host"])
            self.port_input.setText(str(data["port"]))
            self.cert_input.setText(data.get("cert_path", ""))
            self.ssl_checkbox.setChecked(data.get("ssl", True))
            proto_index = self.protocol_combo.findData(data.get("protocol", "custom"))
            if proto_index >= 0:
                self.protocol_combo.setCurrentIndex(proto_index)

    def _on_ssl_toggled(self, checked: bool):
        self.cert_input.setEnabled(checked)
        self.cert_browse_btn.setEnabled(checked)
        current_port = self.port_input.text().strip()
        if current_port in (DEFAULT_SSL_PORT, DEFAULT_PLAIN_PORT, ""):
            self.port_input.setText(DEFAULT_SSL_PORT if checked else DEFAULT_PLAIN_PORT)

    def _register_server(self):
        host = self.host_input.text().strip()
        port = self.port_input.text().strip()
        if not host or not port:
            self.show_status("서버 주소와 포트를 먼저 입력하세요.")
            return
        try:
            port = int(port)
        except ValueError:
            self.show_status("포트는 숫자여야 합니다.")
            return
        name, ok = QInputDialog.getText(self, "공용서버 등록", "서버 이름:")
        name = name.strip()
        if not ok or not name:
            return
        use_ssl = self.ssl_checkbox.isChecked()
        cert_path = self.cert_input.text().strip().strip('"').strip("'") if use_ssl else ""
        protocol = self.protocol_combo.currentData()
        server_registry.add_server(name, host, port, cert_path, ssl=use_ssl, protocol=protocol)
        self._reload_servers(select_name=name)
        self.show_status(f"'{name}' 서버가 등록되었습니다. 다음부터 목록에서 바로 선택할 수 있어요.")

    def _delete_server(self):
        data = self.server_combo.itemData(self.server_combo.currentIndex())
        if not data:
            self.show_status("삭제할 서버를 목록에서 선택하세요.")
            return
        confirm = QMessageBox.question(
            self, "서버 삭제", f"'{data['name']}' 서버를 목록에서 삭제할까요?",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        server_registry.remove_server(data["name"])
        self._reload_servers()
        self.show_status(f"'{data['name']}' 서버를 삭제했습니다.")

    def _browse_cert(self):
        path, _ = QFileDialog.getOpenFileName(self, "cert.pem 선택", "", "PEM Files (*.pem);;All Files (*)")
        if path:
            self.cert_input.setText(path)

    def show_status(self, text: str):
        self.status_label.setText(text)

    def set_connecting(self, connecting: bool):
        self.login_btn.setEnabled(not connecting)
        self.register_btn.setEnabled(not connecting)
        self.cancel_btn.setVisible(connecting)

    def get_values(self):
        return {
            "host": self.host_input.text().strip(),
            "port": self.port_input.text().strip(),
            "cert_path": self.cert_input.text().strip().strip('"').strip("'"),
            "ssl": self.ssl_checkbox.isChecked(),
            "protocol": self.protocol_combo.currentData(),
            "user_id": self.user_input.text().strip(),
            "password": self.pw_input.text(),
        }


class ChannelPage(QWidget):
    def __init__(self, on_submit):
        super().__init__()
        self.on_submit = on_submit
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        box = QVBoxLayout()
        box.setSpacing(8)
        title = QLabel("채널 입장 / 생성")
        title.setObjectName("title")
        box.addWidget(title)

        self.channel_input = QLineEdit()
        self.channel_input.setPlaceholderText("채널명 (예: #친구들)")
        box.addWidget(self.channel_input)

        self.key_input = QLineEdit()
        self.key_input.setPlaceholderText("채널 비밀번호 (선택)")
        self.key_input.setEchoMode(QLineEdit.EchoMode.Password)
        box.addWidget(self.key_input)

        btn_row = QHBoxLayout()
        join_btn = QPushButton("입장")
        join_btn.clicked.connect(lambda: self.on_submit("join"))
        self.create_btn = QPushButton("새 채널 만들기")
        self.create_btn.setObjectName("secondary")
        self.create_btn.clicked.connect(lambda: self.on_submit("create"))
        btn_row.addWidget(join_btn)
        btn_row.addWidget(self.create_btn)
        box.addLayout(btn_row)

        self.status_label = QLabel("")
        self.status_label.setObjectName("status_err")
        self.status_label.setWordWrap(True)
        box.addWidget(self.status_label)

        container = QFrame()
        container.setLayout(box)
        container.setFixedWidth(360)
        layout.addWidget(container)
        self.setLayout(layout)

    def set_mode(self, protocol: str):
        self.create_btn.setVisible(protocol != "irc")

    def show_status(self, text: str):
        self.status_label.setText(text)

    def get_values(self):
        return {
            "channel": self.channel_input.text().strip(),
            "key": self.key_input.text(),
        }


class MessageWidget(QWidget):
    """채팅 메시지 한 개 - 왼쪽에 아바타, 오른쪽 아래에 시간 타원 배지"""

    def __init__(self, sender: str, text: str, mine: bool, ts: float, avatar_pixmap: QPixmap, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)

        avatar_label = QLabel()
        avatar_label.setFixedSize(AVATAR_MSG_PX, AVATAR_MSG_PX)
        avatar_label.setPixmap(avatar_pixmap.scaled(
            AVATAR_MSG_PX, AVATAR_MSG_PX,
            Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.FastTransformation,
        ))
        layout.addWidget(avatar_label, 0, Qt.AlignmentFlag.AlignTop)

        body = QVBoxLayout()
        body.setSpacing(2)

        color = "#7cd0ff" if mine else "#ffd27c"
        safe_text = text.replace("<", "&lt;").replace(">", "&gt;")
        text_label = QLabel(f'<span style="color:{color}"><b>{sender}</b></span>: {safe_text}')
        text_label.setTextFormat(Qt.TextFormat.RichText)
        text_label.setWordWrap(True)
        body.addWidget(text_label)

        badge_row = QHBoxLayout()
        badge_row.addStretch(1)
        badge = QLabel(_format_ts(ts))
        badge.setObjectName("timestampBadge")
        badge.setFixedHeight(TIMESTAMP_BADGE_HEIGHT_PX)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge_row.addWidget(badge)
        body.addLayout(badge_row)

        layout.addLayout(body, 1)


def _build_system_label(text: str) -> QLabel:
    label = QLabel(f'<span style="color:#9a9cad"><i>* {text}</i></span>')
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    label.setWordWrap(True)
    return label


class ChannelLogView(QScrollArea):
    """채널 하나의 메시지 목록 - 메시지마다 개별 위젯으로 쌓음 (QTextEdit HTML 방식 대체)"""

    def __init__(self, channel: str, parent=None):
        super().__init__(parent)
        self.channel_name = channel
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        self._layout = QVBoxLayout(content)
        self._layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._layout.setSpacing(4)
        self.setWidget(content)

    def append_message(self, sender: str, text: str, mine: bool, ts: float, avatar_pixmap: QPixmap):
        self._layout.addWidget(MessageWidget(sender, text, mine, ts, avatar_pixmap))
        self._scroll_to_bottom_deferred()

    def append_system(self, text: str):
        self._layout.addWidget(_build_system_label(text))
        self._scroll_to_bottom_deferred()

    def _scroll_to_bottom_deferred(self):
        QTimer.singleShot(0, lambda: self.verticalScrollBar().setValue(self.verticalScrollBar().maximum()))


class AvatarEditorDialog(QDialog):
    """16x16 픽셀아트 아이콘 에디터 - 셀 클릭으로 색칠, 지우개, 전체 지우기 지원"""

    def __init__(self, initial_base64: str | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("내 아이콘 그리기")
        self.result_base64 = ""
        self._current_color = QColor("#7c6cf0")
        self._eraser = False
        self._cell_colors: dict[tuple[int, int], QColor | None] = {}
        self._buttons: dict[tuple[int, int], QPushButton] = {}

        layout = QVBoxLayout(self)

        grid_widget = QWidget()
        grid = QGridLayout(grid_widget)
        grid.setSpacing(0)
        for y in range(AVATAR_GRID_SIZE):
            for x in range(AVATAR_GRID_SIZE):
                btn = QPushButton()
                btn.setFixedSize(20, 20)
                btn.setStyleSheet("background-color: transparent; border: 1px solid #3d3f52;")
                btn.clicked.connect(lambda checked=False, x=x, y=y: self._on_cell_clicked(x, y))
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
                self._buttons[(x, y)].setStyleSheet(f"background-color: {color.name()}; border: 1px solid #3d3f52;")

    def _on_cell_clicked(self, x: int, y: int):
        if self._eraser:
            self._cell_colors[(x, y)] = None
            self._buttons[(x, y)].setStyleSheet("background-color: transparent; border: 1px solid #3d3f52;")
        else:
            self._cell_colors[(x, y)] = QColor(self._current_color)
            self._buttons[(x, y)].setStyleSheet(
                f"background-color: {self._current_color.name()}; border: 1px solid #3d3f52;"
            )

    def _choose_color(self):
        color = QColorDialog.getColor(self._current_color, self, "색상 선택")
        if color.isValid():
            self._current_color = color
            self._eraser_btn.setChecked(False)

    def _toggle_eraser(self, checked: bool):
        self._eraser = checked

    def _clear_all(self):
        self._cell_colors.clear()
        for btn in self._buttons.values():
            btn.setStyleSheet("background-color: transparent; border: 1px solid #3d3f52;")

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
        b64 = self.to_base64_png()
        if len(b64) > AVATAR_MAX_B64_CHARS:
            QMessageBox.warning(self, "저장 실패", "아이콘 데이터가 너무 큽니다. 더 단순하게 그려주세요.")
            return
        self.result_base64 = b64
        self.accept()


class ChatPage(QWidget):
    """여러 채널을 탭으로 동시에 열어둘 수 있음"""

    def __init__(self, on_send, on_add_channel, on_leave_channel, on_set_avatar):
        super().__init__()
        self.on_send = on_send
        self.on_add_channel = on_add_channel
        self.on_leave_channel = on_leave_channel
        self.on_set_avatar = on_set_avatar
        self.my_id = ""
        self._log_views: dict[str, ChannelLogView] = {}
        self._members: dict[str, list[str]] = {}
        self._avatar_pixmaps: dict[str, QPixmap] = {}
        self._active_channel = ""
        self._protocol_mode = "custom"

        layout = QHBoxLayout()

        center = QVBoxLayout()
        self._center_stack = QStackedWidget()
        self._empty_label = QLabel("입장한 채널이 없습니다.\n'+' 버튼으로 입장하세요.")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._center_stack.addWidget(self._empty_label)

        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self._on_tab_close_requested)
        self.tabs.currentChanged.connect(self._on_tab_changed)
        add_tab_btn = QPushButton("+")
        add_tab_btn.setObjectName("secondary")
        add_tab_btn.setFixedWidth(32)
        add_tab_btn.clicked.connect(lambda: self.on_add_channel())
        self.tabs.setCornerWidget(add_tab_btn, Qt.Corner.TopRightCorner)
        self._center_stack.addWidget(self.tabs)

        center.addWidget(self._center_stack)

        input_row = QHBoxLayout()
        self.msg_input = QLineEdit()
        self.msg_input.setPlaceholderText("메시지 입력 후 Enter")
        self.msg_input.returnPressed.connect(self._submit)
        send_btn = QPushButton("전송")
        send_btn.clicked.connect(self._submit)
        input_row.addWidget(self.msg_input)
        input_row.addWidget(send_btn)
        center.addLayout(input_row)
        center_widget = QWidget()
        center_widget.setLayout(center)

        right = QVBoxLayout()
        right.addWidget(QLabel("참여자"))
        self.user_list = QListWidget()
        right.addWidget(self.user_list)
        self.avatar_btn = QPushButton("내 아이콘 설정")
        self.avatar_btn.setObjectName("secondary")
        self.avatar_btn.clicked.connect(lambda: self.on_set_avatar())
        right.addWidget(self.avatar_btn)
        right_widget = QWidget()
        right_widget.setLayout(right)
        right_widget.setFixedWidth(160)

        layout.addWidget(center_widget, 3)
        layout.addWidget(right_widget, 1)
        self.setLayout(layout)
        self._update_input_enabled()

    def set_protocol_mode(self, mode: str):
        self._protocol_mode = mode
        self.avatar_btn.setVisible(mode != "irc")
        self._avatar_pixmaps.clear()

    def _update_input_enabled(self):
        self.msg_input.setEnabled(bool(self._active_channel))

    def add_channel(self, channel: str, activate: bool = True):
        if channel not in self._log_views:
            view = ChannelLogView(channel)
            self._log_views[channel] = view
            self._members[channel] = []
            self.tabs.addTab(view, channel)
            self._center_stack.setCurrentWidget(self.tabs)
        if activate:
            self.set_active_channel(channel)

    def remove_channel(self, channel: str):
        view = self._log_views.pop(channel, None)
        if view is None:
            return
        self._members.pop(channel, None)
        index = self.tabs.indexOf(view)
        if index >= 0:
            self.tabs.removeTab(index)  # 남은 탭이 있으면 currentChanged가 자동으로 활성 채널을 갱신함
        view.deleteLater()
        if not self._log_views:
            self._active_channel = ""
            self._center_stack.setCurrentWidget(self._empty_label)
            self.user_list.clear()
        self._update_input_enabled()

    def set_active_channel(self, channel: str):
        view = self._log_views.get(channel)
        if view is None:
            return
        index = self.tabs.indexOf(view)
        if index >= 0:
            self.tabs.setCurrentIndex(index)

    def active_channel(self) -> str:
        return self._active_channel

    def _on_tab_changed(self, index: int):
        if index < 0:
            return
        view = self.tabs.widget(index)
        if view is None:
            return
        self._active_channel = view.channel_name
        self.tabs.setTabIcon(index, QIcon())
        self.user_list.clear()
        self._add_userlist_items(self._members.get(self._active_channel, []))
        self._update_input_enabled()

    def _on_tab_close_requested(self, index: int):
        view = self.tabs.widget(index)
        if view is None:
            return
        channel = view.channel_name
        confirm = QMessageBox.question(self, "채널 나가기", f"'{channel}' 채널에서 나갈까요?")
        if confirm == QMessageBox.StandardButton.Yes:
            self.on_leave_channel(channel)

    def _mark_unread(self, channel: str):
        if channel == self._active_channel:
            return
        view = self._log_views.get(channel)
        if view is None:
            return
        index = self.tabs.indexOf(view)
        if index >= 0:
            self.tabs.setTabIcon(index, _unread_icon())

    def _submit(self):
        text = self.msg_input.text().strip()
        if not text or not self._active_channel:
            return
        self.on_send(self._active_channel, text)
        self.msg_input.clear()

    def focus_input(self):
        self.msg_input.setFocus()

    def _avatar_for(self, user_id: str, px: int) -> QPixmap:
        cached = None if self._protocol_mode == "irc" else self._avatar_pixmaps.get(user_id)
        base = cached if cached is not None else _hashed_avatar_pixmap(user_id)
        return base.scaled(px, px, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.FastTransformation)

    def append_message(self, channel: str, sender: str, text: str, mine: bool, ts: float):
        view = self._log_views.get(channel)
        if view is None:
            return
        view.append_message(sender, text, mine, ts, self._avatar_for(sender, AVATAR_MSG_PX))
        self._mark_unread(channel)

    def append_system(self, channel: str, text: str):
        view = self._log_views.get(channel)
        if view is None:
            return
        view.append_system(text)

    def load_history(self, channel: str, entries: list[dict]):
        if not entries:
            return
        self.append_system(channel, "── 이전 대화 기록 ──")
        for entry in entries:
            mine = entry.get("from") == self.my_id
            self.append_message(
                channel, entry.get("from", "?"), entry.get("text", ""), mine, entry.get("ts", 0)
            )
        self.append_system(channel, "── 여기까지 이전 기록 ──")

    def _add_userlist_items(self, users: list[str]):
        for uid in users:
            item = QListWidgetItem(uid)
            item.setIcon(QIcon(self._avatar_for(uid, AVATAR_LIST_PX)))
            self.user_list.addItem(item)

    def update_userlist(self, channel: str, users: list[str]):
        self._members[channel] = users
        if channel == self._active_channel:
            self.user_list.clear()
            self._add_userlist_items(users)

    def set_avatar(self, user_id: str, avatar_b64: str | None):
        if self._protocol_mode == "irc" or not avatar_b64:
            self._avatar_pixmaps.pop(user_id, None)
        else:
            pixmap = _decode_avatar_pixmap(avatar_b64)
            if pixmap is not None:
                self._avatar_pixmaps[user_id] = pixmap
        if self._active_channel:
            self.user_list.clear()
            self._add_userlist_items(self._members.get(self._active_channel, []))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(720, 480)

        self.client = ChatClient()
        self.client.connected.connect(self._on_tcp_connected)
        self.client.encrypted.connect(self._on_connected)
        self.client.connection_failed.connect(self._on_connection_failed)
        self.client.message_received.connect(self._on_message)
        self.client.irc_line_received.connect(self._on_irc_line)

        self.my_id = ""
        self.pending_mode = ""
        self._connecting = False
        self._auth_phase = False
        self._pending_ssl = True
        self._host = ""
        self._port = 0
        self._protocol_mode = "custom"
        self._joined_channels: set[str] = set()
        self._my_avatar_b64: str | None = None

        # 실제 IRC 서버 모드 전용 상태
        self._irc_current_nick = ""
        self._irc_password = ""
        self._irc_identified = False
        self._irc_members: dict[str, set[str]] = {}
        self._irc_names_buffer: dict[str, list[str]] = {}
        self._irc_nick_retries = 0

        self._connect_timer = QTimer(self)
        self._connect_timer.setSingleShot(True)
        self._connect_timer.timeout.connect(self._on_connect_timeout)

        self.stack = QStackedWidget()

        self.login_page = LoginPage(self._handle_login_submit, self._handle_cancel_connect)
        self.channel_page = ChannelPage(self._handle_channel_submit)
        self.chat_page = ChatPage(
            self._handle_send, self._handle_add_channel, self._handle_leave_channel, self._handle_set_avatar
        )

        self.stack.addWidget(self.login_page)
        self.stack.addWidget(self.channel_page)
        self.stack.addWidget(self.chat_page)
        self.setCentralWidget(self.stack)

    # ---------------- 로그인 ----------------
    def _handle_login_submit(self, mode: str):
        values = self.login_page.get_values()
        protocol = values["protocol"]
        if protocol == "irc":
            if not values["host"] or not values["port"] or not values["user_id"]:
                self.login_page.show_status("서버 주소/포트/닉네임을 입력하세요.")
                return
        elif not values["host"] or not values["port"] or not values["user_id"] or not values["password"]:
            self.login_page.show_status("모든 항목을 입력하세요.")
            return
        try:
            port = int(values["port"])
        except ValueError:
            self.login_page.show_status("포트는 숫자여야 합니다.")
            return

        self.pending_mode = mode
        self._protocol_mode = protocol
        self.chat_page.set_protocol_mode(protocol)
        self._pending_user_id = values["user_id"]
        self._pending_password = values["password"]
        self._host = values["host"]
        self._port = port
        self._joined_channels = set()
        self._my_avatar_b64 = None

        if protocol == "irc":
            self._irc_current_nick = values["user_id"]
            self._irc_password = values["password"]
            self._irc_identified = False
            self._irc_members = {}
            self._irc_names_buffer = {}
            self._irc_nick_retries = 0

        if self.client.state() == QSslSocket.SocketState.ConnectedState:
            # 이미 연결돼 있으면 (예: 회원가입 후 바로 로그인) 재연결하지 않고 바로 전송
            self._on_connected()
            return

        mode_label = "SSL" if values["ssl"] else "평문(암호화 없음)"
        self.login_page.show_status(f"연결 중... ({mode_label}, 최대 10초, 언제든 '연결 취소' 가능)")
        self.login_page.set_connecting(True)
        self._connecting = True
        self._pending_ssl = values["ssl"]
        self._connect_timer.start(CONNECT_TIMEOUT_MS)
        self.client.set_mode(protocol)
        try:
            self.client.connect_to_server(values["host"], port, values["cert_path"], values["ssl"])
        except Exception as e:  # noqa: BLE001
            self._stop_connecting()
            self.login_page.show_status(f"오류: {e}")

    def _stop_connecting(self):
        self._connecting = False
        self._auth_phase = False
        self._connect_timer.stop()
        self.login_page.set_connecting(False)

    def _handle_cancel_connect(self):
        if not self._connecting:
            return
        self._stop_connecting()
        self.client.abort()
        self.login_page.show_status("연결을 취소했습니다.")

    def _on_connect_timeout(self):
        if not self._connecting:
            return
        was_auth_phase = self._auth_phase
        self._stop_connecting()
        self.client.abort()
        if was_auth_phase:
            # 소켓/TLS 연결은 됐지만 로그인 응답이 안 온 경우 - 우리 채팅 서버가 아니거나
            # (예: 진짜 IRC 서버 등 다른 프로토콜) 서버가 멈춰있을 가능성이 큼
            if self._protocol_mode == "irc":
                self.login_page.show_status(
                    f"서버 응답이 없습니다. ({CONNECT_TIMEOUT_MS // 1000}초) IRC 서버 주소/포트가 맞는지 확인하세요."
                )
            else:
                self.login_page.show_status(
                    f"서버 응답이 없습니다. ({CONNECT_TIMEOUT_MS // 1000}초) "
                    "이 친구 채팅 서버(server.py)가 맞는지, 주소/포트가 맞는지 확인하세요."
                )
        else:
            self.login_page.show_status(f"연결 시간이 초과되었습니다. ({CONNECT_TIMEOUT_MS // 1000}초)")

    def _on_tcp_connected(self):
        # SSL 모드는 TLS 핸드셰이크가 끝나는 encrypted() 신호를 기다려야 함.
        # (여기서 로그인 정보를 보내면 핸드셰이크 완료 전에 취소/타임아웃 창이 사라짐)
        if not self._pending_ssl:
            self._on_connected()

    def _on_connected(self):
        # 소켓/TLS 연결은 끝났지만 아직 로그인 응답을 못 받은 상태이므로 취소/타임아웃을
        # 계속 활성 상태로 유지한 채 응답 대기 단계로 넘어간다 (연결만 되고 로그인 응답이
        # 영영 안 오는 경우에도 무한정 "연결 중"에 멈추지 않도록).
        self._connecting = True
        self._auth_phase = True
        self.login_page.set_connecting(True)
        self._connect_timer.start(CONNECT_TIMEOUT_MS)
        if self._protocol_mode == "irc":
            self.login_page.show_status("서버 접속 중... (언제든 '연결 취소' 가능)")
            self._start_irc_registration()
            return
        self.login_page.show_status("로그인 확인 중... (언제든 '연결 취소' 가능)")
        cmd = "login" if self.pending_mode == "login" else "register"
        self.client.send_cmd({"cmd": cmd, "id": self._pending_user_id, "pw": self._pending_password})

    def _start_irc_registration(self):
        if self._irc_password:
            self.client.send_irc(irc_protocol.format_pass(self._irc_password))
        self.client.send_irc(irc_protocol.format_nick(self._irc_current_nick))
        self.client.send_irc(irc_protocol.format_user(self._irc_current_nick, self._irc_current_nick))

    def _on_connection_failed(self, err: str):
        if not self._connecting:
            # 사용자가 취소했거나 타임아웃으로 이미 처리된 경우 - 중복 메시지 방지
            return
        self._stop_connecting()
        if self.stack.currentWidget() is self.login_page:
            self.login_page.show_status(f"연결 실패: {err}")

    # ---------------- 채널 ----------------
    def _handle_channel_submit(self, action: str):
        values = self.channel_page.get_values()
        if not values["channel"]:
            self.channel_page.show_status("채널명을 입력하세요.")
            return
        if self._protocol_mode == "irc":
            channel = irc_protocol.normalize_channel(values["channel"])
            self.client.send_irc(irc_protocol.format_join(channel, values["key"] or None))
            return
        if action == "create":
            self.client.send_cmd({"cmd": "create_channel", "channel": values["channel"], "key": values["key"]})
        else:
            self.client.send_cmd({"cmd": "join", "channel": values["channel"], "key": values["key"]})

    def _handle_add_channel(self):
        """채팅 화면 안에서 채널을 추가로 입장 (기존 채널을 떠나지 않음, 새 채널 생성은 지원 안 함)"""
        channel, ok = QInputDialog.getText(self.chat_page, "채널 추가", "입장할 채널명:")
        channel = channel.strip()
        if not ok or not channel:
            return
        key, ok2 = QInputDialog.getText(
            self.chat_page, "채널 추가", "채널 비밀번호 (없으면 비워둠):", QLineEdit.EchoMode.Password
        )
        key = key if ok2 else ""
        if self._protocol_mode == "irc":
            channel = irc_protocol.normalize_channel(channel)
            self.client.send_irc(irc_protocol.format_join(channel, key or None))
        else:
            self.client.send_cmd({"cmd": "join", "channel": channel, "key": key})

    def _handle_leave_channel(self, channel: str):
        if self._protocol_mode == "irc":
            self.client.send_irc(irc_protocol.format_part(channel))
        else:
            self.client.send_cmd({"cmd": "leave", "channel": channel})

    def _handle_set_avatar(self):
        if self._protocol_mode == "irc":
            return  # 방어적 처리 - IRC 모드에선 버튼 자체가 숨겨져 있음
        dlg = AvatarEditorDialog(initial_base64=self._my_avatar_b64, parent=self.chat_page)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        b64 = dlg.result_base64
        if len(b64) > AVATAR_MAX_B64_CHARS:
            QMessageBox.warning(self, "아이콘 저장 실패", "아이콘 데이터가 너무 큽니다.")
            return
        self._my_avatar_b64 = b64
        self.chat_page.set_avatar(self.my_id, b64)  # 서버가 보낸 사람에게는 다시 안 보내주므로 낙관적으로 먼저 반영
        self.client.send_cmd({"cmd": "set_avatar", "avatar": b64})

    def _on_channel_joined(self, channel: str, text: str):
        """커스텀 프로토콜의 channel_result 성공 / IRC의 자기 자신 JOIN 둘 다 여기로 모임"""
        first_time = self.stack.currentWidget() is self.channel_page
        self._joined_channels.add(channel)
        self.chat_page.add_channel(channel, activate=True)
        if first_time:
            self.stack.setCurrentWidget(self.chat_page)
            self.chat_page.focus_input()
        self.chat_page.append_system(channel, text)
        entries = history_store.load_history(self._protocol_mode, self._host, self._port, channel)
        self.chat_page.load_history(channel, entries)

    # ---------------- 채팅 ----------------
    def _handle_send(self, channel: str, text: str):
        if self._protocol_mode == "irc":
            self.client.send_irc(irc_protocol.format_privmsg(channel, text))
            # IRC 서버는 보낸 메시지를 나에게 다시 돌려주지 않으므로 직접 반영
            ts = time.time()
            self.chat_page.append_message(channel, self._irc_current_nick, text, True, ts)
            history_store.append_message("irc", self._host, self._port, channel, self._irc_current_nick, text, ts)
            return
        self.client.send_cmd({"cmd": "msg", "channel": channel, "text": text})

    # ---------------- 실제 IRC 서버 메시지 처리 ----------------
    def _on_irc_line(self, msg: irc_protocol.IrcMessage):
        cmd = msg.command

        if cmd == irc_protocol.RPL_WELCOME:
            self._stop_connecting()
            self.my_id = self._irc_current_nick
            self.chat_page.my_id = self.my_id
            self.channel_page.set_mode("irc")
            self.stack.setCurrentWidget(self.channel_page)
            if self._irc_password and not self._irc_identified:
                self._irc_identified = True
                self.client.send_irc(irc_protocol.format_privmsg("NickServ", f"IDENTIFY {self._irc_password}"))
            return

        if cmd in irc_protocol.NICK_COLLISION_NUMERICS:
            if self.stack.currentWidget() is self.login_page and self._irc_nick_retries < irc_protocol.MAX_NICK_RETRIES:
                self._irc_nick_retries += 1
                self._irc_current_nick += "_"
                self.client.send_irc(irc_protocol.format_nick(self._irc_current_nick))
            else:
                self._stop_connecting()
                self.client.abort()
                self.login_page.show_status("사용 가능한 닉네임이 없습니다. 다른 닉네임으로 다시 시도하세요.")
            return

        if cmd in irc_protocol.CHANNEL_JOIN_ERROR_NUMERICS:
            text = msg.trailing or "채널 입장에 실패했습니다."
            if self.stack.currentWidget() is self.channel_page:
                self.channel_page.show_status(text)
            else:
                QMessageBox.warning(self, "채널 입장 실패", text)
            return

        if cmd == irc_protocol.RPL_NAMREPLY:
            channel = msg.params[2] if len(msg.params) > 2 else ""
            self._irc_names_buffer.setdefault(channel, []).extend(irc_protocol.parse_names_reply(msg))
            return

        if cmd == irc_protocol.RPL_ENDOFNAMES:
            channel = msg.params[1] if len(msg.params) > 1 else ""
            members = set(self._irc_names_buffer.pop(channel, []))
            self._irc_members[channel] = members
            self.chat_page.update_userlist(channel, sorted(members))
            return

        if cmd == "JOIN":
            nick = msg.source_nick
            channel = msg.trailing or (msg.params[0] if msg.params else "")
            if nick == self._irc_current_nick:
                self._irc_members.setdefault(channel, set()).add(nick)
                self._on_channel_joined(channel, f"{channel}에 입장했습니다.")
                self.client.send_irc(irc_protocol.format_names(channel))
            else:
                members = self._irc_members.setdefault(channel, set())
                members.add(nick)
                self.chat_page.append_system(channel, f"{nick}님이 입장했습니다.")
                self.chat_page.update_userlist(channel, sorted(members))
            return

        if cmd == "PART":
            nick = msg.source_nick
            channel = msg.params[0] if msg.params else ""
            members = self._irc_members.setdefault(channel, set())
            members.discard(nick)
            self.chat_page.append_system(channel, f"{nick}님이 나갔습니다.")
            self.chat_page.update_userlist(channel, sorted(members))
            if nick == self._irc_current_nick:
                self._joined_channels.discard(channel)
                self.chat_page.remove_channel(channel)
            return

        if cmd == "QUIT":
            # QUIT은 채널 정보가 없으므로 그 닉네임이 있던 모든 채널에 반영
            nick = msg.source_nick
            for channel, members in self._irc_members.items():
                if nick in members:
                    members.discard(nick)
                    self.chat_page.append_system(channel, f"{nick}님이 접속을 종료했습니다.")
                    self.chat_page.update_userlist(channel, sorted(members))
            return

        if cmd == "NICK":
            old_nick = msg.source_nick
            new_nick = msg.trailing or (msg.params[0] if msg.params else "")
            if old_nick == self._irc_current_nick:
                self._irc_current_nick = new_nick
                self.my_id = new_nick
                self.chat_page.my_id = new_nick
            for channel, members in self._irc_members.items():
                if old_nick in members:
                    members.discard(old_nick)
                    members.add(new_nick)
                    self.chat_page.append_system(channel, f"{old_nick}님이 {new_nick}(으)로 닉네임을 변경했습니다.")
                    self.chat_page.update_userlist(channel, sorted(members))
            return

        if cmd == "PRIVMSG":
            sender = msg.source_nick
            target = msg.params[0] if msg.params else ""
            text = msg.trailing
            ts = time.time()
            if target == self._irc_current_nick:
                active = self.chat_page.active_channel()
                if active:
                    self.chat_page.append_message(active, f"{sender} (귓속말)", text, False, ts)
            else:
                self.chat_page.append_message(target, sender, text, False, ts)
                history_store.append_message("irc", self._host, self._port, target, sender, text, ts)
            return

        if cmd == "NOTICE":
            text = msg.trailing
            if self.stack.currentWidget() is self.login_page:
                self.login_page.show_status(text)
            else:
                active = self.chat_page.active_channel()
                if active:
                    self.chat_page.append_system(active, text)
            return

        if cmd == "ERROR":
            active = self.chat_page.active_channel()
            if active:
                self.chat_page.append_system(active, f"서버 연결이 종료되었습니다: {msg.trailing}")
            return

    # ---------------- 친구 서버 메시지 처리 ----------------
    def _on_message(self, msg: dict):
        mtype = msg.get("type")

        if mtype == "auth_result":
            self._stop_connecting()
            if msg.get("ok"):
                if self.pending_mode == "register":
                    self.login_page.show_status("회원가입 완료! 이제 로그인하세요.")
                    self.pending_mode = ""
                else:
                    self.my_id = self._pending_user_id
                    self.chat_page.my_id = self.my_id
                    self.stack.setCurrentWidget(self.channel_page)
            else:
                self.login_page.show_status(msg.get("text", "실패"))

        elif mtype == "channel_result":
            channel = msg.get("channel", "")
            if msg.get("ok"):
                if "채널 생성" in msg.get("text", ""):
                    self.channel_page.show_status("채널 생성 완료! 입장 버튼을 눌러주세요.")
                else:
                    self._on_channel_joined(channel, msg.get("text", "입장 성공"))
            else:
                if self.stack.currentWidget() is self.channel_page:
                    self.channel_page.show_status(msg.get("text", "실패"))
                else:
                    QMessageBox.warning(self, "채널 입장 실패", msg.get("text", "실패"))

        elif mtype == "leave_result":
            channel = msg.get("channel", "")
            if msg.get("ok"):
                self._joined_channels.discard(channel)
                self.chat_page.remove_channel(channel)
            else:
                QMessageBox.warning(self, "채널 나가기 실패", msg.get("text", "실패"))

        elif mtype == "chat":
            sender = msg.get("from", "?")
            channel = msg.get("channel", "")
            text = msg.get("text", "")
            ts = msg.get("ts", time.time())
            self.chat_page.append_message(channel, sender, text, sender == self.my_id, ts)
            history_store.append_message("custom", self._host, self._port, channel, sender, text, ts)

        elif mtype == "system":
            channel = msg.get("channel") or self.chat_page.active_channel()
            if channel:
                self.chat_page.append_system(channel, msg.get("text", ""))

        elif mtype == "userlist":
            channel = msg.get("channel") or self.chat_page.active_channel()
            if channel:
                self.chat_page.update_userlist(channel, msg.get("users", []))

        elif mtype == "member_avatar":
            user_id = msg.get("user_id", "")
            if user_id:
                self.chat_page.set_avatar(user_id, msg.get("avatar"))

        elif mtype == "error":
            text = msg.get("text", "오류")
            if self.stack.currentWidget() is self.login_page:
                self.login_page.show_status(text)
            elif self.stack.currentWidget() is self.channel_page:
                self.channel_page.show_status(text)
            else:
                QMessageBox.warning(self, "오류", text)


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLE_SHEET)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
