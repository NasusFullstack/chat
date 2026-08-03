"""메인 윈도우 - 로그인/채널입장/채팅 화면을 QStackedWidget으로 전환하며 프로토콜 메시지를 처리함.

themed_get_text/themed_warning은 테스트가 g.themed_warning = fake처럼 gui_client 모듈에
직접 몽키패치하는 대상임 - 그래서 호출하는 메서드 본문 안에서 `import gui_client`를 한 뒤
`gui_client.themed_warning(...)`처럼 모듈 속성으로 조회해서 호출함. 이 import를 파일 맨
위에 두면 PyInstaller로 빌드한 실행 파일에서 순환참조 크래시가 남(로컬 CPython에서는
통과하지만 프로즌 임포터는 버전에 따라 덜 관대함 - 실제로 사고가 났었음) - 자세한 이유는
gui_client.py 상단 주석 참고.
"""
import sys
import time

from PySide6.QtCore import QEvent, QPoint, Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtNetwork import QSslSocket
from PySide6.QtWidgets import (
    QApplication, QDialog, QLineEdit, QMainWindow, QStackedWidget, QVBoxLayout, QWidget,
)

import avatar_store
import error_log
import irc_protocol
import login_prefs
from chat_core import constants, events as domain_events
from chat_core.session import build_session
from updater import POST_UPDATE_FLAG
from gui.helpers import _friendly_connection_error
from gui.network import ChatClient
from gui.pages import ChannelPage, ChatPage, LoginPage
from gui.profile_dialog import ProfileDialog
from gui.startup_page import StartupPage
from gui.theme import (APP_TITLE, CONNECT_TIMEOUT_MS, IS_WINDOWS, RECONNECT_BASE_MS,
                       RECONNECT_MAX_ATTEMPTS, RECONNECT_MAX_MS)
from gui.title_bar import TitleBar
from version import APP_VERSION

# 시작화면을 최소한 이만큼은 보여줌 - 업데이트가 없을 때 로고가 깜빡하고 사라지면
# 오히려 뭔가 잘못된 것처럼 보임
_SPLASH_MIN_MS = 900
# 업데이트 직후 재실행된 경우엔 이미 오래 기다린 뒤라 로고를 짧게만 보여주고 넘어감
_SPLASH_POST_UPDATE_MS = 400

# 로그인 폼(카드 582px) + 커스텀 타이틀바(36px) + 위아래 여백이 스크롤 없이 다 들어가는 크기.
# 이 화면들은 크기를 고정해서 내용이 잘리거나 휠을 굴려야 하는 일이 없게 함
_FORM_FIXED_SIZE = (560, 700)
# 채팅 화면은 자유롭게 조절 가능 - 다만 너무 줄이면 탭/참여자 목록이 뭉개져서 하한만 둠
_CHAT_DEFAULT_SIZE = (860, 700)
_CHAT_MIN_SIZE = (620, 520)

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

    # 치트 id -> 화면 동작. if/elif를 늘리는 대신 표에 한 줄 추가하는 형태로 둠.
    # 모르는 id는 조용히 무시되므로, 새 치트를 쓰는 사람과 구버전 클라이언트가 같은
    # 채널에 있어도 구버전이 죽지 않음
    _CHEAT_EFFECTS = {
        constants.CHEAT_RESOURCES: lambda page: page.show_resource_cheat(),
        constants.CHEAT_BATTLECRUISER_SUMMON: lambda page: page.summon_battlecruiser(),
        constants.CHEAT_BATTLECRUISER_DISMISS: lambda page: page.dismiss_battlecruiser(),
    }

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_TITLE} v{APP_VERSION}")
        # 크기 정책은 화면마다 다름(_apply_size_policy_for_page 참고):
        # - 로그인/채널/시작 화면: 내용이 스크롤 없이 한 번에 다 보이도록 크기 고정
        # - 채팅 화면: 대화를 넓게 보고 싶을 수 있으므로 자유롭게 크기 조절 가능
        self.resize(*_CHAT_DEFAULT_SIZE)

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
        self.client.disconnected.connect(self._on_socket_disconnected)

        self._connecting = False
        self._auth_phase = False
        self._pending_ssl = True
        # 사용자가 직접 로그아웃해서 로그인 화면으로 돌아온 뒤에는 자동로그인을 다시 걸지 않음
        self._auto_login_suppressed = False
        self._host = ""
        self._port = 0

        # ---- 끊겼을 때 자동 재접속 ----
        # 예전엔 끊김을 알려주는 경로가 아예 없어서, 서버가 죽어도 화면상으론 멀쩡해 보이고
        # 메시지만 조용히 안 갔음("나갔는지 알 수가 없다")
        self._reconnecting = False        # 지금 자동 재접속 시도 중인가
        self._intentional_close = False   # 로그아웃/종료처럼 일부러 끊은 것인가
        self._reconnect_attempt = 0
        self._channels_to_restore: list[str] = []
        self._reconnect_timer = QTimer(self)
        self._reconnect_timer.setSingleShot(True)
        self._reconnect_timer.timeout.connect(self._try_reconnect)

        # 채널/멤버/닉네임/아바타 등 세션 상태는 전부 chat_core.ChatSession이 소유함
        # (예전에는 여기에 _joined_channels/_irc_members/_irc_names_buffer/... 로 흩어져
        # 있었고 cli_client.py에도 같은 게 따로 있었음). 로그인 시도할 때마다 새로 만들지만,
        # 로그인 전에도 None이 아니도록 빈 세션을 하나 둠 - 안 그러면 로그인 전에 호출될 수
        # 있는 경로(예: 채널 추가)에서 None 참조로 죽음. 소켓이 아직 연결 전이라
        # client.send_cmd()는 조용히 무시되므로 예전(연결 전 전송 무시) 동작과 동일함
        self.session = build_session(
            "custom", "", 0, transport=self.client.send_cmd, on_event=self._on_domain_event
        )

        self._connect_timer = QTimer(self)
        self._connect_timer.setSingleShot(True)
        self._connect_timer.timeout.connect(self._on_connect_timeout)

        self.stack = QStackedWidget()

        # 화면 순서 = 실제 사용 흐름 순서: 시작(로고) -> 로그인 -> 채널선택 -> 채팅
        self.startup_page = StartupPage()
        self.login_page = LoginPage(self._handle_login_submit, self._handle_cancel_connect)
        self.channel_page = ChannelPage(self._handle_channel_submit, self._handle_back_to_login)
        self.chat_page = ChatPage(
            self._handle_send, self._handle_add_channel, self._handle_leave_channel,
            self._handle_set_avatar, self._handle_all_channels_left,
        )

        self.stack.addWidget(self.startup_page)
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

        # 화면이 바뀔 때마다 그 화면에 맞는 크기 정책을 적용
        self.stack.currentChanged.connect(self._apply_size_policy_for_page)
        self._apply_size_policy_for_page(self.stack.currentIndex())

    def _apply_size_policy_for_page(self, _index: int):
        """채팅 화면만 크기 조절을 허용하고, 폼 화면들은 내용이 다 보이는 크기로 고정.

        로그인 폼은 항목이 많아서 창이 작으면 잘리거나 스크롤해야 했음. 어차피 폼 화면은
        크게 볼 이유가 없으니 아예 고정해두는 게 낫고, 대화 내용을 넓게 보고 싶은
        채팅 화면만 자유롭게 열어둠.
        """
        is_chat = self.stack.currentWidget() is self.chat_page
        if is_chat:
            self.setMinimumSize(*_CHAT_MIN_SIZE)
            self.setMaximumSize(16777215, 16777215)  # Qt의 '제한 없음' 기본값
            if self.size().width() < _CHAT_DEFAULT_SIZE[0]:
                self.resize(*_CHAT_DEFAULT_SIZE)
        else:
            # 최소=최대로 두면 사용자가 가장자리를 끌어도 크기가 안 바뀜
            self.setFixedSize(*_FORM_FIXED_SIZE)

    def start_boot_sequence(self):
        """창이 화면에 뜬 뒤 호출 - 시작화면에서 업데이트를 확인/적용하고 로그인으로 넘어감.

        창을 먼저 띄우고 그 다음에 업데이트를 확인하는 순서는 반드시 지켜야 함: 반대로 하면
        업데이트가 계속 실패하는 환경에서 앱 화면을 한 번도 못 보여줌(실제 사고 이력).
        """
        self.stack.setCurrentWidget(self.startup_page)
        if POST_UPDATE_FLAG in sys.argv:
            # 방금 업데이트를 마치고 다시 실행된 참 - 업데이트를 또 확인할 필요가 없고,
            # 사용자는 이미 한참 기다렸으므로 로고도 짧게만 보여주고 바로 로그인으로 감
            self.startup_page.set_status("업데이트 완료! 시작하는 중...")
            QTimer.singleShot(_SPLASH_POST_UPDATE_MS, self._go_to_login)
            return
        QTimer.singleShot(_SPLASH_MIN_MS, self._boot_check_update)

    def _boot_check_update(self):
        from gui import update_flow

        self.startup_page.set_status("업데이트 확인 중...")
        QApplication.processEvents()
        if update_flow.check_and_apply(self.startup_page):
            # 업데이트 적용 중 - 곧 이 프로세스가 끝나고 새 버전이 뜸. 그동안 창이 그냥
            # 멈춰 보이지 않도록 안내 문구를 남겨둠(설치가 끝날 때까지 이 화면이 유지됨)
            self.startup_page.set_status("업데이트를 설치하고 있습니다. 곧 자동으로 다시 시작됩니다...")
            QApplication.processEvents()
            return
        self.startup_page.hide_progress()
        self._go_to_login()

    def _go_to_login(self):
        self.stack.setCurrentWidget(self.login_page)
        # 자동로그인은 로그인 화면이 실제로 보이는 상태에서 시작해야 "연결 중..." 표시와
        # '연결 취소' 버튼이 정상적으로 보임
        QTimer.singleShot(100, self._maybe_auto_login)

    # ---------------- 끊김 감지와 자동 재접속 ----------------

    def _on_socket_disconnected(self):
        """서버와의 연결이 끊어졌을 때. 사용자가 일부러 끊은 게 아니면 다시 붙는다.

        예전엔 끊김을 알려주는 경로가 아예 없어서, 서버가 죽어도 화면상으론 멀쩡해 보이고
        메시지만 조용히 안 나갔음."""
        if self._intentional_close or self._is_pre_login() or not self.session.my_id:
            return
        if self._reconnecting:
            return
        self._reconnecting = True
        self._reconnect_attempt = 0
        # 다시 붙은 뒤 원래 보던 채널로 돌아가기 위해 기억해둠
        self._channels_to_restore = sorted(self.session.joined_channels)
        self._notify_all_channels("서버와의 연결이 끊어졌습니다. 다시 연결하는 중...")
        self._schedule_reconnect()

    def _schedule_reconnect(self):
        """재시도 간격을 점점 늘림 - 서버가 오래 죽어 있을 때 계속 두드리지 않도록"""
        self._reconnect_attempt += 1
        if self._reconnect_attempt > RECONNECT_MAX_ATTEMPTS:
            self._reconnecting = False
            self._notify_all_channels(
                "다시 연결하지 못했습니다. 로그인 화면에서 다시 접속해 주세요."
            )
            return
        delay = min(RECONNECT_BASE_MS * self._reconnect_attempt, RECONNECT_MAX_MS)
        self._notify_all_channels(
            f"다시 연결 시도 {self._reconnect_attempt}/{RECONNECT_MAX_ATTEMPTS}"
            f" ({delay // 1000}초 후)"
        )
        self._reconnect_timer.start(delay)

    def _try_reconnect(self):
        if not self._reconnecting:
            return
        protocol = self._protocol_mode
        self.client.abort()
        self.client.set_mode(protocol)
        # 세션을 새로 만들어야 이전 연결의 채널/멤버 상태가 섞이지 않음
        transport = self.client.send_irc if protocol == "irc" else self.client.send_cmd
        self.session = build_session(
            protocol, self._host, self._port,
            transport=transport, on_event=self._on_domain_event,
        )
        self._auth_mode = "login"
        self._connecting = True
        # 타임아웃을 걸어둬야 "연결도 실패도 안 되고 매달려 있는" 경우에 다음 시도로 넘어감
        # (방화벽이 조용히 버리는 경우가 그렇다 - 실패 신호가 영영 안 온다)
        self._connect_timer.start(CONNECT_TIMEOUT_MS)
        self.client.connect_to_server(
            self._host, self._port, self._pending_cert_path, self._pending_ssl
        )

    def _on_reconnect_logged_in(self):
        """재접속 후 로그인까지 성공했을 때 - 보던 채널로 다시 들어감"""
        self._stop_connecting()
        self._reconnecting = False
        self._reconnect_attempt = 0
        self._notify_all_channels("다시 연결되었습니다.")
        # 세션을 새로 만들었으므로 내 아이콘 기억도 새로 심어줘야 함. 안 그러면 재접속
        # 뒤 IRC에서 남들에게 내 아이콘이 안 뿌려지고 프로필 창도 비어 보임
        self.session.restore_my_profile(avatar_store.load_avatars().get(self.session.my_id))
        for channel in self._channels_to_restore:
            self.session.join_channel(channel)
        self._channels_to_restore = []

    def _cancel_reconnect(self):
        self._reconnect_timer.stop()
        self._reconnecting = False
        self._reconnect_attempt = 0
        self._channels_to_restore = []

    def _notify_all_channels(self, text: str):
        """지금 열어둔 모든 채널에 안내를 남김. 채널이 없으면 로그인 화면에 표시."""
        channels = self.chat_page.open_channels()
        if not channels:
            # 아직 채널에 안 들어간 상태(채널 선택 화면)에서 끊긴 경우 - 지금 보고 있는
            # 화면에 띄워야 보임
            page = self.channel_page if self.stack.currentWidget() is self.channel_page else self.login_page
            page.show_status(text, error=False)
            return
        for channel in channels:
            self.chat_page.append_system(channel, text)

    def _handle_all_channels_left(self):
        """마지막 채널까지 나가면 채널 선택 화면으로 돌아감(빈 채팅 화면에 갇히지 않게).
        연결은 그대로 유지하므로 바로 다른 채널에 들어갈 수 있음"""
        if self.stack.currentWidget() is self.chat_page:
            self.channel_page.show_status("")
            self.stack.setCurrentWidget(self.channel_page)

    def _handle_back_to_login(self):
        """채널 화면에서 로그인 화면으로 되돌아가기(로그아웃).

        연결을 끊고 세션도 새로 비움 - 안 그러면 이전 계정의 채널/멤버 상태가 다음
        로그인에 섞임. 사용자가 직접 되돌아온 것이므로 자동로그인은 이번 실행 동안
        다시 걸지 않음(안 그러면 로그인 화면에 도착하자마자 되돌아온 계정으로 다시
        들어가버려서 계정을 바꿀 수가 없음).
        """
        self._auto_login_suppressed = True
        self._cancel_reconnect()
        self._intentional_close = True  # 일부러 끊는 것이므로 자동 재접속 대상이 아님
        self._stop_connecting()
        self.client.abort()
        self.session = build_session(
            "custom", "", 0, transport=self.client.send_cmd, on_event=self._on_domain_event
        )
        self.chat_page.reset()
        self.login_page.show_status("")
        self.stack.setCurrentWidget(self.login_page)

    # ---------------- 세션에서 파생되는 값들 ----------------
    # 예전에는 MainWindow에도 my_id/_irc_current_nick/_my_avatar_b64/_protocol_mode를 따로
    # 들고 있어서 세션과 어긋날 여지가 있었음(같은 사실을 두 곳이 기억하는 구조). 전부
    # 세션에서 파생시키면 그런 불일치가 구조적으로 불가능해짐.

    @property
    def _protocol_mode(self) -> str:
        return self.session.protocol_mode

    @property
    def my_id(self) -> str:
        return self.session.my_id

    @property
    def _my_avatar_b64(self) -> str | None:
        return self.session.avatars.get(self.session.my_id)

    @property
    def pending_mode(self) -> str:
        return self.session.pending_auth_mode

    def _is_pre_login(self) -> bool:
        """아직 로그인 전 화면(시작화면/로그인화면)에 있는지.

        자동로그인은 시작화면 직후에 걸리기 때문에 login_page만 보면 안 됨 - 시작화면을
        도입했을 때 로그인 성공 후 화면 전환이 안 되는 버그가 실제로 이걸로 생겼었음.
        """
        return self.stack.currentWidget() in (self.startup_page, self.login_page)

    def set_window_icon(self, icon: QIcon):
        self.setWindowIcon(icon)
        if self._title_bar is not None:
            self._title_bar.set_icon(icon)

    def closeEvent(self, event):
        # 종료하면서 소켓이 끊기는 것도 disconnected로 오므로, 여기서 미리 막지 않으면
        # 앱이 닫히는 중에 재접속 타이머가 걸림
        self._intentional_close = True
        self._cancel_reconnect()
        super().closeEvent(event)

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

        self._auth_mode = mode  # "login" 또는 "register" - 연결 완료 후 어느 쪽을 보낼지
        self._cancel_reconnect()
        self._intentional_close = False  # 이제부터 예기치 않게 끊기면 다시 붙어야 함
        self.chat_page.set_protocol_mode(protocol)
        self._pending_user_id = values["user_id"]
        self._pending_password = values["password"]
        self._pending_cert_path = values["cert_path"]
        self._pending_auto_login = values["auto_login"]
        self._host = values["host"]
        self._port = port

        # 로그인 시도마다 도메인 세션을 새로 만듦(이전 세션의 채널/멤버 상태가 안 섞이게).
        # 프로토콜에 맞는 전송 방식만 꽂아주면 나머지 상태 로직은 전부 코어가 담당함
        transport = self.client.send_irc if protocol == "irc" else self.client.send_cmd
        self.session = build_session(
            protocol, values["host"], port,
            transport=transport,
            on_event=self._on_domain_event,
        )
        # '/'만 쳐도 명령 목록이 뜨게 - 지원 명령은 프로토콜마다 다르므로 코어에서 받아옴
        self.chat_page.set_command_specs(self.session.command_specs())

        if self.client.state() == QSslSocket.SocketState.ConnectedState:
            # 이미 연결돼 있으면 (예: 회원가입 후 바로 로그인) 재연결하지 않고 바로 전송
            self._on_connected()
            return

        mode_label = "SSL" if values["ssl"] else "평문(암호화 없음)"
        self.login_page.show_status(
            f"연결 중... ({mode_label}, 최대 10초, 언제든 '연결 취소' 가능)", error=False)
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
        if self._auto_login_suppressed:
            return  # 사용자가 직접 로그아웃해서 돌아온 경우 - 다시 자동으로 들어가면 계정을 못 바꿈
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
        self.login_page.show_status("연결을 취소했습니다.", error=False)

    def _on_connect_timeout(self):
        if not self._connecting:
            return
        was_auth_phase = self._auth_phase
        self._stop_connecting()
        self.client.abort()
        if self._reconnecting:
            self._schedule_reconnect()  # 붙긴 했는데 로그인 응답이 없음 - 다음 간격에 다시
            return
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
            self.login_page.show_status("서버 접속 중... (언제든 '연결 취소' 가능)", error=False)
        else:
            self.login_page.show_status("로그인 확인 중... (언제든 '연결 취소' 가능)", error=False)
        # IRC는 회원가입 개념이 없어서 login()이 곧 등록 핸드셰이크임(프로토콜 전략이 처리)
        if self._auth_mode == "register":
            self.session.register(self._pending_user_id, self._pending_password)
        else:
            self.session.login(self._pending_user_id, self._pending_password)

    def _on_connection_failed(self, err: str):
        if not self._connecting:
            # 사용자가 취소했거나 타임아웃으로 이미 처리된 경우 - 중복 메시지 방지
            return
        self._stop_connecting()
        if self._reconnecting:
            self._schedule_reconnect()  # 서버가 아직 안 살아났음 - 다음 간격에 다시
            return
        if self._is_pre_login():
            friendly = _friendly_connection_error(err, self._pending_ssl, self.client._pinned_cert)
            self.login_page.show_status(friendly)

    # ---------------- 채널 ----------------
    def _handle_channel_submit(self, action: str):
        values = self.channel_page.get_values()
        if not values["channel"]:
            self.channel_page.show_status("채널명을 입력하세요.")
            return
        if action == "create":
            self.session.create_channel(values["channel"], values["key"])
        else:
            self.session.join_channel(values["channel"], values["key"])

    def _handle_add_channel(self):
        """채팅 화면 안에서 채널을 추가로 입장 (기존 채널을 떠나지 않음, 새 채널 생성은 지원 안 함)"""
        import gui_client  # 지연 import - 이유는 파일 맨 위 docstring 참고
        channel, ok = gui_client.themed_get_text(self.chat_page, "채널 추가", "입장할 채널명:")
        channel = channel.strip()
        if not ok or not channel:
            return
        key, ok2 = gui_client.themed_get_text(
            self.chat_page, "채널 추가", "채널 비밀번호 (없으면 비워둠):", QLineEdit.EchoMode.Password
        )
        key = key if ok2 else ""
        self.session.join_channel(channel, key)

    def _handle_leave_channel(self, channel: str):
        self.session.leave_channel(channel)

    def _handle_set_avatar(self):
        import gui_client  # 지연 import - 이유는 파일 맨 위 docstring 참고
        is_irc = self._protocol_mode == "irc"
        # IRC는 닉네임이 곧 접속 식별자라 my_id 자체가 현재 닉네임이고,
        # 커스텀 서버는 아이디와 별개인 표시용 닉네임이 따로 있음(없으면 빈 값)
        current_nickname = self.my_id if is_irc else self.session.nicknames.get(self.my_id, "")
        dlg = ProfileDialog(
            initial_base64=self._my_avatar_b64, initial_nickname=current_nickname, is_irc=is_irc, parent=self.chat_page
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        b64 = dlg.result_base64
        if not self.session.set_avatar(b64):
            gui_client.themed_warning(self, "아이콘 저장 실패", "아이콘 데이터가 너무 큽니다.")
            return

        new_nickname = dlg.result_nickname
        if new_nickname != current_nickname and (new_nickname or not is_irc):
            self.session.set_nickname(new_nickname)

    # ---------------- 채팅 ----------------
    def _handle_send(self, channel: str, text: str):
        self.session.send_message(channel, text)

    # ---------------- 프로토콜 메시지 -> 도메인 코어로 위임 ----------------
    # 예전에는 이 두 메서드가 각각 150줄/70줄짜리 거대한 분기문이었고, 같은 로직이
    # cli_client.py에도 따로 구현돼 있었음. 지금은 해석을 전부 chat_core가 하고
    # 여기서는 원시 메시지를 넘기기만 함 - GUI/CLI가 같은 코어를 공유하게 됨.
    def _on_irc_line(self, msg: irc_protocol.IrcMessage):
        self.session.handle_incoming(msg)

    def _on_message(self, msg: dict):
        self.session.handle_incoming(msg)

    # ---------------- 도메인 이벤트 -> 화면 갱신 ----------------
    def _on_domain_event(self, event):
        """코어가 발행한 이벤트를 Qt 위젯에 반영하는 유일한 지점.

        여기서는 "무엇을 보여줄지"만 결정하고, "무슨 일이 일어났는지"에 대한 판단
        (로그인 성공 여부, 멘션 여부, 쿨타임 등)은 이미 코어가 끝낸 상태로 넘어옴.
        """
        import gui_client  # 지연 import - 이유는 파일 맨 위 docstring 참고

        if isinstance(event, domain_events.LoggedIn):
            self.chat_page.my_id = event.user_id
            if self._reconnecting:
                self._on_reconnect_logged_in()
                return
            # 아직 로그인 단계에 있을 때만 채널 화면으로 넘어감. IRC 닉네임 변경도
            # LoggedIn을 발생시키는데(내 식별자가 바뀌는 건 같으므로), 그때는 이미 채팅
            # 중이라 화면을 되돌리면 안 됨.
            # 시작화면도 포함해야 함 - 자동로그인은 시작화면 직후에 걸리므로 login_page만
            # 보면 전환이 안 일어남(시작화면 도입 때 실제로 이걸로 깨졌었음)
            if self._is_pre_login():
                self._stop_connecting()
                self.channel_page.set_mode(self._protocol_mode)
                self.stack.setCurrentWidget(self.channel_page)
                self._save_login_prefs()
                # 예전에 이 아이디로 설정해둔 아이콘을 되살림(로컬 저장분).
                # 없으면 아무 일도 안 함 - 커스텀 서버는 어차피 입장 때 서버 값을 다시 내려줌
                self.session.restore_my_profile(avatar_store.load_avatars().get(event.user_id))

        elif isinstance(event, domain_events.RegisterSucceeded):
            self._stop_connecting()
            self.login_page.show_status("회원가입 완료! 이제 로그인하세요.", error=False)

        elif isinstance(event, domain_events.AuthFailed):
            self._stop_connecting()
            if self._reconnecting:
                # 재접속했는데 로그인이 거절됨(비번 변경/계정 삭제 등) - 다시 시도해도 소용없음
                self._cancel_reconnect()
                self._notify_all_channels(f"다시 로그인하지 못했습니다: {event.text}")
                return
            self.login_page.show_status(event.text)

        elif isinstance(event, domain_events.ChannelCreated):
            self.channel_page.show_status("채널 생성 완료! 입장 버튼을 눌러주세요.", error=False)

        elif isinstance(event, domain_events.ChannelJoined):
            # 이미 화면에 있는 채널로 다시 들어온 것 = 재접속 후 복구. 안내와 지난 기록을
            # 또 쌓으면 대화가 두 번 보임(응답이 늦게 오므로 시간 기준 플래그로는 못 거름)
            rejoining = self.chat_page.has_channel(event.channel)
            first_time = self.stack.currentWidget() is self.channel_page
            self.chat_page.add_channel(event.channel, activate=True)
            if first_time:
                self.stack.setCurrentWidget(self.chat_page)
                self.chat_page.focus_input()
            if rejoining:
                return
            self.chat_page.append_system(event.channel, event.text)
            self.chat_page.load_history(event.channel, event.history)

        elif isinstance(event, domain_events.ChannelJoinFailed):
            if self.stack.currentWidget() is self.channel_page:
                self.channel_page.show_status(event.text)
            else:
                gui_client.themed_warning(self, "채널 입장 실패", event.text)

        elif isinstance(event, domain_events.ChannelLeft):
            # 채널에서 빠지면 채팅이 통째로 사라지고 입력창까지 잠긴다. 내가 나가기를
            # 누른 게 아닌데 이 일이 벌어지면 원인을 알 방법이 없으므로, 그 직전에 서버가
            # 보낸 줄들을 같이 남긴다(재현이 안 되는 사고의 유일한 단서)
            error_log.log_text(
                f"채널 {event.channel}에서 빠짐. 직전 수신 내용:\n  "
                + "\n  ".join(self.client.recent_lines()[-15:]),
                tag="채널 이탈",
            )
            self.chat_page.remove_channel(event.channel)

        elif isinstance(event, domain_events.ChannelLeaveFailed):
            gui_client.themed_warning(self, "채널 나가기 실패", event.text)

        elif isinstance(event, domain_events.MessageReceived):
            self.chat_page.append_message(
                event.channel, event.sender, event.text, event.mine, event.ts,
                is_mention=event.is_mention, kind=event.kind,
            )

        elif isinstance(event, domain_events.SystemNotice):
            if not event.channel:
                # 등록 전 NOTICE 등 - 채널이 없으면 로그인 화면 상태줄에 표시
                if self._is_pre_login():
                    # 서버가 보내는 접속 안내(예: hostname을 못 찾아 IP를 대신 쓴다는
                    # 문구)는 오류가 아니므로 빨간색으로 보여주면 안 됨
                    self.login_page.show_status(event.text, error=False)
                return
            self.chat_page.append_system(event.channel, event.text)

        elif isinstance(event, domain_events.UserlistUpdated):
            self.chat_page.update_userlist(event.channel, event.users)

        elif isinstance(event, domain_events.AvatarUpdated):
            self.chat_page.set_avatar(event.user_id, event.avatar_b64)

        elif isinstance(event, domain_events.NicknameUpdated):
            self.chat_page.set_nickname(event.user_id, event.nickname)

        elif isinstance(event, domain_events.NicknameChangeFailed):
            gui_client.themed_warning(self, "닉네임 변경 실패", event.text)

        elif isinstance(event, domain_events.NicknameRetrying):
            self.login_page.show_status(
                f"닉네임이 사용 중이라 '{event.new_nickname}'(으)로 재시도합니다.", error=False
            )

        elif isinstance(event, domain_events.CheatActivated):
            # 그 채널을 보는 사람 모두에게 효과 + 작업표시줄 깜빡임.
            # 치트별 화면 동작은 표로 두고, 없는 치트는 조용히 무시(구버전 클라이언트가
            # 모르는 치트 문구를 받아도 죽지 않게)
            effect = self._CHEAT_EFFECTS.get(event.cheat_id)
            if effect is None:
                return
            effect(self.chat_page)
            gui_client._flash_taskbar_icon(self)

        elif isinstance(event, domain_events.CheatBlocked):
            self.chat_page.show_mention_notice(
                f"치트는 {event.remaining_sec}초 후에 다시 사용할 수 있습니다."
            )

        elif isinstance(event, domain_events.CommandHelp):
            self.chat_page.append_system(event.channel, "사용 가능한 명령")
            for line in event.lines:
                self.chat_page.append_system(event.channel, line)

        elif isinstance(event, domain_events.CommandError):
            self.chat_page.show_mention_notice(event.text)

        elif isinstance(event, domain_events.MentionBlocked):
            self.chat_page.show_mention_notice(
                f"@{event.target_display} 호출은 {event.remaining_sec}초 후에 다시 가능합니다."
            )

        elif isinstance(event, domain_events.ConnectionClosed):
            active = self.chat_page.active_channel()
            if active:
                self.chat_page.append_system(active, f"서버 연결이 종료되었습니다: {event.text}")

        elif isinstance(event, domain_events.GenericError):
            if self._is_pre_login():
                self.login_page.show_status(event.text)
            elif self.stack.currentWidget() is self.channel_page:
                self.channel_page.show_status(event.text)
            else:
                gui_client.themed_warning(self, "오류", event.text)
