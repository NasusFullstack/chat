"""로그인/채널입장/채팅 화면 (LoginPage, ChannelPage, ChatPage).

이 모듈은 themed_get_text/themed_question(gui.themed_dialogs)와 _flash_taskbar_icon/
_shake_window(gui.mention_alerts)를 호출하는데, 이 4개는 테스트가 g.themed_question =
fake처럼 gui_client 모듈에 직접 몽키패치하는 대상임. 그래서 `from gui.themed_dialogs
import themed_question`처럼 모듈 로드 시점에 바로 바인딩하지 않고, 호출하는 메서드
"본문 안에서" `import gui_client`를 한 뒤 `gui_client.themed_question(...)`으로 모듈
속성을 조회함.

주의: 이 import를 파일 맨 위(모듈 최상단)에 두면 안 됨 - PyInstaller로 빌드한 실행
파일에서 "cannot import name 'X' from partially initialized module" 순환참조 오류로
실제로 크래시가 났음(로컬 개발 환경의 CPython에서는 sys.modules 캐싱 덕에 통과했지만,
PyInstaller의 프로즌 임포터는 버전에 따라 모듈 최상단의 순환참조를 CPython만큼
관대하게 처리하지 못함). 함수/메서드 "본문 안에서"의 지연 import는 그 함수가 실제로
호출되는 시점(=gui_client.py의 모든 import가 이미 끝난 뒤)에만 실행되므로 이 문제가
원천적으로 없음 - 자세한 이유는 gui_client.py 상단 주석 참고.
"""
import time

from PySide6.QtCore import Qt, QSize, QStringListModel, QTimer
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QCompleter, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMenu, QPushButton, QScrollArea, QStackedWidget,
    QTabWidget, QVBoxLayout, QWidget,
)

import avatar_store
import login_prefs
import server_registry
from chat_core.commands import COMMAND_PREFIX, KIND_ACTION, KIND_NOTICE, format_emoji
from gui.helpers import (
    _build_unread_dot_icon, _decode_avatar_pixmap, _find_default_cert, _find_logo_image,
    _hashed_avatar_pixmap, _smiley_icon,
)
from gui.theme import (
    ADD_TAB_LABEL, APP_TITLE, AVATAR_LIST_PX, AVATAR_MSG_PX, CHANNEL_ROW_GAP,
    CHANNEL_ROW_HEIGHT, CHANNEL_SCROLL_BTN_PX, CHANNEL_SIDEBAR_WIDTH, COPYRIGHT_YEAR,
    DEFAULT_PLAIN_PORT, DEFAULT_SSL_PORT, DEVELOPER_EMAIL, DEVELOPER_NAME, FOOTER_LOGO_PX,
    UNREAD_BLINK_COLOR, UNREAD_BLINK_COUNT, UNREAD_BLINK_INTERVAL_MS,
)
from version import APP_VERSION
from gui.cheat_overlay import CheatOverlay
from gui.battlecruiser import BattlecruiserOverlay
from gui.link_preview import ImageFetcher
from gui.components.channel_sidebar import ChannelSidebar
from gui.components.message_input import MessageInput
from gui.widgets import ChannelLogView

# 입력창 왼쪽 이모티콘 버튼 - 입력창과 같은 높이의 정사각형
EMOJI_BTN_PX = 34
EMOJI_BTN_ICON_PX = 20

# 참여자 헤더 높이 - 채팅 카드 상단과 참여자 카드 상단을 같은 높이에 두기 위한 값
MEMBER_HEADER_HEIGHT = 34

# 카드(채팅/참여자) 아래와 그 밑 컨트롤(입력창/프로필 버튼) 사이 간격.
# 좌우 열이 같은 값을 써야 아래쪽 버튼 줄이 나란히 놓임
_CARD_TO_CONTROL_GAP = 6


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
        title = QLabel(f"{APP_TITLE} 접속")
        title.setObjectName("title")
        box.addWidget(title)

        # 어느 버전을 쓰고 있는지 한눈에 보이게(문의 받을 때 버전부터 확인하게 되므로)
        version_label = QLabel(f"v{APP_VERSION}")
        version_label.setObjectName("hint")
        box.addWidget(version_label)

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

        self.host_input = QLineEdit("home.pdlab.kr")
        self.host_input.setPlaceholderText("서버 주소")
        box.addWidget(self.host_input)

        self.port_input = QLineEdit(DEFAULT_PLAIN_PORT)
        self.port_input.setPlaceholderText("포트")
        box.addWidget(self.port_input)

        self.ssl_checkbox = QCheckBox("SSL 암호화 사용 (권장, 포트 6697)")
        self.ssl_checkbox.setChecked(False)
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
        # 아이디/비밀번호 칸에서 Enter로 바로 로그인
        self.pw_input.returnPressed.connect(lambda: self.on_submit("login"))
        self.user_input.returnPressed.connect(lambda: self.on_submit("login"))
        box.addWidget(self.pw_input)

        self.auto_login_checkbox = QCheckBox("자동로그인 (다음에 앱을 열면 바로 로그인)")
        box.addWidget(self.auto_login_checkbox)

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
        container.setObjectName("card")   # 로그인/채널 화면의 카드 - QSS에서 테두리/여백을 줌
        container.setLayout(box)
        container.setFixedWidth(360)

        # 로그인 폼은 항목이 많아서 창을 최소 크기로 줄이면 카드가 잘림(실측: 582px 필요,
        # 최소 창에선 486px만 확보). 스크롤 영역에 담아 어떤 창 크기에서도 다 볼 수 있게 함
        holder = QWidget()
        holder_layout = QVBoxLayout(holder)
        holder_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        holder_layout.setContentsMargins(0, 12, 0, 12)
        holder_layout.addWidget(container)

        scroll = QScrollArea()
        scroll.setObjectName("plainScroll")  # 테두리/배경 없는 스크롤 영역(QSS에서 처리)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(holder)
        layout.addWidget(scroll)
        self.setLayout(layout)

        self._reload_servers()
        # 이 시점엔 user_input/pw_input 등 관련 위젯이 전부 만들어져 있어야
        # _on_protocol_changed가 안전하게 실행됨 (그래서 protocol_combo 생성 시점이
        # 아니라 __init__ 맨 마지막에서 기본값을 IRC로 바꿈)
        self.protocol_combo.setCurrentIndex(self.protocol_combo.findData("irc"))
        self._load_saved_prefs()

    def _load_saved_prefs(self):
        """예전에 로그인했던 아이디/서버 정보를 미리 채워둠. 자동로그인을 켜둔 적이
        있으면 비밀번호까지 채우고 체크박스도 켜서, MainWindow가 이어서 자동으로
        로그인을 시도할 수 있게 함(비밀번호는 자동로그인을 켠 경우에만 저장돼있음)"""
        prefs = login_prefs.load()
        if not prefs:
            return
        if prefs.get("host"):
            self.host_input.setText(prefs["host"])
        if prefs.get("port"):
            self.port_input.setText(str(prefs["port"]))
        if "ssl" in prefs:
            self.ssl_checkbox.setChecked(bool(prefs["ssl"]))
        if prefs.get("cert_path"):
            self.cert_input.setText(prefs["cert_path"])
        proto = prefs.get("protocol")
        if proto:
            idx = self.protocol_combo.findData(proto)
            if idx >= 0:
                self.protocol_combo.setCurrentIndex(idx)
        if prefs.get("user_id"):
            self.user_input.setText(prefs["user_id"])
        if prefs.get("auto_login"):
            # IRC는 비밀번호 없이 접속하는 게 보통이라(NickServ 비번은 선택),
            # 비밀번호가 비어있어도 자동로그인 자체는 걸려야 함 - password 존재 여부로
            # 게이트를 걸면 안 됨
            self.pw_input.setText(prefs.get("password", ""))
            self.auto_login_checkbox.setChecked(True)

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
        import gui_client  # 지연 import - 이유는 파일 맨 위 docstring 참고
        name, ok = gui_client.themed_get_text(self, "공용서버 등록", "서버 이름:")
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
        import gui_client  # 지연 import - 이유는 파일 맨 위 docstring 참고
        data = self.server_combo.itemData(self.server_combo.currentIndex())
        if not data:
            self.show_status("삭제할 서버를 목록에서 선택하세요.")
            return
        if not gui_client.themed_question(self, "서버 삭제", f"'{data['name']}' 서버를 목록에서 삭제할까요?"):
            return
        server_registry.remove_server(data["name"])
        self._reload_servers()
        self.show_status(f"'{data['name']}' 서버를 삭제했습니다.")

    def _browse_cert(self):
        path, _ = QFileDialog.getOpenFileName(self, "cert.pem 선택", "", "PEM Files (*.pem);;All Files (*)")
        if path:
            self.cert_input.setText(path)

    def show_status(self, text: str, error: bool = True):
        """상태 문구 표시. error=False면 오류색(빨강) 대신 안내색(회색)으로 보여줌.

        구분이 필요한 이유: IRC 서버가 접속 중에 보내는 안내(예: "hostname을 못 찾아
        IP 주소를 대신 씁니다")나 "연결 중..." 같은 진행 문구까지 빨간 글씨로 나와서
        아무 문제가 없는데도 오류가 난 것처럼 보였음.

        기본값을 True로 둔 이유: 새로 추가되는 호출부가 표시를 빠뜨렸을 때 진짜 오류를
        조용히 감추는 쪽보다, 안내가 좀 눈에 띄는 쪽이 안전하기 때문.
        """
        self.status_label.setText(text)
        name = "status_err" if error else "status_info"
        if self.status_label.objectName() != name:
            self.status_label.setObjectName(name)
            # objectName을 바꾸면 스타일시트를 다시 먹여야 색이 반영됨
            self.status_label.style().unpolish(self.status_label)
            self.status_label.style().polish(self.status_label)

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
            "auto_login": self.auto_login_checkbox.isChecked(),
        }


class ChannelPage(QWidget):
    def __init__(self, on_submit, on_back=None):
        super().__init__()
        self.on_submit = on_submit
        self.on_back = on_back
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        box = QVBoxLayout()
        box.setSpacing(8)
        title = QLabel("채널 입장 / 생성")
        title.setObjectName("title")
        box.addWidget(title)

        self.channel_input = QLineEdit()
        self.channel_input.setPlaceholderText("채널명 (예: #친구들)")
        # 채널명/비번 입력창에서 Enter로 바로 입장 (매번 마우스로 버튼 누르지 않게)
        self.channel_input.returnPressed.connect(lambda: self.on_submit("join"))
        box.addWidget(self.channel_input)

        self.key_input = QLineEdit()
        self.key_input.setPlaceholderText("채널 비밀번호 (선택)")
        self.key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_input.returnPressed.connect(lambda: self.on_submit("join"))
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

        # 로그인 화면으로 되돌아갈 수단이 없으면 계정을 잘못 골랐을 때 앱을 껐다 켜야 함
        self.back_btn = QPushButton("← 로그인 화면으로")
        self.back_btn.setObjectName("secondary")
        self.back_btn.clicked.connect(lambda: self.on_back() if self.on_back else None)
        box.addWidget(self.back_btn)

        container = QFrame()
        container.setObjectName("card")   # 로그인/채널 화면의 카드 - QSS에서 테두리/여백을 줌
        container.setLayout(box)
        container.setFixedWidth(360)
        layout.addWidget(container)
        self.setLayout(layout)

    def set_mode(self, protocol: str):
        self.create_btn.setVisible(protocol != "irc")

    def show_status(self, text: str, error: bool = True):
        """상태 문구 표시. error=False면 오류색(빨강) 대신 안내색(회색)으로 보여줌.

        구분이 필요한 이유: IRC 서버가 접속 중에 보내는 안내(예: "hostname을 못 찾아
        IP 주소를 대신 씁니다")나 "연결 중..." 같은 진행 문구까지 빨간 글씨로 나와서
        아무 문제가 없는데도 오류가 난 것처럼 보였음.

        기본값을 True로 둔 이유: 새로 추가되는 호출부가 표시를 빠뜨렸을 때 진짜 오류를
        조용히 감추는 쪽보다, 안내가 좀 눈에 띄는 쪽이 안전하기 때문.
        """
        self.status_label.setText(text)
        name = "status_err" if error else "status_info"
        if self.status_label.objectName() != name:
            self.status_label.setObjectName(name)
            # objectName을 바꾸면 스타일시트를 다시 먹여야 색이 반영됨
            self.status_label.style().unpolish(self.status_label)
            self.status_label.style().polish(self.status_label)

    def get_values(self):
        return {
            "channel": self.channel_input.text().strip(),
            "key": self.key_input.text(),
        }


class ChatPage(QWidget):
    """여러 채널을 탭으로 동시에 열어둘 수 있음"""

    def __init__(self, on_send, on_add_channel, on_leave_channel, on_set_avatar,
                 on_all_channels_left=None):
        super().__init__()
        self.on_send = on_send
        self.on_add_channel = on_add_channel
        self.on_leave_channel = on_leave_channel
        self.on_set_avatar = on_set_avatar
        # 마지막 채널까지 나가면 채널 선택 화면으로 돌려보내기 위한 콜백
        # (없으면 빈 채팅 화면에 갇혀서 다시 들어갈 방법이 '+' 탭밖에 없음)
        self.on_all_channels_left = on_all_channels_left
        self.my_id = ""
        self._log_views: dict[str, ChannelLogView] = {}
        self._members: dict[str, list[str]] = {}
        self._avatar_pixmaps: dict[str, QPixmap] = {}
        for uid, avatar_b64 in avatar_store.load_avatars().items():
            pixmap = _decode_avatar_pixmap(avatar_b64)
            if pixmap is not None:
                self._avatar_pixmaps[uid] = pixmap
        self._nicknames: dict[str, str] = {}
        self._active_channel = ""
        self._protocol_mode = "custom"
        self._unread_timers: dict[str, QTimer] = {}
        self._unread_blink_on: dict[str, bool] = {}
        self._unread_blink_step: dict[str, int] = {}
        self._mention_notice_timer: QTimer | None = None
        # 코어가 @호출 쿨타임으로 전송을 막으면 입력창 내용을 되살리기 위해 잠깐 보관
        self._pending_input_text = ""

        layout = QHBoxLayout()
        self.channel_sidebar = ChannelSidebar(MEMBER_HEADER_HEIGHT)
        self.channel_sidebar.channel_selected.connect(self._on_sidebar_channel)
        self.channel_sidebar.add_requested.connect(lambda: self.on_add_channel())
        self.channel_sidebar.leave_requested.connect(self._request_close_channel)
        layout.addWidget(self.channel_sidebar)

        center = QVBoxLayout()
        center.setSpacing(0)
        # 세 열(채널 사이드바 / 채팅 / 참여자)의 여백을 0으로 통일해야 세로 시작점이 같아짐.
        # 기본 여백이 붙은 열만 9px쯤 아래에서 시작해 윗선이 어긋났음
        center.setContentsMargins(0, 0, 0, 0)
        # 지금 보고 있는 채널 이름. 오른쪽 "참여자" 헤더와 같은 높이로 두면 채팅 카드와
        # 참여자 카드의 위쪽 선이 같은 높이에서 시작함(채널 목록이 왼쪽으로 옮겨가면서
        # 채팅창 위가 비어 카드 상단이 어긋났었음)
        self.channel_header = QLabel("")
        self.channel_header.setObjectName("channelHeader")
        self.channel_header.setFixedHeight(MEMBER_HEADER_HEIGHT)
        self.channel_header.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        center.addWidget(self.channel_header)

        self._center_stack = QStackedWidget()
        self._empty_label = QLabel("입장한 채널이 없습니다.\n'+ 채널 추가' 버튼으로 입장하세요.")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._center_stack.addWidget(self._empty_label)

        # 채널 목록은 왼쪽 사이드바(_build_channel_sidebar)로 옮겼고, 여기 QTabWidget은
        # 채널별 대화 내용을 겹쳐 담아두는 용도로만 남겨둠(탭 막대는 숨김).
        # 이렇게 두면 채널 추가/제거/전환을 다루는 기존 코드가 그대로 살아있고,
        # 사이드바는 그 위에 얹힌 '보여주는 방식'만 담당하게 됨
        self.tabs = QTabWidget()
        self.tabs.tabBar().hide()
        self.tabs.setDocumentMode(True)
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self._center_stack.addWidget(self.tabs)

        center.addWidget(self._center_stack, 1)

        # @호출이 쿨타임 중일 때만 나(보낸 사람)한테만 잠깐 보이는 안내문 - 채팅창에는 안 남음
        self._mention_notice = QLabel("")
        self._mention_notice.setObjectName("status_err")
        self._mention_notice.setVisible(False)
        center.addWidget(self._mention_notice)

        center.addSpacing(_CARD_TO_CONTROL_GAP)
        self.message_input = MessageInput(self._completion_candidates)
        self.message_input.submitted.connect(self._on_input_submitted)
        self.message_input.emoji_requested.connect(self._open_emoji_picker)
        center.addWidget(self.message_input)
        center_widget = QWidget()
        center_widget.setLayout(center)

        right = QVBoxLayout()
        # 오른쪽 헤더 높이를 고정해야 채팅 카드와 참여자 카드의 위쪽 선이 같은 높이에서
        # 시작함. 안 맞추면 카드 상단이 어긋나 어설퍼 보였음
        right.setSpacing(0)
        right.setContentsMargins(0, 0, 0, 0)
        member_header = QLabel("참여자")
        member_header.setFixedHeight(MEMBER_HEADER_HEIGHT)
        member_header.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        right.addWidget(member_header)
        self.user_list = QListWidget()
        self.user_list.setIconSize(QSize(AVATAR_LIST_PX, AVATAR_LIST_PX))
        right.addWidget(self.user_list)
        # 아래쪽도 왼쪽(채팅 카드 -> 입력창) 간격과 같은 값이어야 버튼 줄이 나란히 놓임
        right.addSpacing(_CARD_TO_CONTROL_GAP)
        self.avatar_btn = QPushButton("프로필 변경")
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

        # 미리보기 이미지를 받아오는 담당자(모든 채널 공유). 서버는 이미지 '주소'만
        # 알려주고 그림 자체는 여기서 직접 받아옴 - gui/link_preview.py 설명 참고
        self._image_fetcher = ImageFetcher(self)

        # 치트 오버레이는 레이아웃에 넣지 않고 채팅 영역 위에 겹쳐 띄움(테두리/배경 없이)
        self._cheat_overlay = CheatOverlay(self._center_stack)
        self._battlecruiser = BattlecruiserOverlay(self._center_stack)
        self._battlecruiser.attach_input(self.message_input.line)

        # 지금 프로토콜이 지원하는 슬래시 명령 목록 - 세션이 알려주면 갱신됨
        self._command_tokens: list[str] = []


    def _open_emoji_picker(self):
        """이모티콘 보관함을 열고, 고른 것을 메시지에 넣음."""
        from gui.emoji_picker import EmojiPicker

        picker = EmojiPicker(self, fetcher=self._image_fetcher)
        picker.emoji_chosen.connect(self._insert_emoji)
        picker.exec()
        self.message_input.focus()

    def _insert_emoji(self, url: str):
        self.message_input.insert_emoji(url)

    def show_resource_cheat(self):
        """'show me the money'가 채널에 떴을 때 - 자원 오버레이를 채팅창 가운데에 잠깐 표시"""
        self._cheat_overlay.start()

    def summon_battlecruiser(self):
        """'배틀크루저 소환' - 채팅창 위에 함선을 띄움(방향키로 조종 가능)"""
        self._battlecruiser.summon()

    def dismiss_battlecruiser(self):
        """'배틀크루저 소환해제' - 순간 가속해서 화면 밖으로 빠져나가며 사라짐"""
        self._battlecruiser.dismiss()

    def set_protocol_mode(self, mode: str):
        self._protocol_mode = mode
        self._avatar_pixmaps.clear()
        self._nicknames.clear()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._push_wrap_width()

    def _push_wrap_width(self):
        """self.tabs는 어떤 채널 탭이 떠 있든 항상 실제로 보이는 위젯이라 폭이 정확함.
        이 값을 모든 채널(비활성 탭 포함)에 미리 알려주면, 탭을 실제로 클릭해서 볼 때
        그제서야 폭을 다시 계산하며 메시지가 눈앞에서 재배치되는 것(스크롤 출렁임의
        원인)을 막을 수 있음."""
        width = self.tabs.width()
        if width <= 0:
            return
        for view in self._log_views.values():
            view.set_container_width(width)

    def _display_name_for(self, user_id: str) -> str:
        return self._nicknames.get(user_id, user_id)

    def _update_input_enabled(self):
        self.message_input.set_enabled(bool(self._active_channel))

    def add_channel(self, channel: str, activate: bool = True):
        if channel not in self._log_views:
            view = ChannelLogView(channel, image_fetcher=self._image_fetcher)
            view.set_container_width(self.tabs.width())
            self._log_views[channel] = view
            self._members[channel] = []
            self.tabs.addTab(view, channel)
            self.channel_sidebar.add_channel(channel)
            self._center_stack.setCurrentWidget(self.tabs)
        if activate:
            self.set_active_channel(channel)

    def open_channels(self) -> list[str]:
        """지금 화면에 열려 있는 채널 목록(탭 순서)"""
        return list(self._log_views.keys())

    def has_channel(self, channel: str) -> bool:
        return channel in self._log_views

    def remove_channel(self, channel: str):
        view = self._log_views.pop(channel, None)
        if view is None:
            return
        self._members.pop(channel, None)
        index = self.tabs.indexOf(view)
        if index >= 0:
            self.tabs.removeTab(index)  # 남은 탭이 있으면 currentChanged가 활성 채널을 갱신함
        self.channel_sidebar.remove_channel(channel)
        view.deleteLater()
        if not self._log_views:
            self._active_channel = ""
            self.channel_header.setText("")
            self._center_stack.setCurrentWidget(self._empty_label)
            self.user_list.clear()
            if self.on_all_channels_left is not None:
                self.on_all_channels_left()
        self._update_input_enabled()

    def reset(self):
        """로그아웃 등으로 세션이 끝났을 때 화면을 깨끗이 비움 - 이전 계정의 대화/참여자가
        다음 로그인 화면에 남아있으면 안 됨"""
        for channel in list(self._log_views.keys()):
            self.remove_channel(channel)
        self._avatar_pixmaps.clear()
        self._nicknames.clear()
        self._members.clear()
        self.my_id = ""
        self.user_list.clear()
        # 떠 있던 오버레이/자동완성 팝업이 로그인 화면 위에 남지 않게 정리
        self._battlecruiser.stop()
        self.message_input._hide_popup()

    def set_active_channel(self, channel: str):
        view = self._log_views.get(channel)
        if view is None:
            return
        index = self.tabs.indexOf(view)
        if index >= 0:
            self.tabs.setCurrentIndex(index)   # currentChanged가 나머지를 맞춰줌

    def active_channel(self) -> str:
        return self._active_channel

    def _on_tab_changed(self, index: int):
        """탭(대화 내용)이 바뀌면 사이드바 선택/헤더/참여자 목록을 따라 맞춤.

        폭은 _push_wrap_width()가 채널 추가/창 리사이즈 때 이미 모든 탭에 미리 반영해두므로
        여기서 다시 계산하지 않음(그게 스크롤이 출렁이던 원인이었다).
        """
        if index < 0:
            return
        view = self.tabs.widget(index)
        if view is None:
            return
        self._active_channel = view.channel_name
        self.channel_header.setText(view.channel_name)
        # 사이드바 선택도 같이 옮김. 여기서 신호가 되돌아오는 걸 막으려고 잠시 끊음
        self.channel_sidebar.list.blockSignals(True)
        self.channel_sidebar.set_active(view.channel_name)
        self.channel_sidebar.list.blockSignals(False)
        self.user_list.clear()
        self._add_userlist_items(self._members.get(self._active_channel, []))
        self._update_input_enabled()
        # 폭은 ChatPage._push_wrap_width()가 채널 추가/창 리사이즈 시점에 이미 모든 탭에
        # (비활성 탭 포함) 미리 반영해두므로, 탭을 볼 때 다시 재계산할 필요가 없음 -
        # 예전에는 여기서 매번 재계산했는데, 그게 메시지들이 눈앞에서 다시 배치되며
        # 스크롤이 출렁이는(위로 튀는) 원인이었음

    def _on_sidebar_channel(self, channel: str):
        """사이드바에서 채널을 고르면 그 채널 대화창을 앞으로 가져옴"""
        view = self._log_views.get(channel)
        if view is None:
            return
        index = self.tabs.indexOf(view)
        if index >= 0 and index != self.tabs.currentIndex():
            self.tabs.setCurrentIndex(index)

    def _request_close_channel(self, channel: str):
        import gui_client  # 지연 import - 이유는 파일 맨 위 docstring 참고
        if gui_client.themed_question(self, "채널 나가기", f"'{channel}' 채널에서 나갈까요?"):
            self.on_leave_channel(channel)

    def _mark_unread(self, channel: str):
        """안 보는 채널에 새 메시지가 왔을 때 - 표시는 사이드바가 담당한다."""
        self.channel_sidebar.mark_unread(channel)

    def _stop_blink(self, channel: str):
        self.channel_sidebar.stop_blink(channel)

    def _submit(self):
        self.message_input.submit()

    def _on_input_submitted(self, text: str):
        """입력줄에서 올라온 글자를 그대로 상위(MainWindow -> ChatSession)로 넘김.

        @호출 쿨타임 판단은 도메인 코어가 한다 - 막히면 MentionBlocked 이벤트가 돌아와
        안내문이 뜨고, 그때 입력을 되살려야 하므로 보낸 글자를 기억해둔다.
        """
        if not self._active_channel:
            return
        self._pending_input_text = text
        self.message_input.clear()
        self.on_send(self._active_channel, text)

    # ==================== 자동완성 (@닉네임 / 슬래시 명령) ====================

    def set_command_specs(self, specs):
        """지금 프로토콜이 지원하는 명령 목록을 코어에서 받아둠 - '/'만 쳐도 이 목록이 뜸.
        IRC와 커스텀 서버가 지원하는 명령이 다르므로 하드코딩하지 않고 세션에서 받아옴."""
        self._command_tokens = [spec.token for spec in specs]

    def _completion_candidates(self, trigger: str) -> list[str]:
        """자동완성 후보. 입력줄은 참여자도 명령도 모르므로 화면이 만들어서 넘겨준다."""
        if trigger == COMMAND_PREFIX:
            return list(self._command_tokens)
        members = self._members.get(self._active_channel, [])
        return ["@" + self._display_name_for(uid) for uid in members if uid != self.my_id]

    def _completion_token(self):
        return self.message_input.completion_token()

    def _update_completer(self, text: str = ""):
        self.message_input._update_completer(text)

    def _insert_completion(self, chosen: str):
        self.message_input._insert_completion(chosen)

    def show_mention_notice(self, text: str):
        """코어가 @호출 쿨타임으로 전송을 막았을 때 - 안내문을 띄우고 입력 내용을 되살림"""
        if self._pending_input_text:
            self.message_input.set_text(self._pending_input_text)
            self._pending_input_text = ""
        self._show_mention_notice(text)

    def _show_mention_notice(self, text: str):
        self._mention_notice.setText(text)
        self._mention_notice.setVisible(True)
        if self._mention_notice_timer is not None:
            self._mention_notice_timer.stop()
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda: self._mention_notice.setVisible(False))
        timer.start(3000)
        self._mention_notice_timer = timer

    def focus_input(self):
        self.message_input.focus()

    def _avatar_for(self, user_id: str, px: int) -> QPixmap:
        cached = self._avatar_pixmaps.get(user_id)
        base = cached if cached is not None else _hashed_avatar_pixmap(user_id)
        return base.scaled(px, px, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.FastTransformation)

    def append_message(self, channel: str, sender: str, text: str, mine: bool, ts: float,
                       is_mention: bool = False, kind: str = "chat", preview: bool = True):
        """is_mention/kind는 도메인 코어가 이미 판단해서 넘겨줌 - 화면은 그리기만 하면 됨.

        preview=False는 지난 기록을 다시 그릴 때 씀(load_history 참고)."""
        view = self._log_views.get(channel)
        if view is None:
            return
        view.append_message(
            self._display_name_for(sender), text, mine, ts,
            self._avatar_for(sender, AVATAR_MSG_PX), kind=kind, preview=preview,
        )
        self._mark_unread(channel)
        if is_mention:
            self._trigger_mention_alert()

    def _trigger_mention_alert(self):
        """지금 그 채널을 보고 있는지와 무관하게 항상 작업표시줄 깜빡임 + 창 흔들림"""
        import gui_client  # 지연 import - 이유는 파일 맨 위 docstring 참고
        top = self.window()
        gui_client._flash_taskbar_icon(top)
        gui_client._shake_window(top)

    def append_system(self, channel: str, text: str):
        view = self._log_views.get(channel)
        if view is None:
            return
        view.append_system(text)

    def load_history(self, channel: str, entries: list[dict]):
        """지난 대화 기록을 다시 그림 - 여기서는 링크 미리보기를 만들지 않는다.

        기록은 채널당 최대 200개라, 그걸 전부 미리보기 대상으로 삼으면 채널에 들어갈
        때마다 수백 건의 요청이 한꺼번에 나가서 입장이 느려지고, 옛날 링크 주인들에게
        들어갈 때마다 접속 사실이 다시 알려진다. 지난 링크는 눌러서 열면 됨."""
        if not entries:
            return
        self.append_system(channel, "── 이전 대화 기록 ──")
        for entry in entries:
            mine = entry.get("from") == self.my_id
            self.append_message(
                channel, entry.get("from", "?"), entry.get("text", ""), mine,
                entry.get("ts", 0), preview=False,
            )
        self.append_system(channel, "── 여기까지 이전 기록 ──")

    def _add_userlist_items(self, users: list[str]):
        for uid in users:
            display = self._display_name_for(uid)
            item = QListWidgetItem(display)
            if display != uid:
                item.setToolTip(uid)  # 닉네임은 고유성이 보장되지 않으므로 원래 아이디를 툴팁으로 확인 가능하게
            item.setIcon(QIcon(self._avatar_for(uid, AVATAR_LIST_PX)))
            self.user_list.addItem(item)

    def update_userlist(self, channel: str, users: list[str]):
        self._members[channel] = users
        if channel == self._active_channel:
            self.user_list.clear()
            self._add_userlist_items(users)

    def set_avatar(self, user_id: str, avatar_b64: str | None):
        if not avatar_b64:
            self._avatar_pixmaps.pop(user_id, None)
        else:
            pixmap = _decode_avatar_pixmap(avatar_b64)
            if pixmap is not None:
                self._avatar_pixmaps[user_id] = pixmap
                # 실제 IRC 서버는 아이콘을 서버가 저장해주지 않으므로, 로컬에도 남겨둬서
                # 다음에 앱을 다시 켰을 때 상대가 다시 보내주기 전까지도 곧바로 보이게 함
                avatar_store.save_avatar(user_id, avatar_b64)
        if self._active_channel:
            self.user_list.clear()
            self._add_userlist_items(self._members.get(self._active_channel, []))

    def set_nickname(self, user_id: str, nickname: str | None):
        if not nickname:
            self._nicknames.pop(user_id, None)
        else:
            self._nicknames[user_id] = nickname
        if self._active_channel:
            self.user_list.clear()
            self._add_userlist_items(self._members.get(self._active_channel, []))

