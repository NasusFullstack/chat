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
    QFileDialog, QMessageBox, QFrame,
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

        self.my_id = ""
        self.pending_mode = ""

        self.stack = QStackedWidget()
        self.login_page = LoginPage(self._handle_login_submit)
        self.channel_page = ChannelPage(self._handle_channel_submit)
        self.chat_page = ChatPage(self._handle_send)

        self.stack.addWidget(self.login_page)
        self.stack.addWidget(self.channel_page)
        self.stack.addWidget(self.chat_page)
        self.setCentralWidget(self.stack)

    # ---------------- 로그인 ----------------
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
        if self.stack.currentWidget() is self.login_page:
            self.login_page.show_status(f"연결 실패: {err}")

    # ---------------- 채널 ----------------
    def _handle_channel_submit(self, action: str):
        values = self.channel_page.get_values()
        if not values["channel"]:
            self.channel_page.show_status("채널명을 입력하세요.")
            return
        if action == "create":
            self.client.send_cmd({"cmd": "create_channel", "channel": values["channel"], "key": values["key"]})
        else:
            self.client.send_cmd({"cmd": "join", "channel": values["channel"], "key": values["key"]})

    # ---------------- 채팅 ----------------
    def _handle_send(self, text: str):
        self.client.send_cmd({"cmd": "msg", "text": text})

    # ---------------- 서버 메시지 처리 ----------------
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
            if self.stack.currentWidget() is self.login_page:
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
