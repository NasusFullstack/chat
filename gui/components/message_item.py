"""메시지 한 줄을 그리는 위젯.

한 메시지는 [아이콘][글자 + (링크 미리보기) + (이모티콘)][시간 배지]로 이루어진다.
말풍선 안에서 무엇을 어떻게 배치할지는 전부 여기서 정하고, 목록(ChannelLogView)은
이 위젯을 세로로 쌓기만 한다.

이름들은 몽키패치 대상이 아니라 어디서든 직접 import해도 안전함
(gui_client.py의 순환참조 노트 참고 - 그 규칙은 다른 5개 함수에만 적용됨).
"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from chat_core.commands import KIND_ACTION, KIND_CHAT, KIND_NOTICE, split_emoji_parts
from gui.helpers import _format_ts, _linkify, extract_urls, text_is_only_urls
from gui.theme import AVATAR_MSG_PX, TIMESTAMP_BADGE_HEIGHT_PX

# 폭 계산에 두는 여유. 스크롤바가 나타나는 순간 viewport가 그만큼 좁아지는데, 그 폭을
# 미리 빼두지 않으면 "넘침 -> 스크롤바 등장 -> 더 좁아져서 또 넘침"이 반복됨
_WRAP_SAFETY_PX = 4


def _message_html(sender: str, safe_text: str, mine: bool, kind: str) -> str:
    """메시지 종류별 표시 형식 - IRC 클라이언트들의 관행을 그대로 따름.

    /me(행동)는 "* 닉 행동", /notice(공지)는 "-닉- 내용"으로 보통 채팅과 눈에 띄게 구분한다.
    """
    if kind == KIND_ACTION:
        return f'<span style="color:#b39ddb"><i>* <b>{sender}</b> {safe_text}</i></span>'
    if kind == KIND_NOTICE:
        return f'<span style="color:#7fd6a8">-<b>{sender}</b>- {safe_text}</span>'
    color = "#7cd0ff" if mine else "#ffd27c"
    return f'<span style="color:{color}"><b>{sender}</b></span>: {safe_text}'


class MessageWidget(QWidget):
    """채팅 메시지 한 개 - 왼쪽에 아바타, 오른쪽 아래에 시간 타원 배지"""

    def __init__(self, sender: str, text: str, mine: bool, ts: float, avatar_pixmap: QPixmap,
                 parent=None, kind: str = KIND_CHAT, preview: bool = False, image_fetcher=None):
        super().__init__(parent)
        # 말풍선 배경은 채팅 카드 면색이 그대로 비쳐야 함. objectName으로 한정하지 않으면
        # 이 규칙이 자식(링크 미리보기 카드 등)까지 상속돼 그쪽 배경/테두리를 지워버림
        self.setObjectName("messageRow")
        self.setStyleSheet("QWidget#messageRow { background: transparent; }")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 1, 4, 1)

        avatar_label = QLabel()
        avatar_label.setObjectName("messageAvatar")
        avatar_label.setStyleSheet("QLabel#messageAvatar { background: transparent; }")
        avatar_label.setFixedSize(AVATAR_MSG_PX, AVATAR_MSG_PX)
        avatar_label.setPixmap(avatar_pixmap.scaled(
            AVATAR_MSG_PX, AVATAR_MSG_PX,
            Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.FastTransformation,
        ))
        layout.addWidget(avatar_label, 0, Qt.AlignmentFlag.AlignTop)

        # 텍스트를 시간 배지와 같은 QHBoxLayout에 나란히 넣으면 word-wrap 라벨의
        # sizeHint()가 줄바꿈 전(한 줄) 너비를 그대로 요구해버려서 채팅창 폭을 넘어서는
        # 메시지가 오른쪽으로 잘리고, 그 여파로 스크롤 영역 크기 계산도 꼬여 아래쪽에
        # 빈 공간이 생기는 문제가 있었음. 텍스트를 세로 레이아웃에서 혼자 전체 폭을
        # 쓰게 하면 Qt가 heightForWidth를 제대로 적용해 창 크기에 맞춰 줄바꿈됨.
        body = QVBoxLayout()
        body.setSpacing(1)

        # 이모티콘 표시가 섞여 있으면 글자와 분리한다. 글자는 평소대로 라벨에 넣고,
        # 이모티콘은 아래에 작은 그림으로 붙인다(주소 문자열이 대화에 보이면 안 됨)
        parts = split_emoji_parts(text)
        self.emoji_urls = [value for kind_, value in parts if kind_ == "emoji"]
        plain_text = "".join(value for kind_, value in parts if kind_ == "text")

        safe_text = plain_text.replace("<", "&lt;").replace(">", "&gt;")
        safe_text = _linkify(safe_text)
        text_label = QLabel(_message_html(sender, safe_text, mine, kind))
        text_label.setObjectName("messageText")
        text_label.setStyleSheet("QLabel#messageText { background: transparent; }")
        text_label.setTextFormat(Qt.TextFormat.RichText)
        text_label.setWordWrap(True)
        text_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        text_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.LinksAccessibleByMouse
        )
        text_label.setOpenExternalLinks(True)
        text_label.setCursor(Qt.CursorShape.IBeamCursor)
        body.addWidget(text_label)
        self._text_label = text_label

        # 링크 미리보기 자리. 못 받으면 높이 0이라 평소 메시지와 똑같이 보임
        self.preview_area = None
        self.preview_urls = extract_urls(text) if preview else []
        # 링크만 있는 메시지는 미리보기가 뜨면 주소 문자열을 지움 - 긴 주소가 몇 줄씩
        # 차지하기만 하고, 그림/카드를 눌러 열 수 있어서 주소가 없어도 못 여는 일이 없음.
        # 미리보기를 끝내 못 받으면 콜백이 안 불려서 주소가 그대로 남음
        self._sender_only_html = _message_html(sender, "", mine, kind).rstrip(": ")
        self._link_only = bool(self.preview_urls) and text_is_only_urls(plain_text)

        # 이모티콘은 링크 미리보기(320px)와 달리 글자 옆에 붙는 작은 그림이다.
        # 여러 개면 가로로 이어 붙는다
        self.emoji_area = None
        if self.emoji_urls:
            from gui.emoji_view import EmojiRow
            self.emoji_area = EmojiRow(self.emoji_urls, image_fetcher, self)
            body.addWidget(self.emoji_area)
            if not plain_text.strip():
                # 이모티콘만 보낸 메시지 - 보낸 사람만 남기고 빈 줄은 없앰
                self._text_label.setText(self._sender_only_html)
        if self.preview_urls:
            from gui.link_preview import LinkPreviewArea
            self.preview_area = LinkPreviewArea(
                self.preview_urls, image_fetcher, self,
                on_preview_shown=self._hide_url_text if self._link_only else None,
            )
            # 정렬을 주면 남는 세로 공간을 이 칸에 몰아주지 않는다(필요한 만큼만 차지)
            body.addWidget(self.preview_area, 0, Qt.AlignmentFlag.AlignTop)

        badge_row = QHBoxLayout()
        badge_row.addStretch(1)
        badge = QLabel(_format_ts(ts))
        badge.setObjectName("timestampBadge")
        badge.setFixedHeight(TIMESTAMP_BADGE_HEIGHT_PX)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge_row.addWidget(badge)
        body.addLayout(badge_row)

        layout.addLayout(body, 1)

    def _hide_url_text(self):
        """미리보기가 떴으니 주소 문자열은 지우고 보낸 사람만 남김.

        라벨을 통째로 숨기지 않는 이유: 누가 보낸 건지는 남아야 하기 때문.
        글자가 줄어들면 높이도 줄어드는데, 그걸 레이아웃에 알리지 않으면 예전 높이가
        그대로 남아 아래에 빈 공간이 생긴다."""
        self._text_label.setText(self._sender_only_html)
        self._text_label.updateGeometry()
        self.updateGeometry()

    def set_wrap_width(self, view_width: int):
        """네트워크로 비동기로 도착한 메시지는 QScrollArea 레이아웃이 아직 완전히
        안정되기 전에 위젯이 추가될 때가 있어, word-wrap 라벨의 자동 heightForWidth
        계산이 화면 폭을 반영 못 하고 줄바꿈이 안 풀린 채로 굳어버리는 경우가 있었음
        (내가 직접 보낸 메시지는 항상 창이 안정된 상태에서 추가돼서 이 문제가 안 드러남).
        Qt의 자동 계산에 기대는 대신 뷰포트 폭을 직접 계산해서 넘겨주면 타이밍과
        무관하게 항상 정확히 줄바꿈됨."""
        # 빼야 할 폭을 상수로 어림잡지 말고 실제 레이아웃 값에서 계산할 것.
        # 예전엔 24로 어림했는데 실제 여백/간격 합과 안 맞아서, 좁은 창에서 그림이
        # 10px쯤 삐져나가 가로 스크롤이 생기고 오른쪽이 잘려 보였음
        row = self.layout()
        margins = row.contentsMargins()
        overhead = (AVATAR_MSG_PX + margins.left() + margins.right() + row.spacing()
                    + _WRAP_SAFETY_PX)
        inner_width = max(40, view_width - overhead)
        self._text_label.setMaximumWidth(inner_width)
        # 미리보기 그림/카드도 같은 폭 안에 들어와야 함. 안 그러면 채팅창이 좁을 때
        # 그림이 밖으로 삐져나가 가로 스크롤이 생기고 시간 배지까지 화면 밖으로 밀림
        if self.preview_area is not None:
            self.preview_area.set_max_width(inner_width)


def _build_system_label(text: str) -> QLabel:
    label = QLabel(f'<span style="color:#9a9cad"><i>* {text}</i></span>')
    label.setObjectName("systemNotice")
    label.setStyleSheet("QLabel#systemNotice { background: transparent; }")
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    label.setWordWrap(True)
    return label
