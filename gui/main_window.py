"""메인 윈도우 - 로그인/채널입장/채팅 화면을 QStackedWidget으로 전환하며 프로토콜 메시지를 처리함.

themed_get_text/themed_warning은 테스트가 g.themed_warning = fake처럼 gui_client 모듈에
직접 몽키패치하는 대상임 - 그래서 `import gui_client` 후 `gui_client.themed_warning(...)`
처럼 모듈 속성으로 조회해서 호출함. 자세한 이유는 gui_client.py 상단 주석 참고.
"""
import time

from PySide6.QtCore import QEvent, QPoint, Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtNetwork import QSslSocket
from PySide6.QtWidgets import (
    QApplication, QDialog, QLineEdit, QMainWindow, QStackedWidget, QVBoxLayout, QWidget,
)

import gui_client
import history_store
import irc_protocol
import login_prefs
from gui.helpers import _friendly_connection_error
from gui.network import ChatClient
from gui.pages import ChannelPage, ChatPage, LoginPage
from gui.profile_dialog import ProfileDialog
from gui.theme import APP_TITLE, AVATAR_MAX_B64_CHARS, CONNECT_TIMEOUT_MS, IS_WINDOWS
from gui.title_bar import TitleBar
from version import APP_VERSION

_RESIZE_EDGE_CURSORS = {
    frozenset({Qt.Edge.TopEdge}): Qt.CursorShape.SizeVerCursor,
    frozenset({Qt.Edge.BottomEdge}): Qt.CursorShape.SizeVerCursor,
    frozenset({Qt.Edge.LeftEdge}): Qt.CursorShape.SizeHorCursor,
    frozenset({Qt.Edge.RightEdge}): Qt.CursorShape.SizeHorCursor,
    frozenset({Qt.Edge.TopEdge, Qt.Edge.LeftEdge}): Qt.CursorShape.SizeFDiagCursor,
    frozenset({Qt.Edge.BottomEdge, Qt.Edge.RightEdge}): Qt.CursorShape.SizeFDiagCursor,
    frozenset({Qt.Edge.TopEdge, Qt.Edge.RightEdge}): Qt.CursorShape.SizeBDiagCursor,
    frozenset({Qt.Edge.BottomEdge, Qt.Edge.LeftEdge}): Qt.CursorShape.SizeBDiagCursor,
}


class MainWindow(QMainWindow):
    _RESIZE_BORDER = 6  # 프레임 없는 창에서 이 두께(px)만큼을 크기조절 손잡이로 취급

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_TITLE} v{APP_VERSION}")
        # 로그인 화면이 위젯을 세로로 많이 쌓아둔 편이라(항목이 가장 많은 화면),
        # 커스텀 타이틀바(36px)까지 감안해도 그 화면이 찌그러지지 않을 만큼
        # 넉넉하게 시작 크기/최소 크기를 잡음 (타이틀바 높이는 TitleBar.TITLEBAR_HEIGHT)
        self.resize(720, 600)
        self.setMinimumSize(480, 540)

        self._title_bar: TitleBar | None = None
        if IS_WINDOWS:
            self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
            self.setMouseTracking(True)
            QApplication.instance().installEventFilter(self)

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
        self._nick_change_pending = False  # 프로필 화면에서 직접 요청한 닉네임 변경 처리 중인지

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

        if IS_WINDOWS:
            container = QWidget()
            outer = QVBoxLayout(container)
            outer.setContentsMargins(0, 0, 0, 0)
            outer.setSpacing(0)
            self._title_bar = TitleBar(self)
            outer.addWidget(self._title_bar)
            outer.addWidget(self.stack)
            self.setCentralWidget(container)
        else:
            self.setCentralWidget(self.stack)

        # 창이 실제로 뜬 뒤에 시도해야 로그인 중 상태 표시(연결 중.../취소 버튼)가
        # 정상적으로 보임 - 생성자 안에서 곧바로 시도하면 아직 화면에 아무것도
        # 그려지기 전이라 사용자 입장에서 뭐가 되고 있는지 알기 어려움
        QTimer.singleShot(200, self._maybe_auto_login)

    def set_window_icon(self, icon: QIcon):
        self.setWindowIcon(icon)
        if self._title_bar is not None:
            self._title_bar.set_icon(icon)

    def changeEvent(self, event):
        # 버튼 클릭이 아니라 더블클릭/에어로 스냅 등 다른 경로로 최대화 상태가
        # 바뀌어도 타이틀바의 최대화<->복원 아이콘이 항상 실제 상태와 맞도록 동기화
        if event.type() == event.Type.WindowStateChange and self._title_bar is not None:
            self._title_bar.set_maximized(self.isMaximized())
        super().changeEvent(event)

    def _resize_edges_at(self, local_pos: QPoint) -> Qt.Edges:
        if self.isMaximized():
            return Qt.Edges()
        w, h = self.width(), self.height()
        bw = self._RESIZE_BORDER
        edges = Qt.Edges()
        if local_pos.x() < bw:
            edges |= Qt.Edge.LeftEdge
        elif local_pos.x() > w - bw:
            edges |= Qt.Edge.RightEdge
        if local_pos.y() < bw:
            edges |= Qt.Edge.TopEdge
        elif local_pos.y() > h - bw:
            edges |= Qt.Edge.BottomEdge
        return edges

    def eventFilter(self, obj, event):
        # 프레임 없는 창은 OS가 알아서 해주던 가장자리 크기조절이 사라지므로,
        # 자식 위젯이 마우스 이벤트를 먼저 가로채기 전에(앱 전역 이벤트 필터라 위젯
        # 디스패치보다 먼저 통과함) 창 가장자리 근처인지 직접 확인해서
        # QWindow.startSystemResize()로 OS의 네이티브 크기조절 루프를 그대로 넘김
        et = event.type()
        if et in (QEvent.Type.MouseMove, QEvent.Type.MouseButtonPress) and isinstance(obj, QWidget):
            if obj.window() is self:
                local_pos = self.mapFromGlobal(event.globalPosition().toPoint())
                edges = self._resize_edges_at(local_pos)
                if et == QEvent.Type.MouseMove:
                    key = frozenset(e for e in (Qt.Edge.TopEdge, Qt.Edge.BottomEdge, Qt.Edge.LeftEdge, Qt.Edge.RightEdge) if edges & e)
                    self.setCursor(_RESIZE_EDGE_CURSORS.get(key, Qt.CursorShape.ArrowCursor))
                elif edges and event.button() == Qt.MouseButton.LeftButton:
                    handle = self.windowHandle()
                    if handle is not None:
                        handle.startSystemResize(edges)
                        return True
        return super().eventFilter(obj, event)

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
        self._pending_cert_path = values["cert_path"]
        self._pending_auto_login = values["auto_login"]
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
            self._nick_change_pending = False

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

    def _save_login_prefs(self):
        """로그인이 실제로 성공한 시점에만 호출함. 자동로그인 체크박스를 껐다면
        비밀번호는 저장하지 않고(민감정보), 아이디/서버 주소 등은 다음에 편하게
        쓸 수 있도록 계속 기억해둠. 매번 새로 덮어써서, 체크박스를 껐다가 로그인하면
        이전에 저장돼있던 비밀번호도 자연스럽게 지워짐"""
        prefs = {
            "user_id": self._pending_user_id,
            "host": self._host,
            "port": self._port,
            "ssl": self._pending_ssl,
            "cert_path": self._pending_cert_path,
            "protocol": self._protocol_mode,
            "auto_login": self._pending_auto_login,
        }
        if self._pending_auto_login:
            prefs["password"] = self._pending_password
        login_prefs.save(prefs)

    def _maybe_auto_login(self):
        """저장된 자동로그인 정보가 있으면 앱을 켜자마자 자동으로 로그인 시도.
        로그인 화면의 입력값은 LoginPage._load_saved_prefs()에서 이미 채워둔 상태라
        여기서는 그걸 그대로 제출하기만 하면 됨"""
        prefs = login_prefs.load()
        # password는 필수로 안 봄 - IRC는 비밀번호 없이 접속하는 게 보통이라(NickServ
        # 비번은 선택), 빈 비밀번호를 요구하면 IRC 자동로그인이 항상 조용히 안 걸림
        if prefs.get("auto_login") and prefs.get("user_id"):
            self._handle_login_submit("login")

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
            friendly = _friendly_connection_error(err, self._pending_ssl, self.client._pinned_cert)
            self.login_page.show_status(friendly)

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
        channel, ok = gui_client.themed_get_text(self.chat_page, "채널 추가", "입장할 채널명:")
        channel = channel.strip()
        if not ok or not channel:
            return
        key, ok2 = gui_client.themed_get_text(
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
        is_irc = self._protocol_mode == "irc"
        current_nickname = self._irc_current_nick if is_irc else self.chat_page._nicknames.get(self.my_id, "")
        dlg = ProfileDialog(
            initial_base64=self._my_avatar_b64, initial_nickname=current_nickname, is_irc=is_irc, parent=self.chat_page
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        b64 = dlg.result_base64
        if len(b64) > AVATAR_MAX_B64_CHARS:
            gui_client.themed_warning(self, "아이콘 저장 실패", "아이콘 데이터가 너무 큽니다.")
            return
        self._my_avatar_b64 = b64
        self.chat_page.set_avatar(self.my_id, b64)  # 상대에게는 다시 안 돌아오므로 낙관적으로 먼저 반영
        if is_irc:
            # 실제 IRC 서버는 아이콘 개념이 없으므로, PRIVMSG 안에 CTCP처럼 숨겨서
            # 우리 클라이언트끼리만 알아보게 보냄 (내가 입장한 모든 채널에)
            for channel in self._joined_channels:
                self.client.send_irc(irc_protocol.format_ctcp_avatar(channel, b64))
        else:
            self.client.send_cmd({"cmd": "set_avatar", "avatar": b64})

        new_nickname = dlg.result_nickname
        if new_nickname == current_nickname:
            return
        if is_irc:
            if new_nickname:
                # 실제 IRC 서버는 닉네임이 곧 접속 식별자라 서버가 승인해야 확정됨 -
                # 낙관적으로 먼저 바꾸지 않고 NICK 요청 후 서버 응답(NICK 반영/충돌 오류)을 기다림
                self._nick_change_pending = True
                self.client.send_irc(irc_protocol.format_nick(new_nickname))
        else:
            self.chat_page.set_nickname(self.my_id, new_nickname)  # 낙관적으로 먼저 반영
            self.client.send_cmd({"cmd": "set_nickname", "nickname": new_nickname})

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
            # 서버가 001 응답 첫 파라미터로 실제로 확정된 닉네임을 알려줌 - 우리가 보낸
            # 닉네임과 다를 수 있음(글자 제한/치환 등으로 서버가 바꿨을 수 있어서, 이걸
            # 안 읽고 우리가 보낸 값을 그대로 쓰면 화면에는 엉뚱한 이름이 남을 수 있음)
            confirmed_nick = msg.params[0] if msg.params else self._irc_current_nick
            self._irc_current_nick = confirmed_nick
            self.my_id = confirmed_nick
            self.chat_page.my_id = self.my_id
            self.channel_page.set_mode("irc")
            self.stack.setCurrentWidget(self.channel_page)
            self._save_login_prefs()
            if self._irc_password and not self._irc_identified:
                self._irc_identified = True
                self.client.send_irc(irc_protocol.format_privmsg("NickServ", f"IDENTIFY {self._irc_password}"))
            return

        if cmd in irc_protocol.NICK_COLLISION_NUMERICS:
            if self._nick_change_pending:
                # 로그인 후 프로필 화면에서 직접 요청한 닉네임 변경이 거부된 경우 -
                # 이미 접속된 세션이므로 연결을 끊지 않고 실패만 알림
                self._nick_change_pending = False
                gui_client.themed_warning(
                    self, "닉네임 변경 실패", msg.trailing or "이미 사용 중인 닉네임입니다."
                )
                return
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
                gui_client.themed_warning(self, "채널 입장 실패", text)
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
                if self._my_avatar_b64:
                    # 내가 방금 입장한 채널의 기존 멤버들에게 내 아이콘을 알려줌
                    self.client.send_irc(irc_protocol.format_ctcp_avatar(channel, self._my_avatar_b64))
            else:
                members = self._irc_members.setdefault(channel, set())
                members.add(nick)
                self.chat_page.append_system(channel, f"{nick}님이 입장했습니다.")
                self.chat_page.update_userlist(channel, sorted(members))
                if self._my_avatar_b64:
                    # 새로 들어온 사람에게 내 아이콘을 바로 알려줌 (channel 전체에 다시 뿌릴 필요 없이 1:1로)
                    self.client.send_irc(irc_protocol.format_ctcp_avatar(nick, self._my_avatar_b64))
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
                self._nick_change_pending = False
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
            avatar_b64 = irc_protocol.parse_ctcp_avatar(text)
            if avatar_b64 is not None:
                # 아이콘 교환용 CTCP - 채팅으로 표시하거나 기록에 남기지 않고 캐시만 갱신
                self.chat_page.set_avatar(sender, avatar_b64)
                return
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
                    self._save_login_prefs()
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
                    gui_client.themed_warning(self, "채널 입장 실패", msg.get("text", "실패"))

        elif mtype == "leave_result":
            channel = msg.get("channel", "")
            if msg.get("ok"):
                self._joined_channels.discard(channel)
                self.chat_page.remove_channel(channel)
            else:
                gui_client.themed_warning(self, "채널 나가기 실패", msg.get("text", "실패"))

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

        elif mtype == "member_nickname":
            user_id = msg.get("user_id", "")
            if user_id:
                self.chat_page.set_nickname(user_id, msg.get("nickname"))

        elif mtype == "error":
            text = msg.get("text", "오류")
            if self.stack.currentWidget() is self.login_page:
                self.login_page.show_status(text)
            elif self.stack.currentWidget() is self.channel_page:
                self.channel_page.show_status(text)
            else:
                gui_client.themed_warning(self, "오류", text)
