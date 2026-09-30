"""채팅 화면 - 부품들을 조립하고 서로 연결하는 곳.

화면 자체는 무엇을 그릴지 거의 모른다. 실제 그리기는 부품들이 한다:
- 왼쪽  gui/components/channel_sidebar.py  채널 목록/추가/나가기/안읽음
- 가운데 gui/components/message_log.py      채널별 대화 목록
- 아래  gui/components/message_input.py    입력창/이모티콘/자동완성
- 오른쪽 gui/components/member_panel.py     참여자 목록/아이콘/닉네임

여기 남는 일은 "어느 부품이 어느 부품에게 무엇을 알려줄지" 뿐이다.

주의: 이 모듈은 themed_get_text/themed_question/themed_warning/_flash_taskbar_icon/
_shake_window를 호출하는데, 이 5개는 테스트가 gui_client 모듈에 직접 몽키패치하는 대상이다.
그래서 모듈 맨 위에서 바인딩하지 않고 호출하는 메서드 "본문 안에서" `import gui_client`를 한 뒤
`gui_client.xxx(...)`로 조회한다. 맨 위에 두면 PyInstaller 빌드에서 순환참조로 크래시가 난다
(자세한 이유는 gui_client.py 상단 주석 참고).
"""
import time

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QPushButton, QStackedWidget,
                               QTabWidget, QVBoxLayout, QWidget)

import app_prefs
from chat_core.commands import COMMAND_PREFIX
from gui.battlecruiser import BattlecruiserOverlay
from gui.cheat_overlay import CheatOverlay
from gui.components.app_footer import AppFooter
from gui.components.channel_sidebar import ChannelSidebar
from gui.components.member_panel import MemberPanel
from gui.components.message_input import MessageInput
from gui.components.upload_bar import UploadBar
from gui.components.message_log import ChannelLogView
from gui.components.gear_button import GearButton
from gui.components.sidebar_handle import SidebarHandle
from gui.link_preview import ImageFetcher
from gui.theme import (AVATAR_MSG_PX, CHANNEL_SIDEBAR_WIDTH, GEAR_BTN_PX,
                       SIDEBAR_HANDLE_WIDTH)

# 참여자 헤더 높이 - 채팅 카드 상단과 참여자 카드 상단을 같은 높이에 두기 위한 값
MEMBER_HEADER_HEIGHT = 34
# 참여자 열 폭 - 왼쪽 채널 사이드바와 같은 폭으로 맞춤(양쪽이 대칭이라 눈에 안정적이고,
# 아래로 옮겨온 만든이 표시도 예전 사이드바에 있을 때와 같은 폭을 그대로 쓴다)
MEMBER_COLUMN_WIDTH = CHANNEL_SIDEBAR_WIDTH

# 카드(채팅/참여자) 아래와 그 밑 컨트롤(입력창/프로필 버튼) 사이 간격.
# 좌우 열이 같은 값을 써야 아래쪽 버튼 줄이 나란히 놓임
_CARD_TO_CONTROL_GAP = 6


class ChatPage(QWidget):
    """여러 채널을 탭으로 동시에 열어둘 수 있음"""
    # 환경설정 톱니가 눌렸다(창을 여는 일은 바깥이 한다)
    settings_requested = Signal()

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
        self._active_channel = ""
        self._protocol_mode = "custom"
        self._unread_blink_on: dict[str, bool] = {}
        self._unread_blink_step: dict[str, int] = {}
        self._mention_notice_timer: QTimer | None = None
        # 코어가 @호출 쿨타임으로 전송을 막으면 입력창 내용을 되살리기 위해 잠깐 보관
        self._pending_input_text = ""
        # 지금 떠 있는 이모티콘 보관함(모달이 아니라 하나만 띄우고 참조를 들고 있음)
        self._emoji_picker = None

        layout = QHBoxLayout()
        self.channel_sidebar = ChannelSidebar(MEMBER_HEADER_HEIGHT)
        self.channel_sidebar.channel_selected.connect(self._on_sidebar_channel)
        self.channel_sidebar.add_requested.connect(lambda: self.on_add_channel())
        self.channel_sidebar.leave_requested.connect(self._request_close_channel)
        # 접어둔 채로 껐으면 다음에도 접힌 채로 연다(매번 다시 접게 하면 성가심)
        self.channel_sidebar.set_collapsed(app_prefs.get("channel_sidebar_collapsed"))
        self.channel_sidebar.collapsed_changed.connect(
            lambda on: app_prefs.set_value("channel_sidebar_collapsed", on))
        layout.addWidget(self.channel_sidebar)

        # 여닫기 손잡이는 사이드바와 대화창 '사이'에, 세로 가운데에 놓는다.
        # 사이드바 안에 두면 접었을 때(폭 0) 같이 사라져 다시 펼 방법이 없어진다
        handle_column = QVBoxLayout()
        handle_column.setContentsMargins(0, 0, 0, 0)
        # 간격을 0으로 둬야 위아래 균형 계산이 정확해진다(기본 간격이 끼면
        # 손잡이가 그만큼 위로 밀린다 - 실측 3px)
        handle_column.setSpacing(0)
        handle_column.addStretch(1)
        self.sidebar_handle = SidebarHandle()
        self.sidebar_handle.set_collapsed(self.channel_sidebar.is_collapsed())
        self.sidebar_handle.toggled.connect(self._toggle_sidebar)
        self.channel_sidebar.collapsed_changed.connect(self.sidebar_handle.set_collapsed)
        handle_column.addWidget(self.sidebar_handle, 0, Qt.AlignmentFlag.AlignHCenter)
        handle_column.addStretch(1)
        # 환경설정 톱니는 채널 목록 **밖**에 둔다. 목록 안에 두면 접었을 때 같이 사라져서
        # (접힌 폭이 0이다) 설정으로 가는 길이 트레이 메뉴 하나만 남는다
        self.gear_btn = GearButton()
        self.gear_btn.clicked.connect(self.settings_requested.emit)
        self._handle_column = handle_column
        self._gear_balance = None      # 손잡이 균형용 위쪽 여백
        handle_column.addWidget(self.gear_btn, 0, Qt.AlignmentFlag.AlignHCenter)
        self._place_gear(self.channel_sidebar.is_collapsed())
        self.channel_sidebar.collapsed_changed.connect(self._place_gear)
        handle_host = QWidget()
        handle_host.setLayout(handle_column)
        # 손잡이와 환경설정 톱니가 함께 들어가는 열 - 둘 중 넓은 것에 맞춘다
        # (톱니가 열보다 넓으면 가장자리가 잘려 보인다)
        handle_host.setFixedWidth(max(SIDEBAR_HANDLE_WIDTH + 6,
                                      self.gear_btn.width() + 4))
        layout.addWidget(handle_host)

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
        self.message_input.photo_requested.connect(lambda: self._upload("photo"))
        self.message_input.file_requested.connect(lambda: self._upload("file"))
        self.message_input.clicked.connect(self._close_emoji_picker)
        # 올리는 중일 때만 나타나는 줄. 입력줄 바로 위라 눈에 띄면서 자리를 안 뺏는다
        self.upload_bar = UploadBar()
        self.upload_bar.cancelled.connect(self._cancel_upload)
        center.addWidget(self.upload_bar)
        center.addWidget(self.message_input)
        center_widget = QWidget()
        center_widget.setLayout(center)

        right = QVBoxLayout()
        # 오른쪽 헤더 높이를 고정해야 채팅 카드와 참여자 카드의 위쪽 선이 같은 높이에서
        # 시작함. 안 맞추면 카드 상단이 어긋나 어설퍼 보였음
        right.setSpacing(0)
        right.setContentsMargins(0, 0, 0, 0)
        # 로고를 인터넷에서 받아와야 하므로 받아오기 담당자를 같이 넘긴다
        self._image_fetcher = ImageFetcher(self)
        self.member_panel = MemberPanel(MEMBER_HEADER_HEIGHT, fetcher=self._image_fetcher)
        right.addWidget(self.member_panel, 0)
        # 프로필 변경은 참여자 목록에 바로 붙는다(내 아이콘도 저 목록에 보이므로 같은 덩어리)
        right.addSpacing(_CARD_TO_CONTROL_GAP)
        self.avatar_btn = QPushButton("프로필 변경")
        self.avatar_btn.setObjectName("secondary")
        self.avatar_btn.clicked.connect(lambda: self.on_set_avatar())
        right.addWidget(self.avatar_btn)
        # 만든이 표시는 맨 아래에 가라앉힌다. 채널 사이드바에 있었지만 그쪽은 접을 수 있게
        # 되면서 접으면 통째로 사라져버려서, 항상 보이는 이쪽 열로 옮겼다
        right.addStretch(1)
        self.footer = AppFooter()
        right.addWidget(self.footer, 0)
        right_widget = QWidget()
        right_widget.setLayout(right)
        right_widget.setFixedWidth(MEMBER_COLUMN_WIDTH)

        layout.addWidget(center_widget, 3)
        layout.addWidget(right_widget, 1)
        self.setLayout(layout)
        self._update_input_enabled()

        # 치트 오버레이는 레이아웃에 넣지 않고 채팅 영역 위에 겹쳐 띄움(테두리/배경 없이)
        self._cheat_overlay = CheatOverlay(self._center_stack)
        self._battlecruiser = BattlecruiserOverlay(self._center_stack)
        self._battlecruiser.attach_input(self.message_input.line)

        # 지금 프로토콜이 지원하는 슬래시 명령 목록 - 세션이 알려주면 갱신됨
        self._command_tokens: list[str] = []
        # 파일 올리기 담당(처음 누를 때 만든다 - 안 쓰면 아무것도 안 만들어진다)
        self._uploader = None
        self._uploading_channel = ""
        self._upload_queue: list[str] = []
        # 창에 끌어다 놓으면 올라간다. 사진인지 파일인지는 **내용을 보고** 정하므로
        # 사람이 미리 고를 필요가 없다(확장자는 거짓말을 한다)
        self.setAcceptDrops(True)


    def _open_emoji_picker(self):
        """이모티콘 보관함 열기/닫기.

        모달(exec)로 띄우지 않는 이유: 모달이면 창이 떠 있는 동안 이모티콘 버튼도 입력창도
        누를 수 없어서 "다시 눌러 닫기"가 안 된다. 하나만 띄우고 참조를 들고 있다가
        같은 버튼을 다시 누르거나 입력창을 누르면 닫는다.
        """
        from gui.emoji_picker import EmojiPicker

        if self._emoji_picker is not None and self._emoji_picker.isVisible():
            self._close_emoji_picker()
            return
        picker = EmojiPicker(self, fetcher=self._image_fetcher,
                             group=self.emoji_group())
        picker.emoji_chosen.connect(self._insert_emoji)
        picker.finished.connect(lambda _=0: setattr(self, "_emoji_picker", None))
        self._emoji_picker = picker
        picker.show()
        picker.raise_()

    def _close_emoji_picker(self):
        picker, self._emoji_picker = self._emoji_picker, None
        if picker is not None:
            picker.close()

    def _insert_emoji(self, url: str):
        """고른 이모티콘을 입력창에 넣음. 입력창에는 이름이 보이고 보낼 때 주소로 바뀐다."""
        import emoji_store

        name = ""
        for item in emoji_store.load_emojis():
            if item.get("url") == url:
                name = item.get("name", "")
                break
        self.message_input.insert_emoji(url, name)
        self._close_emoji_picker()
        self.message_input.focus()

    # ---------------- 파일·사진 올리기 ----------------
    # ---------------- 끌어다 놓기 ----------------

    def dragEnterEvent(self, event):  # noqa: N802 - Qt 규약
        if event.mimeData().hasUrls() and any(u.isLocalFile()
                                              for u in event.mimeData().urls()):
            event.acceptProposedAction()

    def dragMoveEvent(self, event):  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):  # noqa: N802
        """끌어다 놓은 것을 차례로 올린다.

        여러 개를 한꺼번에 놓을 수 있는데 동시에 올리면 서로 느려지기만 하므로 줄을
        세운다. 폴더는 건너뛴다(안에 뭐가 얼마나 있을지 알 수 없다).
        """
        import os

        paths = [url.toLocalFile() for url in event.mimeData().urls()
                 if url.isLocalFile()]
        files = [p for p in paths if p and os.path.isfile(p)]
        if not files:
            return
        event.acceptProposedAction()
        skipped = len(paths) - len(files)
        channel = self.active_channel()
        if skipped and channel:
            self.append_system(channel, f"폴더 {skipped}개는 건너뛰었습니다(파일만 올릴 수 있습니다).")
        self._upload_queue.extend(files)
        self._start_next_upload()

    def _start_next_upload(self):
        if self._uploading_channel or not self._upload_queue:
            return
        self._begin_upload(self._upload_queue.pop(0))

    def _cancel_upload(self):
        """올리는 줄의 '취소' - 지금 것만 멈추고 줄 선 것도 비운다."""
        dropped = len(self._upload_queue)
        self._upload_queue.clear()
        channel = self._uploading_channel
        if self._uploader is not None:
            self._uploader.cancel()
        if channel and dropped:
            self.append_system(channel, f"기다리던 {dropped}개도 함께 취소했습니다.")

    # ---------------- 올리기 ----------------

    def _ensure_uploader(self):
        if self._uploader is None:
            from gui.uploader import Uploader

            self._uploader = Uploader(self)
            self._uploader.refresh_limits()
            self._uploader.finished.connect(self._on_upload_done)
            self._uploader.progress.connect(self._on_upload_progress)

    def _begin_upload(self, path: str):
        import os

        self._ensure_uploader()
        self._uploading_channel = self.active_channel()
        self.upload_bar.start(os.path.basename(path))
        self._uploader.upload(path)

    def _upload(self, kind: str):
        """파일을 골라 올리고, 끝나면 **주소를 입력줄에 넣는다.**

        바로 보내지 않고 입력줄에 넣는 이유: 사람이 한마디 덧붙이거나("이거 봐") 잘못
        고른 것을 지울 수 있어야 한다. 주소가 들어가면 그 뒤는 이미 있는 길이 알아서
        한다 - 사진이면 미리보기가 뜨고, 파일이면 눌러서 받는 링크가 된다.
        """
        from PySide6.QtWidgets import QFileDialog

        if kind == "photo":
            title, filters = "사진 고르기", "사진 (*.png *.jpg *.jpeg *.gif *.webp *.bmp)"
        else:
            title, filters = "파일 고르기", "모든 파일 (*.*)"
        # 여러 개를 한 번에 고를 수 있게 한다 - 사진은 보통 여러 장을 같이 보낸다
        paths, _chosen = QFileDialog.getOpenFileNames(self, title, "", filters)
        if not paths:
            return
        self._upload_queue.extend(paths)
        self._start_next_upload()

    def _on_upload_progress(self, sent: int, total: int):
        # 큰 파일은 한참 걸린다 - 아무 표시가 없으면 멈춘 줄 안다
        self.upload_bar.set_progress(sent, total)

    def _on_upload_done(self, url: str, note: str):
        import gui_client  # 지연 import - 이유는 CLAUDE.md 1번

        self.upload_bar.stop()
        channel, self._uploading_channel = self._uploading_channel, ""
        if not url:
            # 조용히 실패하면 사람이 이유를 모른다
            if channel:
                self.append_system(channel, f"올리지 못했습니다: {note}")
            else:
                gui_client.themed_warning(self, "올리기 실패", note)
            self._start_next_upload()
            return
        if channel:
            self.append_system(channel, note)
        # 이미 쓰던 글이 있으면 뒤에 붙인다(덮어쓰면 쓰던 글이 날아간다)
        current = self.message_input.line.text()
        self.message_input.line.setText(f"{current} {url}".strip())
        self.message_input.focus()
        self._start_next_upload()

    def show_resource_cheat(self):
        """'show me the money'가 채널에 떴을 때 - 자원 오버레이를 채팅창 가운데에 잠깐 표시"""
        self._cheat_overlay.start()

    def summon_battlecruiser(self):
        """'배틀크루저 소환' - 채팅창 위에 함선을 띄움(방향키로 조종 가능)"""
        self._battlecruiser.summon()

    def dismiss_battlecruiser(self):
        """'배틀크루저 소환해제' - 순간 가속해서 화면 밖으로 빠져나가며 사라짐"""
        self._battlecruiser.dismiss()

    def emoji_group(self) -> str:
        """이모티콘을 누구와 같이 쓰는가 - 같은 채팅 서버를 쓰는 사람들.

        화면은 접속 정보를 모르므로 바깥(창)에서 넣어준다. 못 받았으면 빈 값이고,
        그러면 '다 같이 쓰는 것' 칸이 아예 안 보인다.
        """
        return getattr(self, "_emoji_group", "")

    def set_emoji_group(self, group: str):
        self._emoji_group = group

    def battle_host(self):
        """전투 화면이 올라갈 자리 - 혼자 나는 배틀크루저와 같은 곳(채팅 영역 위)."""
        return self._center_stack

    def set_protocol_mode(self, mode: str):
        self._protocol_mode = mode
        # 프로토콜이 바뀌면 예전 세상의 아이콘/닉네임은 의미가 없음
        self.member_panel.clear_display_cache()

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
        return self.member_panel.display_name(user_id)

    def _update_input_enabled(self):
        self.message_input.set_enabled(bool(self._active_channel))

    def add_channel(self, channel: str, activate: bool = True):
        if channel not in self._log_views:
            view = ChannelLogView(channel, image_fetcher=self._image_fetcher)
            view.set_container_width(self.tabs.width())
            self._log_views[channel] = view
            self.member_panel.set_members(channel, [])
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
        self.member_panel.forget_channel(channel)
        index = self.tabs.indexOf(view)
        if index >= 0:
            self.tabs.removeTab(index)  # 남은 탭이 있으면 currentChanged가 활성 채널을 갱신함
        self.channel_sidebar.remove_channel(channel)
        view.deleteLater()
        if not self._log_views:
            self._active_channel = ""
            self.channel_header.setText("")
            self._center_stack.setCurrentWidget(self._empty_label)
            self.member_panel.clear()
            if self.on_all_channels_left is not None:
                self.on_all_channels_left()
        self._update_input_enabled()

    def reset(self):
        """로그아웃 등으로 세션이 끝났을 때 화면을 깨끗이 비움 - 이전 계정의 대화/참여자가
        다음 로그인 화면에 남아있으면 안 됨"""
        for channel in list(self._log_views.keys()):
            self.remove_channel(channel)
        self.member_panel.reset()
        self.my_id = ""
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
        self.member_panel.show_channel(view.channel_name)
        self._update_input_enabled()
        # 폭은 ChatPage._push_wrap_width()가 채널 추가/창 리사이즈 시점에 이미 모든 탭에
        # (비활성 탭 포함) 미리 반영해두므로, 탭을 볼 때 다시 재계산할 필요가 없음 -
        # 예전에는 여기서 매번 재계산했는데, 그게 메시지들이 눈앞에서 다시 배치되며
        # 스크롤이 출렁이는(위로 튀는) 원인이었음

    def _toggle_sidebar(self):
        """채널 목록을 접거나 편다 - **화면은 한 번만 다시 그린다.**

        목록 폭이 줄어드는 것과 창 폭이 줄어드는 것은 두 단계로 일어난다. 그 사이 상태가
        그대로 그려지면 대화창이 한 번 확 넓어졌다가 제자리로 돌아오는 것처럼 보인다
        (실측: 접을 때 418 -> 598 -> 418). 그리는 것을 잠깐 멈춰두면 중간이 안 보인다.
        """
        window = self.window()
        window.setUpdatesEnabled(False)
        try:
            self.channel_sidebar.toggle_collapsed()
        finally:
            # 이번 처리(창 크기 조정 포함)가 다 끝난 뒤에 한 번만 그린다
            QTimer.singleShot(0, lambda: window.setUpdatesEnabled(True))

    def _place_gear(self, collapsed: bool):
        """톱니는 언제나 **왼쪽 아래**에 있어야 한다.

        - 펼쳤을 때: 채널 목록 아래(목록에 딸린 도구처럼 보인다)
        - 접었을 때: 목록이 사라지므로 손잡이 열의 맨 아래로 옮긴다(같은 왼쪽 아래)

        가운데로 올려봤더니 "저기 있으면 어떡해, 아래에 있어야지"가 됐다. 자리를 옮겨
        끼우는 이유는 접힌 목록의 폭이 0이라 그 안에 두면 잘려서다.
        """
        column = self._handle_column
        column.removeWidget(self.gear_btn)
        self.channel_sidebar.gear_slot.removeWidget(self.gear_btn)
        # 손잡이는 늘 창 세로 가운데에 있어야 한다. 아래에 톱니가 붙는 동안에는 위에도
        # 같은 높이를 비워둬야 균형이 맞는다(안 그러면 그 절반만큼 위로 밀린다)
        if self._gear_balance is not None:
            column.removeItem(self._gear_balance)
            self._gear_balance = None
        if collapsed:
            column.insertSpacing(0, GEAR_BTN_PX)
            self._gear_balance = column.itemAt(0)
            column.addWidget(self.gear_btn, 0, Qt.AlignmentFlag.AlignHCenter)
        else:
            self.channel_sidebar.gear_slot.addWidget(
                self.gear_btn, 0, Qt.AlignmentFlag.AlignLeft)
        self.gear_btn.show()

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
        # 보내는 순간 바로 맨 아래로. 서버를 돌아온 내 메시지가 늦게 도착해도
        # 그때 한 번 더 따라 내려간다(ChannelLogView가 표시를 들고 있음)
        view = self._log_views.get(self._active_channel)
        if view is not None:
            view.scroll_to_bottom()
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
        members = self.member_panel.members_of(self._active_channel)
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

    def _avatar_for(self, user_id: str, size: int):
        return self.member_panel.avatar(user_id, size)

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

    def append_system(self, channel: str, text: str, ts: float = 0.0):
        view = self._log_views.get(channel)
        if view is None:
            return
        view.append_system(text, ts)

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

    def update_userlist(self, channel: str, users: list[str]):
        self.member_panel.set_members(channel, users)

    def set_avatar(self, user_id: str, avatar_b64: str | None):
        self.member_panel.set_avatar(user_id, avatar_b64)

    def has_avatar(self, user_id: str) -> bool:
        return self.member_panel.has_avatar(user_id)

    def set_client_version(self, user_id: str, version: str):
        """그 사람이 무슨 프로그램으로 접속했는지 - 참여자 목록에 작은 로고로 표시된다."""
        self.member_panel.set_client_version(user_id, version)

    def set_nickname(self, user_id: str, nickname: str | None):
        self.member_panel.set_nickname(user_id, nickname)
