"""
IRC 스타일 채팅 - 터미널(TUI) 클라이언트
실행: python tui_client.py [서버주소] [포트]
기본값: 127.0.0.1 6667
"""
import asyncio
import json
import os
import ssl
import sys
from datetime import datetime

from textual.app import App, ComposeResult
from textual.screen import Screen
from textual.containers import Vertical, Horizontal
from textual.widgets import Input, Button, Static, RichLog, Label

DEFAULT_HOST = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
DEFAULT_PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 6667


def _app_dir() -> str:
    """exe로 빌드됐을 때도, python으로 실행했을 때도 실행 파일이 있는 폴더를 정확히 찾음"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _find_default_cert() -> str:
    """실행 파일과 같은 폴더에 cert.pem이 있으면 자동으로 경로를 채워줌"""
    candidate = os.path.join(_app_dir(), "cert.pem")
    return candidate if os.path.exists(candidate) else ""


def _clean_path(raw: str) -> str:
    """윈도우 '경로로 복사'는 양쪽에 큰따옴표를 붙여서 복사되는 경우가 많아 제거해줌"""
    return raw.strip().strip('"').strip("'")


DEFAULT_CERT_PATH = _find_default_cert()


class LoginScreen(Screen):
    """접속 서버 입력 + 아이디/비밀번호 로그인 및 회원가입"""

    CSS = """
    LoginScreen {
        align: center middle;
    }
    #login_box {
        width: 50;
        border: round $accent;
        padding: 1 2;
    }
    #status {
        color: $error;
        height: 2;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="login_box"):
            yield Label("채팅 프로그램 접속", id="title")
            yield Input(placeholder="서버 주소", value=DEFAULT_HOST, id="host")
            yield Input(placeholder="포트", value=str(DEFAULT_PORT), id="port")
            yield Input(
                placeholder="cert.pem 경로 (없으면 비워둠)",
                value=DEFAULT_CERT_PATH,
                id="cert_path",
            )
            yield Static(
                "[dim]※ FriendChat.exe와 같은 폴더에 cert.pem을 넣으면 자동으로 채워집니다[/dim]",
                id="cert_hint",
            )
            yield Input(placeholder="아이디", id="user_id")
            yield Input(placeholder="비밀번호", password=True, id="password")
            with Horizontal():
                yield Button("로그인", id="login_btn", variant="primary")
                yield Button("회원가입", id="register_btn")
            yield Static("", id="status")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        try:
            host = self.query_one("#host", Input).value.strip()
            port = self.query_one("#port", Input).value.strip()
            cert_path = _clean_path(self.query_one("#cert_path", Input).value)
            user_id = self.query_one("#user_id", Input).value.strip()
            password = self.query_one("#password", Input).value

            if not host or not port or not user_id or not password:
                self.query_one("#status", Static).update("모든 항목을 입력하세요.")
                return

            try:
                port_num = int(port)
            except ValueError:
                self.query_one("#status", Static).update("포트는 숫자여야 합니다.")
                return

            app: ChatApp = self.app  # type: ignore

            if event.button.id == "login_btn":
                await app.connect_and_auth(host, port_num, "login", user_id, password, cert_path)
            elif event.button.id == "register_btn":
                await app.connect_and_auth(host, port_num, "register", user_id, password, cert_path)
        except Exception as e:  # noqa: BLE001 - 프로그램이 죽는 것보다 화면에 오류 표시가 낫다
            self.query_one("#status", Static).update(f"오류: {e}")

    def show_status(self, text: str) -> None:
        self.query_one("#status", Static).update(text)


class ChannelScreen(Screen):
    """채널 입장 / 새 채널 생성"""

    CSS = """
    ChannelScreen {
        align: center middle;
    }
    #channel_box {
        width: 50;
        border: round $accent;
        padding: 1 2;
    }
    #status2 {
        color: $error;
        height: 2;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="channel_box"):
            yield Label("채널 입장 / 생성", id="title2")
            yield Input(placeholder="채널명 (예: #친구들)", id="channel")
            yield Input(placeholder="채널 비밀번호 (선택)", password=True, id="key")
            with Horizontal():
                yield Button("입장", id="join_btn", variant="primary")
                yield Button("새 채널 만들기", id="create_btn")
            yield Static("", id="status2")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        try:
            channel = self.query_one("#channel", Input).value.strip()
            key = self.query_one("#key", Input).value

            if not channel:
                self.query_one("#status2", Static).update("채널명을 입력하세요.")
                return

            app: ChatApp = self.app  # type: ignore

            if event.button.id == "create_btn":
                await app.send_cmd({"cmd": "create_channel", "channel": channel, "key": key})
            else:
                await app.send_cmd({"cmd": "join", "channel": channel, "key": key})
        except Exception as e:  # noqa: BLE001
            self.query_one("#status2", Static).update(f"오류: {e}")

    def show_status(self, text: str) -> None:
        self.query_one("#status2", Static).update(text)


class ChatScreen(Screen):
    """실제 채팅 화면"""

    CSS = """
    ChatScreen {
        layout: horizontal;
    }
    #log_area {
        width: 3fr;
        height: 100%;
    }
    #side {
        width: 1fr;
        border-left: solid $accent;
        padding: 1;
    }
    #msg_input {
        dock: bottom;
    }
    """

    def compose(self) -> ComposeResult:
        with Horizontal():
            with Vertical(id="log_area"):
                yield RichLog(id="log", wrap=True, markup=True)
                yield Input(placeholder="메시지 입력 후 Enter", id="msg_input")
            with Vertical(id="side"):
                yield Label("참여자")
                yield Static("", id="userlist")

    def on_mount(self) -> None:
        self.query_one("#msg_input", Input).focus()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "msg_input":
            return
        text = event.value.strip()
        if not text:
            return
        app: ChatApp = self.app  # type: ignore
        try:
            await app.send_cmd({"cmd": "msg", "text": text})
        except Exception:  # noqa: BLE001
            self.append_system("메시지 전송 실패 (연결 확인 필요)")
        event.input.value = ""

    def append_message(self, sender: str, text: str, ts: float, mine: bool) -> None:
        log = self.query_one("#log", RichLog)
        time_str = datetime.fromtimestamp(ts).strftime("%H:%M")
        color = "cyan" if mine else "yellow"
        log.write(f"[{time_str}] [bold {color}]{sender}[/bold {color}]: {text}")

    def append_system(self, text: str) -> None:
        log = self.query_one("#log", RichLog)
        log.write(f"[dim]* {text}[/dim]")

    def update_userlist(self, users: list[str]) -> None:
        self.query_one("#userlist", Static).update("\n".join(users))


class ChatApp(App):
    """전체 앱: 소켓 연결 관리 + 화면 전환"""

    TITLE = "친구 채팅"

    def __init__(self):
        super().__init__()
        self.reader: asyncio.StreamReader | None = None
        self.writer: asyncio.StreamWriter | None = None
        self.user_id: str | None = None
        self.pending_auth_mode: str | None = None

    def on_mount(self) -> None:
        self.push_screen(LoginScreen())

    async def connect_and_auth(self, host, port, mode, user_id, password, cert_path=""):
        login_screen = self.screen

        try:
            ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            if cert_path:
                ssl_context.load_verify_locations(cafile=cert_path)
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_REQUIRED
            else:
                # 인증서 없이도 통신 자체는 암호화됨 (도청 방지)
                # 단, 서버가 진짜인지 확인은 안 하므로 신뢰할 수 있는 서버에서만 사용
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE
        except Exception as e:  # noqa: BLE001 - 잘못된 경로/손상된 인증서 등 모든 경우 방어
            login_screen.show_status(f"인증서 파일을 읽을 수 없습니다: {e}")
            return

        try:
            self.reader, self.writer = await asyncio.open_connection(
                host, port, ssl=ssl_context
            )
        except Exception as e:  # noqa: BLE001 - 연결 관련 모든 예외를 화면에 표시하고 방어
            login_screen.show_status(f"연결 실패: {e}")
            return

        self.pending_auth_mode = mode
        self._pending_user_id = user_id
        cmd = "login" if mode == "login" else "register"
        try:
            await self.send_cmd({"cmd": cmd, "id": user_id, "pw": password})
        except Exception as e:  # noqa: BLE001
            login_screen.show_status(f"통신 오류: {e}")
            return
        self._listen_task = asyncio.create_task(self.listen_loop())

    async def send_cmd(self, payload: dict):
        if not self.writer:
            return
        self.writer.write((json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8"))
        await self.writer.drain()

    async def listen_loop(self) -> None:
        assert self.reader is not None
        try:
            while True:
                line = await self.reader.readline()
                if not line:
                    break
                try:
                    msg = json.loads(line.decode("utf-8").strip())
                except json.JSONDecodeError:
                    continue
                try:
                    await self._handle(msg)
                except Exception:  # noqa: BLE001 - 메시지 하나 처리 실패로 전체가 죽으면 안 됨
                    pass
        except Exception:  # noqa: BLE001 - 연결 종료/네트워크 오류 등 전부 방어
            pass

    async def _handle(self, msg: dict) -> None:
        mtype = msg.get("type")

        if mtype == "auth_result":
            if isinstance(self.screen, LoginScreen):
                if msg["ok"]:
                    if self.pending_auth_mode == "register":
                        self.screen.show_status("회원가입 완료! 이제 로그인하세요.")
                        self.pending_auth_mode = None
                    else:
                        self.user_id = self._pending_user_id
                        self.push_screen(ChannelScreen())
                else:
                    self.screen.show_status(msg.get("text", "실패"))

        elif mtype == "channel_result":
            if isinstance(self.screen, ChannelScreen):
                if msg["ok"]:
                    if "채널 생성" in msg.get("text", ""):
                        self.screen.show_status("채널 생성 완료! 입장 버튼을 눌러주세요.")
                    else:
                        self.push_screen(ChatScreen())
                        self.screen.append_system(msg.get("text", "입장 성공"))
                else:
                    self.screen.show_status(msg.get("text", "실패"))

        elif mtype == "chat":
            if isinstance(self.screen, ChatScreen):
                sender = msg.get("from", "?")
                self.screen.append_message(
                    sender, msg.get("text", ""), msg.get("ts", 0), sender == self.user_id
                )

        elif mtype == "system":
            if isinstance(self.screen, ChatScreen):
                self.screen.append_system(msg.get("text", ""))

        elif mtype == "userlist":
            if isinstance(self.screen, ChatScreen):
                self.screen.update_userlist(msg.get("users", []))

        elif mtype == "error":
            if isinstance(self.screen, (LoginScreen, ChannelScreen)):
                self.screen.show_status(msg.get("text", "오류"))


if __name__ == "__main__":
    ChatApp().run()
