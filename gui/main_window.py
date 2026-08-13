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
from PySide6.QtNetwork import QAbstractSocket, QSslSocket
from PySide6.QtWidgets import (
    QApplication, QDialog, QLineEdit, QMainWindow, QStackedWidget, QVBoxLayout, QWidget,
)

import app_prefs
import error_log
import avatar_store
import client_version_store
import irc_protocol
import login_prefs
from chat_core import constants
from chat_core.session import build_session
from gui import event_router, liveness
from gui.login_request import parse_login_values
from gui.reconnect import ReconnectPolicy
from gui.tray import TrayIcon
from gui.client_probe import ClientProbeController
from gui.version_prober import VersionProber
from updater import POST_UPDATE_FLAG
from gui.helpers import _friendly_connection_error
from gui.network import ChatClient
from gui.network_probe import WebReachableProbe, blocked_port_message
from gui.pages import ChannelPage, ChatPage, LoginPage
from gui.profile_dialog import ProfileDialog
from gui.startup_page import StartupPage
from gui.theme import (APP_TITLE, CHANNEL_SIDEBAR_COLLAPSED_WIDTH, CHANNEL_SIDEBAR_WIDTH,
                       CONNECT_TIMEOUT_MS, IS_WINDOWS, LIVENESS_CHECK_MS)
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

    # ---------------- 창 조립 ----------------

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
            self._in_event_filter = False
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
        self._intentional_close = False   # 로그아웃/종료처럼 일부러 끊은 것인가
        # "언제 다시 붙을지"는 정책이 정하고, "실제로 붙는 일"만 여기서 한다
        self._reconnect = ReconnectPolicy(self._try_reconnect, self._notify_all_channels, self)

        # 채널/멤버/닉네임/아바타 등 세션 상태는 전부 chat_core.ChatSession이 소유함
        # (예전에는 여기에 _joined_channels/_irc_members/_irc_names_buffer/... 로 흩어져
        # 있었고 cli_client.py에도 같은 게 따로 있었음). 로그인 시도할 때마다 새로 만들지만,
        # 로그인 전에도 None이 아니도록 빈 세션을 하나 둠 - 안 그러면 로그인 전에 호출될 수
        # 있는 경로(예: 채널 추가)에서 None 참조로 죽음. 소켓이 아직 연결 전이라
        # client.send_cmd()는 조용히 무시되므로 예전(연결 전 전송 무시) 동작과 동일함
        self.session = build_session(
            "custom", "", 0, transport=self.client.send_cmd, on_event=self._on_domain_event
        )

        # 창을 닫아도 계속 받으려면 트레이가 필요하다. 트레이가 없는 환경이면
        # available=False로 오고, 그때는 창을 닫는 즉시 종료된다
        self._quitting = False
        self._tray = TrayIcon(self.windowIcon(), self)
        self._tray.open_requested.connect(self.show_from_tray)
        self._tray.quit_requested.connect(self.quit_app)

        # 참여자들이 무슨 프로그램을 쓰는지 알아보는 일 전체(누구에게, 언제, 얼마나
        # 아껴 물을지)는 gui/client_probe.py가 맡는다. 창은 그 담당자만 들고 있는다
        self._prober = VersionProber(self._ask_client_version, self)
        # 알릴 일이 생겼을 때 그 자리에서 채팅 화면을 찾는다. 여기서 chat_page를 바로
        # 넘기면 화면이 아직 만들어지기 전이라 없다(창 조립 순서에 묶이지 않게 함수로 준다)
        self._probe_ctl = ClientProbeController(
            self._prober,
            lambda channel, text: self.chat_page.append_system(channel, text),
            self)
        # 화면이 멈추면 어디서 멈췄는지 기록에 남기는 감시 장치. 살아 있는 동안은
        # 이 타이머가 계속 갱신해줘서 아무 것도 안 찍힌다
        self._alive_timer = QTimer(self)
        self._alive_timer.timeout.connect(error_log.arm_freeze_watchdog)
        self._alive_timer.start(5000)
        error_log.arm_freeze_watchdog()

        # 연결이 살아 있는지 스스로 확인하는 타이머. 조용하면 우리가 먼저 물어보고,
        # 그래도 답이 없으면 서버가 끊기 전에 우리가 먼저 다시 붙는다(gui/liveness.py)
        self._liveness_timer = QTimer(self)
        self._liveness_timer.timeout.connect(self._check_connection_alive)
        self._liveness_timer.start(LIVENESS_CHECK_MS)

        # 업데이트 직후 채팅창에 한 줄 남길 안내(채널에 들어갈 때 소비된다)
        self._pending_update_note = ""
        # 접속 실패 원인 진단용. 서버마다 한 번만 확인하고 결과를 기억한다
        self._probe = None
        self._web_reachable: dict[str, bool] = {}

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
        # 채널 목록 아래 톱니바퀴 - 트레이 메뉴의 '환경설정'과 같은 창을 연다
        # (설정 창을 여는 곳이 둘이지만 여는 코드는 트레이 쪽 하나만 둔다)
        self.chat_page.settings_requested.connect(self._tray.open_settings)
        # 채널 목록을 펼치면 그만큼 **창이 넓어진다**(대화 영역을 뺏지 않는다).
        # 예전에는 창 폭이 그대로라 목록이 펼쳐질 때 대화창이 밀려 좁아졌고, 읽던 줄이
        # 다시 접히면서 화면이 출렁였다. 접을 때는 반대로 창이 좁아진다
        self.chat_page.channel_sidebar.collapsed_changed.connect(self._resize_for_sidebar)

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
    def set_window_icon(self, icon: QIcon):
        self.setWindowIcon(icon)
        self._tray.set_icon(icon)
        if self._title_bar is not None:
            self._title_bar.set_icon(icon)
    # ---------------- 세션에서 파생되는 값들 (같은 사실을 두 곳이 기억하지 않게) ----------------

    @property
    def my_id(self) -> str:
        return self.session.my_id
    # 예전에는 MainWindow에도 my_id/_irc_current_nick/_my_avatar_b64/_protocol_mode를 따로
    # 들고 있어서 세션과 어긋날 여지가 있었음(같은 사실을 두 곳이 기억하는 구조). 전부
    # 세션에서 파생시키면 그런 불일치가 구조적으로 불가능해짐.

    @property
    def _protocol_mode(self) -> str:
        return self.session.protocol_mode
    @property
    def _my_avatar_b64(self) -> str | None:
        return self.session.avatars.get(self.session.my_id)
    @property
    def pending_mode(self) -> str:
        return self.session.pending_auth_mode
    # ---------------- 화면 흐름 (시작 -> 로그인 -> 채널 -> 채팅) ----------------

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
        # 업데이트로 새 버전이 된 뒤 처음 켠 것이면 "뭐가 바뀌었는지"를 한 번 보여준다.
        # 로그인 화면이 뜬 뒤에 띄우는 이유: 시작화면 위에 겹치면 업데이트가 아직 진행
        # 중인 것처럼 보인다. 저절로 닫히지 않으며, 한 버전당 한 번만 뜬다
        QTimer.singleShot(300, self._show_changelog_once)
        # 자동로그인은 로그인 화면이 실제로 보이는 상태에서 시작해야 "연결 중..." 표시와
        # '연결 취소' 버튼이 정상적으로 보임
        QTimer.singleShot(100, self._maybe_auto_login)
    def _show_changelog_once(self):
        """업데이트 뒤 처음 켰으면 변경 내역 창을 띄우고, 채팅에도 한 줄 남길 준비를 한다.

        창만 띄우면 닫는 순간 사라져서 "뭐가 바뀐 거였지?" 할 때 볼 곳이 없다.
        그래서 채널에 들어갈 때 대화창에도 한 줄 남긴다(나에게만 보이는 안내다).
        """
        from gui import changelog_dialog

        notes = changelog_dialog.load_notes()
        if changelog_dialog.show_if_updated(self) and notes:
            self._pending_update_note = changelog_dialog.summary_line(notes)
    def take_update_note(self) -> str:
        """채널에 들어갈 때 한 번만 쓰고 비운다."""
        note, self._pending_update_note = self._pending_update_note, ""
        return note
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
    def _is_pre_login(self) -> bool:
        """아직 로그인 전 화면(시작화면/로그인화면)에 있는지.

        자동로그인은 시작화면 직후에 걸리기 때문에 login_page만 보면 안 됨 - 시작화면을
        도입했을 때 로그인 성공 후 화면 전환이 안 되는 버그가 실제로 이걸로 생겼었음.
        """
        return self.stack.currentWidget() in (self.startup_page, self.login_page)
    def show_page(self, page):
        self.stack.setCurrentWidget(page)
    def current_page(self):
        return self.stack.currentWidget()
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
    def _handle_all_channels_left(self):
        """마지막 채널까지 나가면 채널 선택 화면으로 돌아감(빈 채팅 화면에 갇히지 않게).
        연결은 그대로 유지하므로 바로 다른 채널에 들어갈 수 있음"""
        if self.stack.currentWidget() is self.chat_page:
            self.channel_page.show_status("")
            self.stack.setCurrentWidget(self.channel_page)
    def _notify_all_channels(self, text: str):
        """지금 열어둔 모든 채널에 안내를 남김. 채널이 없으면 보고 있는 화면에 표시."""
        channels = self.chat_page.open_channels()
        if not channels:
            # 아직 채널에 안 들어간 상태(채널 선택 화면)에서 끊긴 경우 - 지금 보고 있는
            # 화면에 띄워야 보임
            page = (self.channel_page if self.stack.currentWidget() is self.channel_page
                    else self.login_page)
            page.show_status(text, error=False)
            return
        for channel in channels:
            self.chat_page.append_system(channel, text)
    # ---------------- 접속 / 재접속 / 연결 확인 ----------------

    def _handle_login_submit(self, mode: str):
        """로그인/회원가입 버튼 -> 입력값 검사 -> 세션 준비 -> 접속.

        검사는 gui/login_request.py의 순수 함수가 하고, 여기서는 화면과 소켓만 다룬다.
        """
        request, problem = parse_login_values(self.login_page.get_values())
        if request is None:
            self.login_page.show_status(problem)
            return

        self._auth_mode = mode  # "login" 또는 "register" - 연결 완료 후 어느 쪽을 보낼지
        self._cancel_reconnect()
        self._intentional_close = False  # 이제부터 예기치 않게 끊기면 다시 붙어야 함
        self._remember(request)
        self.chat_page.set_protocol_mode(request.protocol)
        self._start_session(request)

        if self.client.state() == QSslSocket.SocketState.ConnectedState:
            # 이미 연결돼 있으면 (예: 회원가입 후 바로 로그인) 재연결하지 않고 바로 전송
            self._on_connected()
            return
        self._connect_to(request)
    def _start_session(self, request):
        """로그인 시도마다 도메인 세션을 새로 만듦 - 이전 세션의 채널/멤버 상태가 안 섞이게.

        프로토콜에 맞는 전송 방식만 꽂아주면 나머지 상태 로직은 전부 코어가 담당한다.
        """
        transport = self.client.send_irc if request.is_irc else self.client.send_cmd
        self.session = build_session(
            request.protocol, request.host, request.port,
            transport=transport, on_event=self._on_domain_event,
        )
        # '/'만 쳐도 명령 목록이 뜨게 - 지원 명령은 프로토콜마다 다르므로 코어에서 받아옴
        self.chat_page.set_command_specs(self.session.command_specs())
    def _connect_to(self, request):
        self.login_page.show_status(
            f"연결 중... ({request.mode_label}, 최대 10초, 언제든 '연결 취소' 가능)",
            error=False)
        self.login_page.set_connecting(True)
        self._connecting = True
        self._connect_timer.start(CONNECT_TIMEOUT_MS)
        self.client.set_mode(request.protocol)
        try:
            self.client.connect_to_server(
                request.host, request.port, request.cert_path, request.use_ssl)
        except Exception as e:  # noqa: BLE001
            self._stop_connecting()
            self.login_page.show_status(f"오류: {e}")
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
    def _on_connect_timeout(self):
        if not self._connecting:
            return
        was_auth_phase = self._auth_phase
        self._stop_connecting()
        self.client.abort()
        if self._reconnect.active:
            self._reconnect.schedule()  # 붙긴 했는데 로그인 응답이 없음 - 다음 간격에 다시
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
            # 포트가 막힌 네트워크에서는 거절도 안 오고 그냥 조용히 시간만 흐른다.
            # 그래서 이 경로가 '학교 와이파이에서 안 된다'의 실제 모습이다
            timeout_message = f"연결 시간이 초과되었습니다. ({CONNECT_TIMEOUT_MS // 1000}초)"
            self.login_page.show_status(timeout_message)
            self._diagnose_network(timeout_message)
    def _on_connection_failed(self, err: str):
        if not self._connecting:
            # 사용자가 취소했거나 타임아웃으로 이미 처리된 경우 - 중복 메시지 방지
            return
        self._stop_connecting()
        if self._reconnect.active:
            self._reconnect.schedule()  # 서버가 아직 안 살아났음 - 다음 간격에 다시
            return
        if self._is_pre_login():
            friendly = _friendly_connection_error(err, self._pending_ssl, self.client._pinned_cert)
            self.login_page.show_status(friendly)
            self._diagnose_network(friendly)
    def _handle_cancel_connect(self):
        if not self._connecting:
            return
        self._stop_connecting()
        self.client.abort()
        self.login_page.show_status("연결을 취소했습니다.", error=False)
    def _stop_connecting(self):
        self._connecting = False
        self._auth_phase = False
        self._connect_timer.stop()
        self.login_page.set_connecting(False)
    def _diagnose_network(self, fallback_message: str):
        """접속 실패가 '네트워크가 막은 것'인지 확인해서 안내를 더 정확하게 바꾼다.

        학교/회사 와이파이는 웹(80/443)만 열어두는 경우가 많다. 그런 곳에서는 홈페이지는
        열리는데 채팅만 안 되므로 사용자는 원인을 알 길이 없다(실제 신고 사례).
        같은 서버의 웹 포트가 열려 있으면 서버는 살아 있다는 뜻이므로 그렇게 알려준다.
        """
        if not self._host:
            return
        known = self._web_reachable.get(self._host)
        if known is not None:
            # 이미 확인해 본 서버 - 다시 두드리지 않는다. 접속 실패는 여러 번 날 수 있는데
            # 그때마다 검사를 새로 돌리면 기다리는 시간만 쌓인다(실측: 테스트가 7초에서
            # 66초로 늘어났다)
            if known and self._is_pre_login():
                self.login_page.show_status(blocked_port_message(self._host, self._port))
            return
        if self._probe is not None:
            self._probe.cancel()      # 앞서 돌던 검사는 버린다(결과가 늦게 와서 덮지 않게)
        self._probe = WebReachableProbe(self)

        host = self._host

        def done(web_reachable: bool):
            self._web_reachable[host] = web_reachable
            if self._connecting:
                return   # 사용자가 다시 접속을 시도하는 중 - 지금 화면 문구를 건드리면 안 된다
            if not self._is_pre_login():
                return   # 그 사이에 사용자가 다른 화면으로 갔으면 건드리지 않는다
            if web_reachable:
                self.login_page.show_status(blocked_port_message(self._host, self._port))
            else:
                self.login_page.show_status(fallback_message)

        self._probe.finished.connect(done)
        self._probe.start(self._host)
    def _resize_for_sidebar(self, collapsed: bool):
        """채널 목록이 접히고 펴진 만큼 창 폭을 함께 줄이고 늘린다.

        최대화 상태이거나 화면 밖으로 나가게 되는 경우에는 창을 건드리지 않는다 -
        그때는 예전처럼 안에서 나눠 쓰는 수밖에 없다.
        """
        delta = CHANNEL_SIDEBAR_WIDTH - CHANNEL_SIDEBAR_COLLAPSED_WIDTH
        if collapsed:
            delta = -delta
        if self.isMaximized() or self.isFullScreen():
            return
        target = self.width() + delta
        screen = self.screen()
        if screen is not None:
            available = screen.availableGeometry()
            # 화면을 넘어서면 넘어서는 만큼만 포기한다(아예 안 늘리면 대화창이 그대로
            # 좁아져서, 고치려던 증상이 그 상황에서만 되살아난다)
            target = min(target, available.width())
            if self.x() + target > available.right():
                self.move(max(available.left(), available.right() - target + 1), self.y())
        self.resize(max(self.minimumWidth(), target), self.height())

    def _check_connection_alive(self):
        """조용한 연결이 진짜 살아 있는지 확인한다.

        TCP는 상대가 조용히 사라져도 남은 쪽이 한참 모른다(노트북이 잠들거나 와이파이가
        연결을 버리는 경우). 그동안 화면에는 멀쩡히 접속된 것처럼 보이고 보낸 메시지는
        그냥 사라진다. 서버(UnrealIRCd)는 180초 동안 우리 응답이 없으면 끊어버리는데,
        그때는 이미 "왜 팅겼는지" 모르는 상태가 된다. 그래서 우리가 먼저 확인한다.
        """
        if self._is_pre_login() or self._intentional_close or not self.session.my_id:
            return
        if self.client.state() != QAbstractSocket.SocketState.ConnectedState:
            return
        # 회선이 바뀌어 이름이 밀렸으면(Mong -> Mong_) 원래 이름을 되찾아 본다.
        # 유령 세션은 서버가 핑 타임아웃으로 정리하므로, 그때가 되면 이 시도가 성공한다
        self.session.reclaim_nickname()
        silence = time.time() - getattr(self.client, "last_rx_at", time.time())
        action = liveness.action_for(silence)
        if action == liveness.PING:
            self.session.keepalive()
        elif action == liveness.DEAD:
            # 살아 있으면 핑에 곧바로 답이 온다. 그래도 조용하다면 죽은 연결이다 -
            # 끊어서 평소의 재접속 절차를 태운다(가만히 두면 영영 모른다)
            error_log.log_text(
                f"{int(silence)}초 동안 아무 것도 오지 않아 죽은 연결로 판단하고 다시 붙습니다.",
                tag="연결 확인")
            self.client.abort()
    def _on_socket_disconnected(self):
        """서버와의 연결이 끊어졌을 때. 일부러 끊은 게 아니면 재접속 정책에 맡긴다.

        예전엔 끊김을 알려주는 경로가 아예 없어서, 서버가 죽어도 화면상으론 멀쩡해 보이고
        메시지만 조용히 안 나갔음."""
        if self._intentional_close or self._is_pre_login() or not self.session.my_id:
            return
        self._reconnect.start(self.session.joined_channels)
    def _try_reconnect(self):
        """재접속 정책이 "지금 붙어라"고 할 때 실제로 하는 일."""
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
        # 세션을 새로 만들었으므로 내 아이콘 기억도 새로 심어줘야 함. 안 그러면 재접속
        # 뒤 IRC에서 남들에게 내 아이콘이 안 뿌려지고 프로필 창도 비어 보임
        self.session.restore_my_profile(avatar_store.load_avatars().get(self.session.my_id))
        for channel in self._reconnect.succeeded():
            self.session.join_channel(channel)
    def _cancel_reconnect(self):
        self._reconnect.cancel()
    def _remember(self, request):
        """다시 접속할 때(재접속 포함) 쓰려고 이번 접속 정보를 기억해둠."""
        self._pending_user_id = request.user_id
        self._pending_password = request.password
        self._pending_cert_path = request.cert_path
        self._pending_auto_login = request.auto_login
        self._pending_ssl = request.use_ssl
        self._host = request.host
        self._port = request.port
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
    def _say_goodbye(self, reason: str):
        """끊기 전에 서버에 "나갑니다"라고 알린다(IRC는 QUIT).

        안 보내고 그냥 소켓을 닫으면 서버는 한참 뒤 핑 응답이 없어서야 알아챈다. 그동안
        채널 사람들 목록에는 유령처럼 남아 있고 나중에 "Ping timeout"으로 나갔다고 뜬다.

        쓴 줄이 실제로 나갈 때까지 잠깐 기다린다 - write()는 예약만 하므로, 곧바로
        소켓을 닫으면 그 줄이 사라져서 보낸 의미가 없다.
        """
        try:
            self.session.disconnect_gracefully(reason)
            self.client.flush_pending()
        except Exception:  # noqa: BLE001 - 끝내는 중이라 무슨 일이 있어도 종료는 돼야 한다
            pass
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
        self._say_goodbye("로그아웃")
        self.client.abort()
        self.session = build_session(
            "custom", "", 0, transport=self.client.send_cmd, on_event=self._on_domain_event
        )
        self.chat_page.reset()
        self._probe_ctl.reset()   # 서버가 바뀌면 사람도 프로그램도 다른 세상이다
        self.login_page.show_status("")
        self.stack.setCurrentWidget(self.login_page)
    # ---------------- 도메인 이벤트 -> 화면 ----------------

    # 예전에는 이 두 메서드가 각각 150줄/70줄짜리 거대한 분기문이었고, 같은 로직이
    # cli_client.py에도 따로 구현돼 있었음. 지금은 해석을 전부 chat_core가 하고
    # 여기서는 원시 메시지를 넘기기만 함 - GUI/CLI가 같은 코어를 공유하게 됨.
    def _on_irc_line(self, msg: irc_protocol.IrcMessage):
        self.session.handle_incoming(msg)
    def _on_message(self, msg: dict):
        self.session.handle_incoming(msg)
    def _on_domain_event(self, event):
        """코어가 발행한 이벤트를 화면에 반영하는 유일한 지점.

        무엇을 할지는 gui/event_router.py의 표가 정한다. 예전엔 이 메서드 하나가
        isinstance 149줄 사슬이어서, 이벤트를 하나 늘릴 때마다 여기를 열어야 했다.
        """
        event_router.route(self, event)
    def _handle_send(self, channel: str, text: str):
        self.session.send_message(channel, text)
    # ---------------- event_router가 쓰는 창구 (라우터가 창 내부 사정을 몰라도 되게) ----------------

    def warn(self, title: str, text: str):
        import gui_client  # 지연 import - 이유는 파일 맨 위 docstring 참고
        gui_client.themed_warning(self, title, text)
    # 아래는 event_router가 화면을 만질 때 쓰는 창구. 라우터가 MainWindow 내부 사정을
    # 몰라도 되게(그래서 라우터만 따로 테스트할 수 있게) 이름을 정리해서 열어둔다

    def is_pre_login(self) -> bool:
        return self._is_pre_login()
    @property
    def protocol_mode(self) -> str:
        return self._protocol_mode
    def stop_connecting(self):
        self._stop_connecting()
    def save_login_prefs(self):
        self._save_login_prefs()
    @property
    def is_reconnecting(self) -> bool:
        return self._reconnect.active
    def on_reconnect_logged_in(self):
        self._on_reconnect_logged_in()
    def cancel_reconnect(self):
        self._cancel_reconnect()
    def notify_all_channels(self, text: str):
        self._notify_all_channels(text)
    def notify_new_message(self, sender: str, text: str, channel: str):
        """창을 보고 있지 않을 때만 오른쪽 아래에 알림을 띄운다.

        보고 있는데도 뜨면 방해만 된다 - 창이 떠 있고 활성 상태면 화면에 이미 보인다.
        """
        if self.isVisible() and self.isActiveWindow():
            return
        self._tray.notify(sender, text, channel)
    def recent_server_lines(self) -> list:
        return self.client.recent_lines()
    # 누가 무슨 프로그램을 쓰는지 알아보는 일은 gui/client_probe.py가 전담한다.
    # 창은 "그 일을 시키는 창구"만 남긴다(event_router가 이 이름으로 부른다)
    def probe_client_versions(self, channel: str):
        self._probe_ctl.probe(self.session, self._host, channel)
    def note_server_message(self, text: str) -> bool:
        return self._probe_ctl.note_server_message(self.session, self._host, text)
    def _ask_client_version(self, user_id: str):
        self.session.request_client_version(user_id)
    def remember_client_version(self, user_id: str, version: str):
        """알아낸 것을 서버별로 적어둔다 - 다음에 켤 때는 안 물어봐도 된다."""
        client_version_store.remember(self._host, user_id, version)
    # ---------------- 프로필 / 치트 ----------------

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
    def play_cheat(self, cheat_id: str):
        """치트 효과 재생. 모르는 치트는 조용히 무시한다."""
        import gui_client  # 지연 import - 이유는 파일 맨 위 docstring 참고
        effect = self._CHEAT_EFFECTS.get(cheat_id)
        if effect is None:
            return
        effect(self.chat_page)
        gui_client._flash_taskbar_icon(self)
    # ---------------- 창 동작 (닫기/트레이/크기 조절) ----------------

    def closeEvent(self, event):
        """창의 X는 '종료'가 아니라 '치우기'다.

        메신저는 창을 닫았다고 나가버리면 곤란하다. 창만 숨기고 연결은 유지하다가,
        트레이 아이콘 메뉴에서 '종료'를 눌러야 실제로 끝난다(그때는 _quitting이 켜진다).
        트레이를 못 쓰는 환경이거나 설정에서 껐으면 예전처럼 그냥 종료한다.
        """
        if not self._quitting and self._tray.available and app_prefs.get("close_to_tray"):
            event.ignore()
            self.hide()
            # 안내는 처음 한 번만. 닫을 때마다 뜨면 성가시기만 하다
            if not app_prefs.get("tray_hint_shown"):
                app_prefs.set_value("tray_hint_shown", True)
                self._tray.notify(APP_TITLE, "창을 닫아도 계속 받습니다. 종료하려면 "
                                             "이 아이콘을 우클릭해 '종료'를 누르세요.")
            return
        # 종료하면서 소켓이 끊기는 것도 disconnected로 오므로, 여기서 미리 막지 않으면
        # 앱이 닫히는 중에 재접속 타이머가 걸림
        self._intentional_close = True
        self._cancel_reconnect()
        self._say_goodbye("종료")
        self._tray.hide()
        super().closeEvent(event)
    def changeEvent(self, event):
        # 버튼 클릭이 아니라 더블클릭/에어로 스냅 등 다른 경로로 최대화 상태가
        # 바뀌어도 타이틀바의 최대화<->복원 아이콘이 항상 실제 상태와 맞도록 동기화
        if event.type() == event.Type.WindowStateChange and self._title_bar is not None:
            self._title_bar.set_maximized(self.isMaximized())
        super().changeEvent(event)
    def eventFilter(self, obj, event):
        # 프레임 없는 창은 OS가 알아서 해주던 가장자리 크기조절이 사라지므로,
        # 자식 위젯이 마우스 이벤트를 먼저 가로채기 전에(앱 전역 이벤트 필터라 위젯
        # 디스패치보다 먼저 통과함) 창 가장자리 근처인지 직접 확인해서
        # QWindow.startSystemResize()로 OS의 네이티브 크기조절 루프를 그대로 넘김
        et = event.type()
        if et not in (QEvent.Type.MouseMove, QEvent.Type.MouseButtonPress):
            return super().eventFilter(obj, event)   # 앱 전체를 지나가는 필터라 빨리 빠진다
        if self._in_event_filter:
            # **여기로 다시 들어오면 안 된다.** 아래에서 커서 모양을 바꾸면 Qt가 그 자리에
            # 마우스 이벤트를 다시 흘리는데, 이 필터는 앱 전체(QApplication)에 걸려 있어서
            # 그 이벤트가 또 여기로 들어온다. 그러면 끝없이 파고들다 스택이 넘쳐 앱이
            # 그냥 사라진다(파이썬 오류가 아니라 프로세스가 죽는 것이라 기록도 안 남았다).
            # 실제 사고 2026-08-13: friendchat_error.log에
            #   "Windows fatal exception: stack overflow ... in eventFilter"
            return False
        if not isinstance(obj, QWidget) or obj.window() is not self:
            return super().eventFilter(obj, event)
        self._in_event_filter = True
        try:
            local_pos = self.mapFromGlobal(event.globalPosition().toPoint())
            edges = self._resize_edges_at(local_pos)
            if et == QEvent.Type.MouseMove:
                key = frozenset(e for e in (Qt.Edge.TopEdge, Qt.Edge.BottomEdge,
                                            Qt.Edge.LeftEdge, Qt.Edge.RightEdge) if edges & e)
                shape = _RESIZE_EDGE_CURSORS.get(key, Qt.CursorShape.ArrowCursor)
                # **바뀔 때만 바꾼다.** 마우스가 움직일 때마다 setCursor를 부르면 위에서
                # 말한 되돌이의 출발점이 되고, 어차피 같은 모양이라 화면에도 변화가 없다
                if self.cursor().shape() != shape:
                    self.setCursor(shape)
            elif edges and event.button() == Qt.MouseButton.LeftButton:
                handle = self.windowHandle()
                if handle is not None:
                    handle.startSystemResize(edges)
                    return True
        finally:
            self._in_event_filter = False
        return super().eventFilter(obj, event)
    def show_from_tray(self):
        """트레이에서 다시 창을 꺼냄. 최소화돼 있었으면 원래 크기로 되돌린다."""
        self.showNormal()
        self.raise_()
        self.activateWindow()
    def quit_app(self):
        """트레이 메뉴의 '종료' - 이제 진짜로 끝낸다."""
        self._quitting = True
        self.close()
        QApplication.instance().quit()
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
