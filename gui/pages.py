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
    QListWidget, QListWidgetItem, QPushButton, QScrollArea, QStackedWidget, QTabBar,
    QTabWidget, QVBoxLayout, QWidget,
)

import avatar_store
import login_prefs
import server_registry
from chat_core.commands import COMMAND_PREFIX, KIND_ACTION, KIND_NOTICE
from gui.helpers import (
    _build_unread_dot_icon, _decode_avatar_pixmap, _find_default_cert, _hashed_avatar_pixmap,
)
from gui.theme import (
    ADD_TAB_LABEL, APP_TITLE, AVATAR_LIST_PX, AVATAR_MSG_PX, CHANNEL_TAB_HEIGHT,
    DEFAULT_PLAIN_PORT, DEFAULT_SSL_PORT, UNREAD_BLINK_COLOR, UNREAD_BLINK_COUNT,
    UNREAD_BLINK_INTERVAL_MS,
)

# 카드(채팅/참여자) 아래와 그 밑 컨트롤(입력창/프로필 버튼) 사이 간격.
# 좌우 열이 같은 값을 써야 아래쪽 버튼 줄이 나란히 놓임
_CARD_TO_CONTROL_GAP = 6
from version import APP_VERSION
from gui.cheat_overlay import CheatOverlay
from gui.battlecruiser import BattlecruiserOverlay
from gui.link_preview import ImageFetcher
from gui.widgets import ChannelLogView, _ChannelTabBar


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

    def show_status(self, text: str):
        self.status_label.setText(text)

    def get_values(self):
        return {
            "channel": self.channel_input.text().strip(),
            "key": self.key_input.text(),
        }


class ChatPage(QWidget):
    """여러 채널을 탭으로 동시에 열어둘 수 있음"""

    def __init__(self, on_send, on_add_channel, on_leave_channel, on_set_avatar,
                 on_all_channels_left=None, on_request_unfurl=None):
        super().__init__()
        self.on_send = on_send
        # 링크 미리보기 정보를 서버에 요청하는 콜백(MainWindow -> ChatSession).
        # 안 주면 미리보기를 아예 시도하지 않음 - 테스트/오프라인에서 안전
        self.on_request_unfurl = on_request_unfurl
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

        center = QVBoxLayout()
        self._center_stack = QStackedWidget()
        self._empty_label = QLabel("입장한 채널이 없습니다.\n'+ 채널 추가' 버튼으로 입장하세요.")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._center_stack.addWidget(self._empty_label)

        self.tabs = QTabWidget()
        self.tabs.setTabBar(_ChannelTabBar())
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self.tabs.tabBarClicked.connect(self._on_tab_bar_clicked)
        # '+' 채널 추가 버튼을 코너에 따로 두는 대신, 항상 맨 오른쪽에 붙어있는 '+' 탭
        # 자체로 구현 - 마지막 채널 탭 바로 뒤에 절반 크기로 붙어서 자연스럽게 이어짐.
        # 처음에는 setTabEnabled(False)로 막아뒀었는데, disabled 탭은 Qt에서 마우스
        # 이벤트 자체를 안 받아서(진짜 클릭으로 검증하고서야 발견함 - 핸들러를 직접
        # 호출하는 테스트로는 이 문제가 안 잡혔음) 실제로는 눌러도 아무 반응이 없었음.
        # 그래서 그냥 enabled로 두고, 클릭으로 "선택"되는 순간 곧바로 원래 활성 채널로
        # 되돌리는 방식으로 바꿈 - 같은 이벤트 처리 안에서 되돌아가므로 화면 깜빡임 없음
        self._add_tab_placeholder = QWidget()
        self.tabs.addTab(self._add_tab_placeholder, ADD_TAB_LABEL)
        self.tabs.setTabToolTip(0, "새 채널에 입장합니다")
        self._center_stack.addWidget(self.tabs)

        center.addWidget(self._center_stack)

        # @호출이 쿨타임 중일 때만 나(보낸 사람)한테만 잠깐 보이는 안내문 - 채팅창에는 안 남음
        self._mention_notice = QLabel("")
        self._mention_notice.setObjectName("status_err")
        self._mention_notice.setVisible(False)
        center.addWidget(self._mention_notice)

        input_row = QHBoxLayout()
        self.msg_input = QLineEdit()
        self.msg_input.setPlaceholderText("메시지 입력 후 Enter (@닉네임으로 호출 가능)")
        self.msg_input.returnPressed.connect(self._submit)
        send_btn = QPushButton("전송")
        send_btn.clicked.connect(self._submit)
        input_row.addWidget(self.msg_input)
        input_row.addWidget(send_btn)
        center.addLayout(input_row)
        center_widget = QWidget()
        center_widget.setLayout(center)

        right = QVBoxLayout()
        # 오른쪽 헤더를 왼쪽 탭 줄과 같은 높이로 고정해야 두 카드(채팅/참여자)의 위쪽 선이
        # 같은 높이에서 시작함. 안 맞추면 카드 상단이 14px쯤 어긋나 어설퍼 보였음
        right.setSpacing(0)
        member_header = QLabel("참여자")
        member_header.setFixedHeight(CHANNEL_TAB_HEIGHT)
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
        self._battlecruiser.attach_input(self.msg_input)

        # @닉네임 / 슬래시 명령 자동완성 - Qt 내장 QCompleter가 접두사 필터링까지 다 해줌
        # (별도 라이브러리 불필요). 한글도 일반 접두사 매칭은 그대로 동작함("몽"->"몽키").
        # 못 하는 건 초성 검색("ㅁ"->"몽키")뿐인데, 그건 자모 분해가 필요한 별개 기능이라
        # 여기서는 다루지 않음.
        #
        # QCompleter는 원래 "위젯 전체 텍스트"를 접두사로 보기 때문에 문장 중간의 @토큰에는
        # 그대로 쓸 수 없음. 그래서 setCompletionPrefix()로 지금 입력 중인 토큰만 직접
        # 넘겨주고 complete()로 팝업을 띄우는 방식으로 씀.
        self._completion_model = QStringListModel([], self)
        self._completer = QCompleter(self._completion_model, self)
        self._completer.setWidget(self.msg_input)
        self._completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self._completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._completer.setFilterMode(Qt.MatchFlag.MatchStartsWith)
        self._completer.activated.connect(self._insert_completion)
        self.msg_input.textEdited.connect(self._update_completer)
        # 지금 완성 중인 토큰의 시작 위치(트리거 문자 포함). -1이면 완성 중이 아님
        self._completion_start = -1
        # 지금 프로토콜이 지원하는 슬래시 명령 목록 - 세션이 알려주면 갱신됨
        self._command_tokens: list[str] = []

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
        self.msg_input.setEnabled(bool(self._active_channel))

    def _make_close_button(self, channel: str) -> QPushButton:
        """빨간 X 대신 테마에 맞는 수수한 × 기호 - 기본 탭 닫기 아이콘 대신 직접 그림.

        평소엔 흐릿하게 두고 마우스를 올렸을 때만 또렷해지게 함 - 탭마다 ×가 진하게 박혀
        있으면 채널 이름보다 버튼이 먼저 눈에 들어와 어수선해 보임."""
        btn = QPushButton("×")
        btn.setFlat(True)
        btn.setFixedSize(18, 18)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(
            "QPushButton { background: transparent; color: #6e7185; border: none;"
            " border-radius: 9px; font-size: 14px; font-weight: bold; padding: 0px; }"
            "QPushButton:hover { background: #565a72; color: #ffffff; }"
        )
        btn.setToolTip(f"'{channel}' 채널 나가기")
        btn.clicked.connect(lambda: self._request_close_channel(channel))
        return btn

    def add_channel(self, channel: str, activate: bool = True):
        if channel not in self._log_views:
            view = ChannelLogView(channel, image_fetcher=self._image_fetcher)
            view.set_container_width(self.tabs.width())
            self._log_views[channel] = view
            self._members[channel] = []
            insert_at = self.tabs.count() - 1  # 맨 끝의 '+' 탭 바로 앞에 끼워넣음
            index = self.tabs.insertTab(insert_at, view, channel)
            self.tabs.tabBar().setTabButton(
                index, QTabBar.ButtonPosition.RightSide, self._make_close_button(channel)
            )
            # 탭 폭이 고정이라 긴 이름은 말줄임(...)으로 잘리므로, 전체 이름은 툴팁으로 보여줌
            self.tabs.setTabToolTip(index, channel)
            self._center_stack.setCurrentWidget(self.tabs)
        if activate:
            self.set_active_channel(channel)

    def _on_tab_bar_clicked(self, index: int):
        if self.tabs.widget(index) is self._add_tab_placeholder:
            self.on_add_channel()
            # tabBarClicked 신호는 Qt 내부의 QTabBar::mouseReleaseEvent가 끝나기 "전에"
            # 방출되는데, 그 신호 처리 직후 Qt가 자체적으로 한 번 더 setCurrentIndex를
            # 호출해서 우리가 여기서 바로 되돌려도 곧바로 다시 덮어써버림(실측으로 확인함
            # - 되돌린 직후엔 값이 맞다가 mouseClick이 완전히 리턴된 뒤엔 다시 '+' 탭으로
            # 돌아가 있었음). 다음 이벤트 루프 틱으로 미뤄서 Qt의 내부 처리가 완전히
            # 끝난 뒤에 되돌리면 확실히 반영됨
            QTimer.singleShot(0, self._restore_active_tab)

    def _restore_active_tab(self):
        """'+' 탭이 클릭되면서 currentChanged로 잠깐 선택된 상태를 원래 활성 채널로
        되돌려서 버튼처럼 동작하게 함. 아직 입장한 채널이 하나도 없으면(활성 채널 없음)
        되돌릴 곳이 없으니 그냥 '+' 탭에 그대로 둠"""
        view = self._log_views.get(self._active_channel)
        if view is None:
            return
        index = self.tabs.indexOf(view)
        if index >= 0:
            self.tabs.setCurrentIndex(index)

    def remove_channel(self, channel: str):
        view = self._log_views.pop(channel, None)
        if view is None:
            return
        self._stop_blink(channel)
        self._members.pop(channel, None)
        index = self.tabs.indexOf(view)
        if index >= 0:
            self.tabs.removeTab(index)  # 남은 탭이 있으면 currentChanged가 자동으로 활성 채널을 갱신함
        view.deleteLater()
        if not self._log_views:
            self._active_channel = ""
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
        self._completer.popup().hide()
        self._completion_start = -1

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
        if view is None or view is self._add_tab_placeholder:
            return
        self._active_channel = view.channel_name
        self._stop_blink(view.channel_name)
        self.user_list.clear()
        self._add_userlist_items(self._members.get(self._active_channel, []))
        self._update_input_enabled()
        # 폭은 ChatPage._push_wrap_width()가 채널 추가/창 리사이즈 시점에 이미 모든 탭에
        # (비활성 탭 포함) 미리 반영해두므로, 탭을 볼 때 다시 재계산할 필요가 없음 -
        # 예전에는 여기서 매번 재계산했는데, 그게 메시지들이 눈앞에서 다시 배치되며
        # 스크롤이 출렁이는(위로 튀는) 원인이었음

    def _request_close_channel(self, channel: str):
        import gui_client  # 지연 import - 이유는 파일 맨 위 docstring 참고
        if gui_client.themed_question(self, "채널 나가기", f"'{channel}' 채널에서 나갈까요?"):
            self.on_leave_channel(channel)

    def _mark_unread(self, channel: str):
        """탭에 작은 점 아이콘이 UNREAD_BLINK_COUNT번 깜빡인 뒤, 탭을 보기 전까지는
        점을 그대로 유지함 (글자색 깜빡임은 QTabBar::tab { color: ... } 스타일시트가
        항상 우선 적용돼서 안 먹혔음 - 아이콘은 스타일시트 영향을 안 받아 확실히 보임)"""
        if channel == self._active_channel:
            return
        view = self._log_views.get(channel)
        if view is None:
            return
        if self.tabs.indexOf(view) < 0:
            return
        if channel in self._unread_timers:
            return  # 이미 깜빡이는 중
        timer = QTimer(self)
        timer.timeout.connect(lambda ch=channel: self._toggle_blink(ch))
        self._unread_timers[channel] = timer
        self._unread_blink_on[channel] = False
        self._unread_blink_step[channel] = 0
        timer.start(UNREAD_BLINK_INTERVAL_MS)
        self._toggle_blink(channel)  # 바로 한 번 켜서 즉각 반응하는 느낌을 줌

    def _toggle_blink(self, channel: str):
        view = self._log_views.get(channel)
        index = self.tabs.indexOf(view) if view is not None else -1
        if view is None or index < 0 or channel == self._active_channel:
            self._stop_blink(channel)
            return
        step = self._unread_blink_step.get(channel, 0) + 1
        self._unread_blink_step[channel] = step
        on = not self._unread_blink_on.get(channel, False)
        self._unread_blink_on[channel] = on
        icon = _build_unread_dot_icon(UNREAD_BLINK_COLOR) if on else QIcon()
        self.tabs.tabBar().setTabIcon(index, icon)
        if on and step >= 2 * UNREAD_BLINK_COUNT - 1:
            # 지정된 횟수만큼 깜빡였으니 타이머만 멈추고 밝은 색은 그대로 유지
            # (실제로 탭을 봐야만 _stop_blink에서 기본 색으로 되돌아감)
            timer = self._unread_timers.pop(channel, None)
            if timer is not None:
                timer.stop()
                timer.deleteLater()

    def _stop_blink(self, channel: str):
        timer = self._unread_timers.pop(channel, None)
        if timer is not None:
            timer.stop()
            timer.deleteLater()
        self._unread_blink_on.pop(channel, None)
        self._unread_blink_step.pop(channel, None)
        view = self._log_views.get(channel)
        if view is not None:
            index = self.tabs.indexOf(view)
            if index >= 0:
                self.tabs.tabBar().setTabIcon(index, QIcon())

    def _submit(self):
        """입력창 내용을 그대로 상위(MainWindow -> ChatSession)로 넘김.

        @호출 쿨타임 판단은 이제 도메인 코어가 함 - 막히면 MentionBlocked 이벤트가 돌아와
        show_mention_notice()로 안내문이 뜨고, 그때는 입력창을 비우지 않아야 하므로
        여기서는 코어가 실제로 전송했는지를 알 수 없다는 점에 유의(전송 여부와 무관하게
        비우면 막힌 메시지가 사라짐). 그래서 코어가 막았을 때만 입력을 되살리는 대신,
        전송 시도 전 텍스트를 기억해뒀다가 안내문이 뜨면 그대로 복원함."""
        # 자동완성 팝업이 떠 있을 때의 Enter는 "후보 선택"이지 "전송"이 아님.
        # 이 가드가 없으면 Enter 한 번에 후보 선택과 전송이 같이 일어나서, 완성되기 전
        # 상태의 텍스트("@Mo")가 그대로 전송됨(실제 키 이벤트 테스트로 발견한 버그)
        if self._completer.popup().isVisible():
            return
        text = self.msg_input.text().strip()
        if not text or not self._active_channel:
            return
        self._pending_input_text = text
        self.msg_input.clear()
        self.on_send(self._active_channel, text)

    # ==================== 자동완성 (@닉네임 / 슬래시 명령) ====================

    def set_command_specs(self, specs):
        """지금 프로토콜이 지원하는 명령 목록을 코어에서 받아둠 - '/'만 쳐도 이 목록이 뜸.
        IRC와 커스텀 서버가 지원하는 명령이 다르므로 하드코딩하지 않고 세션에서 받아옴."""
        self._command_tokens = [spec.token for spec in specs]

    def _completion_candidates(self, trigger: str) -> list[str]:
        if trigger == COMMAND_PREFIX:
            return list(self._command_tokens)
        members = self._members.get(self._active_channel, [])
        # 나 자신은 호출할 일이 없으니 목록에서 뺌
        return ["@" + self._display_name_for(uid) for uid in members if uid != self.my_id]

    def _completion_token(self) -> tuple[int, str] | None:
        """커서 바로 앞에서 입력 중인 토큰이 자동완성 대상이면 (시작위치, 토큰).

        - '@'는 문장 어디서든 트리거(앞이 공백이거나 맨 앞일 때만 - 이메일 주소 오인 방지)
        - '/'는 맨 앞에서만 트리거(명령은 줄 맨 앞에만 올 수 있음)
        - 토큰 안에 공백이 들어가면 더 이상 완성 대상이 아님
        """
        text = self.msg_input.text()
        cursor = self.msg_input.cursorPosition()
        head = text[:cursor]
        for trigger in ("@", COMMAND_PREFIX):
            start = head.rfind(trigger)
            if start < 0:
                continue
            token = head[start:]
            if " " in token:
                continue
            if trigger == COMMAND_PREFIX and start != 0:
                continue
            if trigger == "@" and start > 0 and not head[start - 1].isspace():
                continue
            return start, token
        return None

    def _update_completer(self, _text: str = ""):
        found = self._completion_token()
        if found is None:
            self._completion_start = -1
            self._completer.popup().hide()
            return
        start, token = found
        candidates = self._completion_candidates(token[0])
        if not candidates:
            self._completion_start = -1
            self._completer.popup().hide()
            return
        self._completion_start = start
        # 후보 목록 자체를 매번 새로 세팅해야 참여자가 들어오고 나간 게 바로 반영됨
        self._completion_model.setStringList(candidates)
        self._completer.setCompletionPrefix(token)
        if self._completer.completionCount() == 0:
            self._completer.popup().hide()
            return
        popup = self._completer.popup()
        popup.setCurrentIndex(self._completer.completionModel().index(0, 0))
        self._completer.complete()

    def _insert_completion(self, chosen: str):
        """팝업에서 고른 항목으로 입력 중이던 토큰을 교체하고 뒤에 공백 하나를 붙임"""
        if self._completion_start < 0:
            return
        text = self.msg_input.text()
        cursor = self.msg_input.cursorPosition()
        new_text = text[:self._completion_start] + chosen + " " + text[cursor:]
        self.msg_input.setText(new_text)
        self.msg_input.setCursorPosition(self._completion_start + len(chosen) + 1)
        self._completion_start = -1

    def show_mention_notice(self, text: str):
        """코어가 @호출 쿨타임으로 전송을 막았을 때 - 안내문을 띄우고 입력 내용을 되살림"""
        if self._pending_input_text:
            self.msg_input.setText(self._pending_input_text)
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
        self.msg_input.setFocus()

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
        widget = view.append_message(
            self._display_name_for(sender), text, mine, ts,
            self._avatar_for(sender, AVATAR_MSG_PX), kind=kind,
            preview=preview and self.on_request_unfurl is not None,
        )
        # 링크가 있으면 서버에 "이 주소 정보 좀 가져다줘"라고 요청해둠. 결과는 나중에
        # apply_unfurl()로 돌아와 카드가 채워짐(안 오면 하이퍼링크만 남음)
        if widget is not None and widget.preview_urls and self.on_request_unfurl is not None:
            for url in widget.preview_urls:
                self.on_request_unfurl(url)
        self._mark_unread(channel)
        if is_mention:
            self._trigger_mention_alert()

    def apply_unfurl(self, url: str, title: str, description: str = "", image_url: str = ""):
        """서버가 보내준 링크 메타데이터를 그 링크를 기다리던 메시지에 반영.

        image_url은 '주소'일 뿐이고, 그림은 카드가 만들어진 뒤 여기서 직접 받아옴.

        어느 채널의 메시지였는지는 서버 응답에 없으므로 모든 채널을 훑음 - 같은 링크가
        여러 채널에 붙어 있을 수도 있고, 어차피 채널 수가 많지 않아 부담이 없음."""
        for view in self._log_views.values():
            view.apply_unfurl(url, title, description, image_url)

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
