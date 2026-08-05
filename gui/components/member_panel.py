"""오른쪽 참여자 목록 - 인원수 헤더 + 아이콘 붙은 이름 목록.

여기 담긴 것은 "지금 채널에 누가 있고, 각자 어떤 아이콘/닉네임으로 보이는가"뿐이다.
대화 내용도, 채널 목록도, 입력창도 모른다.

아이콘/닉네임 캐시(_avatars, _nicknames)를 이 컴포넌트가 들고 있는 이유:
값의 출처는 도메인 이벤트뿐이고(코어가 판단해서 내려준다), 여기서는 그걸 화면에 그리기만
한다. 매번 세션에 되물으면 그릴 때마다 역참조가 생기고, 그렇다고 화면 여기저기에 흩어두면
어디가 최신인지 알 수 없게 된다. **그리는 쪽에 캐시를 두되 판단은 절대 하지 않는다**가
이 코드베이스의 규칙이다(CLAUDE.md "상태의 단일 출처" 참고).
"""
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QLabel, QListWidget, QListWidgetItem, QVBoxLayout, QWidget

import avatar_store
from gui.helpers import _decode_avatar_pixmap, _hashed_avatar_pixmap
from gui.theme import AVATAR_LIST_PX, MEMBER_ROW_HEIGHT, MEMBER_VISIBLE_ROWS


class MemberPanel(QWidget):
    """채널 참여자 목록."""

    def __init__(self, header_height: int, parent=None):
        super().__init__(parent)
        column = QVBoxLayout(self)
        # 세 열(채널/채팅/참여자)의 여백을 0으로 통일해야 세로 시작점이 같아짐
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)

        # objectName을 주면 안 됨 - 채팅 헤더(channelHeader)는 굵고 흰 글씨라 모양이 달라진다.
        # 지금은 기본 QLabel 스타일 그대로여야 예전 화면과 픽셀까지 같다
        self.header = QLabel(_header_text(0))
        self.header.setFixedHeight(header_height)
        self.header.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        column.addWidget(self.header)

        self.list = QListWidget()
        self.list.setObjectName("memberList")
        self.list.setIconSize(QSize(AVATAR_LIST_PX, AVATAR_LIST_PX))
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # 창 끝까지 늘리지 않고 여섯 줄만 - 그 아래 프로필 버튼과 만든이 표시가 밀려나지
        # 않게. 넘치는 사람은 얇은 스크롤바로 내려서 본다
        self.list.setFixedHeight(MEMBER_ROW_HEIGHT * MEMBER_VISIBLE_ROWS + 2)
        column.addWidget(self.list, 0)

        # 채널별 참여자와, 사람별 표시 정보. 값의 출처는 도메인 이벤트뿐이다
        self._members: dict[str, list[str]] = {}
        self._avatars: dict[str, QPixmap] = {}
        self._nicknames: dict[str, str] = {}
        self._active_channel = ""

        # 예전에 본 적 있는 사람의 아이콘을 로컬에서 되살림. 실제 IRC 서버는 아이콘을
        # 저장해주지 않아서, 이게 없으면 상대가 다시 보내줄 때까지 기본 도트만 보인다
        for user_id, avatar_b64 in avatar_store.load_avatars().items():
            pixmap = _decode_avatar_pixmap(avatar_b64)
            if pixmap is not None:
                self._avatars[user_id] = pixmap

    # ---------------- 목록 ----------------

    def show_channel(self, channel: str):
        """보고 있는 채널이 바뀌었을 때 - 그 채널 참여자로 갈아끼움."""
        self._active_channel = channel
        self._redraw()

    def set_members(self, channel: str, users: list[str]):
        self._members[channel] = list(users)
        if channel == self._active_channel:
            self._redraw()

    def members_of(self, channel: str) -> list[str]:
        return self._members.get(channel, [])

    def forget_channel(self, channel: str):
        self._members.pop(channel, None)

    def clear(self):
        self.list.clear()
        self.header.setText(_header_text(0))

    def reset(self):
        """로그아웃 등 - 이전 계정의 참여자/아이콘이 다음 로그인에 남으면 안 됨"""
        self._members.clear()
        self._avatars.clear()
        self._nicknames.clear()
        self._active_channel = ""
        self.list.clear()
        self.header.setText(_header_text(0))

    def count(self) -> int:
        return self.list.count()

    def _redraw(self):
        self.list.clear()
        for user_id in self._members.get(self._active_channel, []):
            display = self.display_name(user_id)
            item = QListWidgetItem(display)
            if display != user_id:
                # 닉네임은 고유성이 보장되지 않으므로 원래 아이디를 툴팁으로 확인 가능하게
                item.setToolTip(user_id)
            item.setIcon(QIcon(self.avatar(user_id, AVATAR_LIST_PX)))
            # 줄 높이를 못박아야 "여섯 줄"이 글꼴에 상관없이 정확히 여섯 줄이 된다
            item.setSizeHint(QSize(0, MEMBER_ROW_HEIGHT))
            self.list.addItem(item)
        self.header.setText(_header_text(self.list.count()))

    # ---------------- 표시 정보 ----------------

    def display_name(self, user_id: str) -> str:
        return self._nicknames.get(user_id, user_id)

    def avatar(self, user_id: str, size: int) -> QPixmap:
        """그 사람 아이콘. 없으면 아이디로 색을 정한 기본 도트."""
        pixmap = self._avatars.get(user_id)
        if pixmap is None:
            pixmap = _hashed_avatar_pixmap(user_id)
        return pixmap.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                             Qt.TransformationMode.FastTransformation)

    def set_avatar(self, user_id: str, avatar_b64):
        if not avatar_b64:
            self._avatars.pop(user_id, None)
        else:
            pixmap = _decode_avatar_pixmap(avatar_b64)
            if pixmap is not None:
                self._avatars[user_id] = pixmap
                # 실제 IRC 서버는 아이콘을 저장해주지 않으므로 로컬에도 남겨둬서, 다음에
                # 앱을 켰을 때 상대가 다시 보내주기 전에도 곧바로 보이게 함
                avatar_store.save_avatar(user_id, avatar_b64)
        if self._active_channel:
            self._redraw()

    def set_nickname(self, user_id: str, nickname):
        if not nickname:
            self._nicknames.pop(user_id, None)
        else:
            self._nicknames[user_id] = nickname
        if self._active_channel:
            self._redraw()

    def has_avatar(self, user_id: str) -> bool:
        return user_id in self._avatars

    def clear_display_cache(self):
        """프로토콜이 바뀌면 아이콘/닉네임은 다른 세상 것이 되므로 비움"""
        self._avatars.clear()
        self._nicknames.clear()


def _header_text(count: int) -> str:
    """머리글에 인원수를 같이 보여준다 - 목록이 잘려 보이므로 전체가 몇 명인지 알 수 있게."""
    return f"참여자 {count}명"
