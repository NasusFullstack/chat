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

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QPushButton, QStackedWidget,
                               QTabWidget, QVBoxLayout, QWidget)

import app_prefs
from chat_core.commands import COMMAND_PREFIX, KIND_ACTION, KIND_NOTICE
from gui.battlecruiser import BattlecruiserOverlay
from gui.cheat_overlay import CheatOverlay
from gui.components.app_footer import AppFooter
from gui.components.channel_sidebar import ChannelSidebar
from gui.components.member_panel import MemberPanel
from gui.components.message_input import MessageInput
from gui.components.message_log import ChannelLogView
from gui.link_preview import ImageFetcher
from gui.theme import AVATAR_MSG_PX, CHANNEL_SIDEBAR_WIDTH

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
        # 접어둔 채로 껐으면 다음에도 접힌 채로 연다(매번 다시 접게 하면 성가심)
        self.channel_sidebar.set_collapsed(app_prefs.get("channel_sidebar_collapsed"))
        self.channel_sidebar.collapsed_changed.connect(
            lambda on: app_prefs.set_value("channel_sidebar_collapsed", on))
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
        self.member_panel = MemberPanel(MEMBER_HEADER_HEIGHT)
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

    def update_userlist(self, channel: str, users: list[str]):
        self.member_panel.set_members(channel, users)

    def set_avatar(self, user_id: str, avatar_b64: str | None):
        self.member_panel.set_avatar(user_id, avatar_b64)

    def set_nickname(self, user_id: str, nickname: str | None):
        self.member_panel.set_nickname(user_id, nickname)
