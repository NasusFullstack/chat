"""로그인/채널입장/채팅 화면 (LoginPage, ChannelPage, ChatPage).

이 모듈은 themed_get_text/themed_question(gui.themed_dialogs)와 _flash_taskbar_icon/
_shake_window(gui.mention_alerts)를 호출하는데, 이 4개는 테스트가 g.themed_question =
fake처럼 gui_client 모듈에 직접 몽키패치하는 대상임. 그래서 `from gui.themed_dialogs
import themed_question`처럼 바로 바인딩하지 않고, `import gui_client` 후 호출 시점에
`gui_client.themed_question(...)`으로 모듈 속성을 조회함 - 이러면 gui_client.py가 아직
이 모듈을 import하는 도중이라도(순환참조처럼 보이지만) 문제없이 동작함. 자세한 이유는
gui_client.py 상단 주석 참고.
"""
import time

from PySide6.QtCore import Qt, QSize, QTimer
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QPushButton, QStackedWidget, QTabBar, QTabWidget,
    QVBoxLayout, QWidget,
)

import gui_client
import avatar_store
import login_prefs
import server_registry
from gui.helpers import (
    _MENTION_TOKEN_RE, _build_unread_dot_icon, _decode_avatar_pixmap, _find_default_cert,
    _hashed_avatar_pixmap,
)
from gui.theme import (
    ADD_TAB_LABEL, AVATAR_LIST_PX, AVATAR_MSG_PX, DEFAULT_PLAIN_PORT, DEFAULT_SSL_PORT,
    MENTION_COOLDOWN_SEC, UNREAD_BLINK_COLOR, UNREAD_BLINK_COUNT, UNREAD_BLINK_INTERVAL_MS,
)
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
        container.setLayout(box)
        container.setFixedWidth(360)
        layout.addWidget(container)
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
        # (채널, 호출 대상 user_id) -> 마지막으로 그 사람을 @호출해서 실제로 전송한 시각.
        # 내가 같은 사람을 다시 호출할 때만 쿨타임이 적용되고, 다른 사람을 부르는 건 무관함
        self._mention_cooldowns: dict[tuple[str, str], float] = {}
        self._mention_notice_timer: QTimer | None = None

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
        right.addWidget(QLabel("참여자"))
        self.user_list = QListWidget()
        self.user_list.setIconSize(QSize(AVATAR_LIST_PX, AVATAR_LIST_PX))
        right.addWidget(self.user_list)
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
        """빨간 X 대신 테마에 맞는 수수한 × 기호 - 기본 탭 닫기 아이콘 대신 직접 그림"""
        btn = QPushButton("×")
        btn.setFlat(True)
        btn.setFixedSize(16, 16)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(
            "QPushButton { background: transparent; color: #9a9cad; border: none;"
            " font-weight: bold; padding: 0px; }"
            "QPushButton:hover { color: #ffffff; }"
        )
        btn.setToolTip(f"'{channel}' 채널 나가기")
        btn.clicked.connect(lambda: self._request_close_channel(channel))
        return btn

    def add_channel(self, channel: str, activate: bool = True):
        if channel not in self._log_views:
            view = ChannelLogView(channel)
            view.set_container_width(self.tabs.width())
            self._log_views[channel] = view
            self._members[channel] = []
            insert_at = self.tabs.count() - 1  # 맨 끝의 '+' 탭 바로 앞에 끼워넣음
            index = self.tabs.insertTab(insert_at, view, channel)
            self.tabs.tabBar().setTabButton(
                index, QTabBar.ButtonPosition.RightSide, self._make_close_button(channel)
            )
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
        text = self.msg_input.text().strip()
        if not text or not self._active_channel:
            return
        channel = self._active_channel
        blocked_target, remaining = self._check_mention_cooldown(channel, text)
        if blocked_target is not None:
            # 쿨타임 중이면 메시지 자체를 아예 보내지 않음(채팅창에 안 남음) -
            # 입력한 내용은 그대로 두고, 보낸 사람한테만 잠깐 안내문을 보여줌
            self._show_mention_notice(f"@{blocked_target} 호출은 {remaining}초 후에 다시 가능합니다.")
            return
        self._record_mention_cooldowns(channel, text)
        self.on_send(channel, text)
        self.msg_input.clear()

    def _mentioned_targets(self, channel: str, text: str) -> list[str]:
        """text에 있는 @토큰들을 그 채널의 실제 참여자(닉네임 또는 아이디)로 해석"""
        tokens = _MENTION_TOKEN_RE.findall(text)
        if not tokens:
            return []
        members = self._members.get(channel, [])
        by_display = {self._display_name_for(uid): uid for uid in members}
        by_id = {uid: uid for uid in members}
        resolved = []
        for token in tokens:
            target = by_display.get(token) or by_id.get(token)
            if target and target not in resolved:
                resolved.append(target)
        return resolved

    def _check_mention_cooldown(self, channel: str, text: str) -> tuple[str | None, int]:
        now = time.time()
        for target in self._mentioned_targets(channel, text):
            last = self._mention_cooldowns.get((channel, target))
            if last is not None and now - last < MENTION_COOLDOWN_SEC:
                remaining = int(MENTION_COOLDOWN_SEC - (now - last)) + 1
                return self._display_name_for(target), remaining
        return None, 0

    def _record_mention_cooldowns(self, channel: str, text: str):
        now = time.time()
        for target in self._mentioned_targets(channel, text):
            self._mention_cooldowns[(channel, target)] = now

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

    def append_message(self, channel: str, sender: str, text: str, mine: bool, ts: float):
        view = self._log_views.get(channel)
        if view is None:
            return
        view.append_message(self._display_name_for(sender), text, mine, ts, self._avatar_for(sender, AVATAR_MSG_PX))
        self._mark_unread(channel)
        if not mine and self._is_mentioned(text):
            self._trigger_mention_alert()

    def _is_mentioned(self, text: str) -> bool:
        if not self.my_id:
            return False
        my_names = {self.my_id, self._display_name_for(self.my_id)}
        return any(token in my_names for token in _MENTION_TOKEN_RE.findall(text))

    def _trigger_mention_alert(self):
        """지금 그 채널을 보고 있는지와 무관하게 항상 작업표시줄 깜빡임 + 창 흔들림"""
        top = self.window()
        gui_client._flash_taskbar_icon(top)
        gui_client._shake_window(top)

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
