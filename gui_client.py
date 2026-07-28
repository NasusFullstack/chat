"""
친구 채팅 - GUI 클라이언트 (PySide6)
실행: python gui_client.py
- 진짜 OS 텍스트 입력창을 쓰기 때문에 한글 조합(쌍자음 등) 문제가 없음
- QSslSocket으로 TLS 통신 (asyncio 대신 Qt 자체 네트워킹 사용 - 이벤트 루프 충돌 방지)
"""
import json
import os
import sys

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QTextCursor
from PySide6.QtNetwork import QSslSocket, QSslCertificate, QSslConfiguration, QSslError
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QStackedWidget, QWidget, QVBoxLayout,
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QTextEdit, QListWidget,
    QFileDialog, QMessageBox, QFrame, QTabWidget,
)

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
QTextEdit {
    background-color: #16171f;
    border: 1px solid #3d3f52;
    border-radius: 8px;
    padding: 8px;
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
"""


def _app_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _find_default_cert() -> str:
    candidate = os.path.join(_app_dir(), "cert.pem")
    return candidate if os.path.exists(candidate) else ""


class ChatClient(QSslSocket):
    """서버와의 TLS 소켓 통신 + JSON 라인 프로토콜 파싱을 담당"""

    message_received = Signal(dict)
    connection_failed = Signal(str)

    def __init__(self):
        super().__init__()
        self._buffer = b""
        self.readyRead.connect(self._on_ready_read)
        self.errorOccurred.connect(self._on_error)
        self.sslErrors.connect(self._on_ssl_errors)

    def connect_to_server(self, host: str, port: int, cert_path: str):
        config = QSslConfiguration.defaultConfiguration()
        if cert_path:
            certs = QSslCertificate.fromPath(cert_path)
            if not certs:
                self.connection_failed.emit(f"인증서 파일을 읽을 수 없습니다: {cert_path}")
                return
            config.setCaCertificates(certs)
            self.setPeerVerifyMode(QSslSocket.PeerVerifyMode.VerifyPeer)
        else:
            self.setPeerVerifyMode(QSslSocket.PeerVerifyMode.QueryPeer)
        self.setSslConfiguration(config)
        self.connectToHostEncrypted(host, port)

    def send_cmd(self, payload: dict):
        if self.state() != QSslSocket.SocketState.ConnectedState:
            return
        data = (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")
        self.write(data)

    def _on_ready_read(self):
        self._buffer += bytes(self.readAll())
        while b"\n" in self._buffer:
            line, self._buffer = self._buffer.split(b"\n", 1)
            if not line.strip():
                continue
            try:
                msg = json.loads(line.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            self.message_received.emit(msg)

    def _on_error(self, _error):
        if self.state() != QSslSocket.SocketState.ConnectedState:
            self.connection_failed.emit(self.errorString())

    def _on_ssl_errors(self, errors: list[QSslError]):
        if self.peerVerifyMode() == QSslSocket.PeerVerifyMode.QueryPeer:
            # cert.pem 없이 접속: 암호화만 하고 신원 검증은 생략
            self.ignoreSslErrors()
            return
        # cert.pem으로 검증하는 경우: 인증서 자체의 진위는 반드시 확인하되,
        # "호스트명이 인증서와 다르다"는 오류만 무시 (자체 서명 인증서라 IP/도메인이
        # 뭐든 상관없이 같은 인증서를 쓰기 때문 - 기존 asyncio 클라이언트와 동일한 방식)
        real_errors = [e for e in errors if e.error() != QSslError.SslError.HostNameMismatch]
        if not real_errors:
            self.ignoreSslErrors()


class IRCClient(QSslSocket):
    """진짜 IRC 프로토콜(RFC 1459/2812)로 공개 IRC 서버(예: Libera.Chat)와 통신"""

    ready = Signal()  # 서버 접속 환영 메시지(001) 수신 -> 채널 join 가능 상태
    joined = Signal(str)  # 채널 입장 완료
    chat_received = Signal(str, str)  # (보낸사람, 텍스트)
    system_message = Signal(str)
    userlist_updated = Signal(list)
    connection_failed = Signal(str)

    def __init__(self):
        super().__init__()
        self._buffer = b""
        self._nickname = ""
        self._channel = ""
        self._names_buffer: list[str] = []
        self.readyRead.connect(self._on_ready_read)
        self.errorOccurred.connect(self._on_error)
        self.sslErrors.connect(self._on_ssl_errors)
        self.connected.connect(self._on_connected)

    def connect_to_irc(self, host: str, port: int, nickname: str):
        self._nickname = nickname
        # 공개 IRC 서버는 정식 CA 서명 인증서를 쓰므로 기본 시스템 신뢰 체인으로 검증
        self.setPeerVerifyMode(QSslSocket.PeerVerifyMode.VerifyPeer)
        self.connectToHostEncrypted(host, port)

    def join_channel(self, channel: str, key: str = ""):
        self._channel = channel
        self._names_buffer = []
        if key:
            self._send_raw(f"JOIN {channel} {key}")
        else:
            self._send_raw(f"JOIN {channel}")

    def send_privmsg(self, text: str):
        if not self._channel:
            return
        self._send_raw(f"PRIVMSG {self._channel} :{text}")

    def _send_raw(self, line: str):
        if self.state() != QSslSocket.SocketState.ConnectedState:
            return
        self.write((line + "\r\n").encode("utf-8"))

    def _on_connected(self):
        self._send_raw(f"NICK {self._nickname}")
        self._send_raw(f"USER {self._nickname} 0 * :{self._nickname}")

    def _on_ready_read(self):
        self._buffer += bytes(self.readAll())
        while b"\r\n" in self._buffer:
            line, self._buffer = self._buffer.split(b"\r\n", 1)
            if line:
                self._handle_line(line.decode("utf-8", errors="replace"))

    def _handle_line(self, line: str):
        if line.startswith("PING"):
            token = line.split(" ", 1)[1] if " " in line else ""
            self._send_raw(f"PONG {token}")
            return

        prefix = ""
        if line.startswith(":"):
            prefix, _, line = line[1:].partition(" ")
        parts = line.split(" ")
        command = parts[0] if parts else ""
        nick = prefix.split("!")[0] if "!" in prefix else prefix

        if command == "001":
            self.ready.emit()
        elif command == "433":  # 닉네임 이미 사용 중
            self._nickname += "_"
            self._send_raw(f"NICK {self._nickname}")
            self.system_message.emit(f"닉네임 충돌 -> {self._nickname}(으)로 변경")
        elif command == "JOIN":
            channel = parts[1].lstrip(":") if len(parts) > 1 else ""
            if nick == self._nickname:
                self.joined.emit(channel)
            else:
                self.system_message.emit(f"{nick}님이 입장했습니다.")
        elif command == "PART":
            self.system_message.emit(f"{nick}님이 나갔습니다.")
        elif command == "QUIT":
            self.system_message.emit(f"{nick}님이 접속을 종료했습니다.")
        elif command == "353":  # NAMES 응답 (참여자 목록)
            if ":" in line:
                names_part = line.split(":", 1)[1]
                self._names_buffer.extend(
                    n.lstrip("@+~&%") for n in names_part.split() if n
                )
        elif command == "366":  # NAMES 목록 끝
            self.userlist_updated.emit(sorted(set(self._names_buffer)))
        elif command == "PRIVMSG":
            if len(parts) >= 2:
                text = line.split(":", 1)[1] if ":" in line else ""
                self.chat_received.emit(nick, text)
        elif command in ("NOTICE",):
            pass  # 서버 공지는 무시 (원하면 system_message로 노출 가능)

    def _on_error(self, _error):
        if self.state() != QSslSocket.SocketState.ConnectedState:
            self.connection_failed.emit(self.errorString())

    def _on_ssl_errors(self, errors: list[QSslError]):
        # 공개 서버는 신뢰할 수 있는 CA 인증서를 쓰므로 오류가 있으면 그대로 노출 (무시하지 않음)
        pass


class LoginPage(QWidget):
    def __init__(self, on_submit):
        super().__init__()
        self.on_submit = on_submit
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(10)

        box = QVBoxLayout()
        box.setSpacing(8)
        title = QLabel("채팅 프로그램 접속")
        title.setObjectName("title")
        box.addWidget(title)

        self.host_input = QLineEdit("127.0.0.1")
        self.host_input.setPlaceholderText("서버 주소")
        box.addWidget(self.host_input)

        self.port_input = QLineEdit("6667")
        self.port_input.setPlaceholderText("포트")
        box.addWidget(self.port_input)

        cert_row = QHBoxLayout()
        self.cert_input = QLineEdit(_find_default_cert())
        self.cert_input.setPlaceholderText("cert.pem 경로 (없으면 비워둠)")
        cert_browse = QPushButton("찾아보기")
        cert_browse.setObjectName("secondary")
        cert_browse.clicked.connect(self._browse_cert)
        cert_row.addWidget(self.cert_input)
        cert_row.addWidget(cert_browse)
        box.addLayout(cert_row)

        hint = QLabel("※ 파일 선택 버튼으로 cert.pem을 고르면 경로 입력이 필요 없어요")
        hint.setObjectName("hint")
        box.addWidget(hint)

        self.user_input = QLineEdit()
        self.user_input.setPlaceholderText("아이디")
        box.addWidget(self.user_input)

        self.pw_input = QLineEdit()
        self.pw_input.setPlaceholderText("비밀번호")
        self.pw_input.setEchoMode(QLineEdit.EchoMode.Password)
        box.addWidget(self.pw_input)

        btn_row = QHBoxLayout()
        login_btn = QPushButton("로그인")
        login_btn.clicked.connect(lambda: self.on_submit("login"))
        register_btn = QPushButton("회원가입")
        register_btn.setObjectName("secondary")
        register_btn.clicked.connect(lambda: self.on_submit("register"))
        btn_row.addWidget(login_btn)
        btn_row.addWidget(register_btn)
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

    def _browse_cert(self):
        path, _ = QFileDialog.getOpenFileName(self, "cert.pem 선택", "", "PEM Files (*.pem);;All Files (*)")
        if path:
            self.cert_input.setText(path)

    def show_status(self, text: str):
        self.status_label.setText(text)

    def get_values(self):
        return {
            "host": self.host_input.text().strip(),
            "port": self.port_input.text().strip(),
            "cert_path": self.cert_input.text().strip().strip('"').strip("'"),
            "user_id": self.user_input.text().strip(),
            "password": self.pw_input.text(),
        }


class LiberaLoginPage(QWidget):
    """Libera.Chat 같은 공개 IRC 서버 접속용 (계정 없이 닉네임만으로 접속)"""

    def __init__(self, on_submit):
        super().__init__()
        self.on_submit = on_submit
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(10)

        box = QVBoxLayout()
        box.setSpacing(8)
        title = QLabel("Libera.Chat 접속")
        title.setObjectName("title")
        box.addWidget(title)

        self.host_input = QLineEdit("irc.libera.chat")
        self.host_input.setPlaceholderText("IRC 서버 주소")
        box.addWidget(self.host_input)

        self.port_input = QLineEdit("6697")
        self.port_input.setPlaceholderText("포트 (TLS)")
        box.addWidget(self.port_input)

        self.nick_input = QLineEdit()
        self.nick_input.setPlaceholderText("닉네임")
        box.addWidget(self.nick_input)

        self.channel_input = QLineEdit()
        self.channel_input.setPlaceholderText("채널명 (예: ##친구들)")
        box.addWidget(self.channel_input)

        self.key_input = QLineEdit()
        self.key_input.setPlaceholderText("채널 비밀번호 (없으면 비워둠)")
        self.key_input.setEchoMode(QLineEdit.EchoMode.Password)
        box.addWidget(self.key_input)

        hint = QLabel("※ Libera.Chat은 회원가입 없이 닉네임만으로 바로 접속됩니다")
        hint.setObjectName("hint")
        box.addWidget(hint)

        connect_btn = QPushButton("접속")
        connect_btn.clicked.connect(self.on_submit)
        box.addWidget(connect_btn)

        self.status_label = QLabel("")
        self.status_label.setObjectName("status_err")
        self.status_label.setWordWrap(True)
        box.addWidget(self.status_label)

        container = QFrame()
        container.setLayout(box)
        container.setFixedWidth(360)
        layout.addWidget(container)
        self.setLayout(layout)

    def show_status(self, text: str):
        self.status_label.setText(text)

    def get_values(self):
        return {
            "host": self.host_input.text().strip(),
            "port": self.port_input.text().strip(),
            "nickname": self.nick_input.text().strip(),
            "channel": self.channel_input.text().strip(),
            "key": self.key_input.text(),
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
        create_btn = QPushButton("새 채널 만들기")
        create_btn.setObjectName("secondary")
        create_btn.clicked.connect(lambda: self.on_submit("create"))
        btn_row.addWidget(join_btn)
        btn_row.addWidget(create_btn)
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

    def show_status(self, text: str):
        self.status_label.setText(text)

    def get_values(self):
        return {
            "channel": self.channel_input.text().strip(),
            "key": self.key_input.text(),
        }


class ChatPage(QWidget):
    def __init__(self, on_send):
        super().__init__()
        self.on_send = on_send
        self.my_id = ""

        layout = QHBoxLayout()

        left = QVBoxLayout()
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        left.addWidget(self.log)

        input_row = QHBoxLayout()
        self.msg_input = QLineEdit()
        self.msg_input.setPlaceholderText("메시지 입력 후 Enter")
        self.msg_input.returnPressed.connect(self._submit)
        send_btn = QPushButton("전송")
        send_btn.clicked.connect(self._submit)
        input_row.addWidget(self.msg_input)
        input_row.addWidget(send_btn)
        left.addLayout(input_row)

        right = QVBoxLayout()
        right.addWidget(QLabel("참여자"))
        self.user_list = QListWidget()
        right.addWidget(self.user_list)

        left_widget = QWidget()
        left_widget.setLayout(left)
        right_widget = QWidget()
        right_widget.setLayout(right)
        right_widget.setFixedWidth(160)

        layout.addWidget(left_widget, 3)
        layout.addWidget(right_widget, 1)
        self.setLayout(layout)

    def _submit(self):
        text = self.msg_input.text().strip()
        if not text:
            return
        self.on_send(text)
        self.msg_input.clear()

    def focus_input(self):
        self.msg_input.setFocus()

    def append_message(self, sender: str, text: str, mine: bool):
        color = "#7cd0ff" if mine else "#ffd27c"
        safe_text = text.replace("<", "&lt;").replace(">", "&gt;")
        self.log.append(f'<span style="color:{color}"><b>{sender}</b></span>: {safe_text}')

    def append_system(self, text: str):
        self.log.append(f'<span style="color:#9a9cad"><i>* {text}</i></span>')

    def update_userlist(self, users: list[str]):
        self.user_list.clear()
        self.user_list.addItems(users)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(720, 480)

        self.client = ChatClient()
        self.client.connected.connect(self._on_connected)
        self.client.connection_failed.connect(self._on_connection_failed)
        self.client.message_received.connect(self._on_message)

        self.irc_client = IRCClient()
        self.irc_client.ready.connect(self._on_irc_ready)
        self.irc_client.joined.connect(self._on_irc_joined)
        self.irc_client.chat_received.connect(self._on_irc_chat)
        self.irc_client.system_message.connect(self._on_irc_system)
        self.irc_client.userlist_updated.connect(self.chat_page_update_userlist_safe)
        self.irc_client.connection_failed.connect(self._on_irc_connection_failed)

        self.my_id = ""
        self.pending_mode = ""
        self.mode = "friend"  # "friend" 또는 "irc" - 지금 어떤 방식으로 접속했는지

        self.stack = QStackedWidget()

        self.login_page = LoginPage(self._handle_login_submit)
        self.libera_page = LiberaLoginPage(self._handle_libera_submit)

        self.entry_tabs = QTabWidget()
        self.entry_tabs.addTab(self.login_page, "친구 서버")
        self.entry_tabs.addTab(self.libera_page, "Libera.Chat (IRC)")

        self.channel_page = ChannelPage(self._handle_channel_submit)
        self.chat_page = ChatPage(self._handle_send)

        self.stack.addWidget(self.entry_tabs)
        self.stack.addWidget(self.channel_page)
        self.stack.addWidget(self.chat_page)
        self.setCentralWidget(self.stack)

    def chat_page_update_userlist_safe(self, users: list[str]):
        self.chat_page.update_userlist(users)

    # ---------------- 친구 서버 로그인 ----------------
    def _handle_login_submit(self, mode: str):
        values = self.login_page.get_values()
        if not values["host"] or not values["port"] or not values["user_id"] or not values["password"]:
            self.login_page.show_status("모든 항목을 입력하세요.")
            return
        try:
            port = int(values["port"])
        except ValueError:
            self.login_page.show_status("포트는 숫자여야 합니다.")
            return

        self.mode = "friend"
        self.pending_mode = mode
        self._pending_user_id = values["user_id"]
        self._pending_password = values["password"]

        if self.client.state() == QSslSocket.SocketState.ConnectedState:
            # 이미 연결돼 있으면 (예: 회원가입 후 바로 로그인) 재연결하지 않고 바로 전송
            self._on_connected()
            return

        self.login_page.show_status("연결 중...")
        try:
            self.client.connect_to_server(values["host"], port, values["cert_path"])
        except Exception as e:  # noqa: BLE001
            self.login_page.show_status(f"오류: {e}")

    def _on_connected(self):
        cmd = "login" if self.pending_mode == "login" else "register"
        self.client.send_cmd({"cmd": cmd, "id": self._pending_user_id, "pw": self._pending_password})

    def _on_connection_failed(self, err: str):
        if self.mode == "friend" and self.stack.currentWidget() is self.entry_tabs:
            self.login_page.show_status(f"연결 실패: {err}")

    # ---------------- Libera.Chat(IRC) 접속 ----------------
    def _handle_libera_submit(self):
        values = self.libera_page.get_values()
        if not values["host"] or not values["port"] or not values["nickname"] or not values["channel"]:
            self.libera_page.show_status("서버/닉네임/채널을 모두 입력하세요.")
            return
        try:
            port = int(values["port"])
        except ValueError:
            self.libera_page.show_status("포트는 숫자여야 합니다.")
            return
        if not values["channel"].startswith("#"):
            self.libera_page.show_status("채널명은 #으로 시작해야 합니다 (예: ##친구들).")
            return

        self.mode = "irc"
        self._pending_channel = values["channel"]
        self._pending_key = values["key"]

        self.libera_page.show_status("접속 중...")
        try:
            self.irc_client.connect_to_irc(values["host"], port, values["nickname"])
        except Exception as e:  # noqa: BLE001
            self.libera_page.show_status(f"오류: {e}")

    def _on_irc_ready(self):
        # 서버 접속 환영 메시지 수신 -> 대기 중이던 채널로 자동 입장
        self.irc_client.join_channel(self._pending_channel, self._pending_key)

    def _on_irc_joined(self, channel: str):
        self.my_id = self.libera_page.get_values()["nickname"]
        self.chat_page.my_id = self.my_id
        self.stack.setCurrentWidget(self.chat_page)
        self.chat_page.append_system(f"{channel} 채널에 입장했습니다.")
        self.chat_page.focus_input()

    def _on_irc_chat(self, sender: str, text: str):
        self.chat_page.append_message(sender, text, sender == self.my_id)

    def _on_irc_system(self, text: str):
        self.chat_page.append_system(text)

    def _on_irc_connection_failed(self, err: str):
        if self.mode == "irc" and self.stack.currentWidget() is self.entry_tabs:
            self.libera_page.show_status(f"연결 실패: {err}")

    # ---------------- 채널 (친구 서버 전용) ----------------
    def _handle_channel_submit(self, action: str):
        values = self.channel_page.get_values()
        if not values["channel"]:
            self.channel_page.show_status("채널명을 입력하세요.")
            return
        if action == "create":
            self.client.send_cmd({"cmd": "create_channel", "channel": values["channel"], "key": values["key"]})
        else:
            self.client.send_cmd({"cmd": "join", "channel": values["channel"], "key": values["key"]})

    # ---------------- 채팅 (모드에 따라 분기) ----------------
    def _handle_send(self, text: str):
        if self.mode == "irc":
            self.irc_client.send_privmsg(text)
            # IRC는 자기 자신에게 에코를 보내주지 않으므로 직접 화면에 표시
            self.chat_page.append_message(self.my_id, text, True)
        else:
            self.client.send_cmd({"cmd": "msg", "text": text})

    # ---------------- 친구 서버 메시지 처리 ----------------
    def _on_message(self, msg: dict):
        mtype = msg.get("type")

        if mtype == "auth_result":
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
            if msg.get("ok"):
                if "채널 생성" in msg.get("text", ""):
                    self.channel_page.show_status("채널 생성 완료! 입장 버튼을 눌러주세요.")
                else:
                    self.stack.setCurrentWidget(self.chat_page)
                    self.chat_page.append_system(msg.get("text", "입장 성공"))
                    self.chat_page.focus_input()
            else:
                self.channel_page.show_status(msg.get("text", "실패"))

        elif mtype == "chat":
            sender = msg.get("from", "?")
            self.chat_page.append_message(sender, msg.get("text", ""), sender == self.my_id)

        elif mtype == "system":
            self.chat_page.append_system(msg.get("text", ""))

        elif mtype == "userlist":
            self.chat_page.update_userlist(msg.get("users", []))

        elif mtype == "error":
            if self.stack.currentWidget() is self.entry_tabs:
                self.login_page.show_status(msg.get("text", "오류"))
            elif self.stack.currentWidget() is self.channel_page:
                self.channel_page.show_status(msg.get("text", "오류"))


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLE_SHEET)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
