"""색상/크기/타이밍 상수와 전체 QSS 스타일시트.

여기 있는 이름들은 몽키패치 대상이 아니라 어디서든 자유롭게 직접 import해도 안전함
(gui_client.py의 순환참조 노트 참고 - 함수 5개만 그 규칙이 적용됨).
"""
import sys

IS_WINDOWS = sys.platform == "win32"

# 사이드바 아래에 두는 만든이 표시
DEVELOPER_EMAIL = "seven7973@gmail.com"
DEVELOPER_NAME = "NasusFullstack"
DEVELOPER_GITHUB = "NasusFullstack"          # 깃허브 계정
GITHUB_URL = "https://github.com/NasusFullstack/chat"
COPYRIGHT_YEAR = 2026
FOOTER_LOGO_PX = 52
# 채널이 많아 자리가 모자랄 때 목록을 미는 화살표 버튼 높이
CHANNEL_SCROLL_BTN_PX = 18

CONNECT_TIMEOUT_MS = 10_000
# 서버가 끊겼을 때 자동 재접속: 시도할수록 간격을 늘림(죽은 서버를 계속 두드리지 않게)
RECONNECT_BASE_MS = 3_000
RECONNECT_MAX_MS = 30_000
RECONNECT_MAX_ATTEMPTS = 10
DEFAULT_SSL_PORT = "6697"
DEFAULT_PLAIN_PORT = "6667"

# 말풍선 시간 배지: 지금 기준 폰트(STYLE_SHEET의 14px)의 절반을 고정값으로 씀 -
# 나중에 앱 기본 폰트 크기가 바뀌어도 이 값 자체는 따라 커지지 않음
TIMESTAMP_BADGE_FONT_PX = 7
TIMESTAMP_BADGE_HEIGHT_PX = 14

UNREAD_BLINK_COLOR = "#ffcc4d"
UNREAD_BLINK_INTERVAL_MS = 350
UNREAD_BLINK_COUNT = 4  # 안 보는 채널에 새 메시지가 오면 이 횟수만큼 반짝인 뒤 밝은 색으로 고정됨
UNREAD_DOT_PX = 9

# 채널 목록은 왼쪽 사이드바에 세로로 쌓는다. 예전엔 채팅창 위쪽 가로 탭이었는데,
# 채널이 늘면 폭이 모자라 이름이 잘리고 탭이 들쭉날쭉해 보였음
CHANNEL_SIDEBAR_WIDTH = 190
CHANNEL_ROW_HEIGHT = 44
CHANNEL_ROW_GAP = 6  # QSS의 QListWidget#channelList::item margin-bottom과 값을 맞출 것
ADD_TAB_LABEL = "+"

# 아래 둘은 예전 가로 탭 시절 값 - 남아있는 참조가 있어 유지만 함
CHANNEL_TAB_FIXED_WIDTH = 140
CHANNEL_TAB_HEIGHT = 34
ADD_TAB_WIDTH = 40

MENTION_COOLDOWN_SEC = 60  # 같은 채널에서 같은 사람을 다시 @호출하려면 이만큼 기다려야 함

AVATAR_LIST_PX = 16
AVATAR_MSG_PX = 16  # 참여자 목록과 채팅창 아이콘이 항상 같은 크기/이미지로 보이게 통일
AVATAR_GRID_SIZE = 16
AVATAR_CELL_PX = 20  # 에디터에서 한 칸을 그리는 픽셀 크기 (실제 저장되는 아이콘 크기와는 무관)
# store.py의 AVATAR_MAX_B64_CHARS와 값을 맞춰야 함
AVATAR_MAX_B64_CHARS = 2000
# store.py의 NICKNAME_MAX_LEN과 값을 맞춰야 함
NICKNAME_MAX_LEN = 20

APP_TITLE = "춥채팅"

# 스타일시트 본문은 영역별로 gui/styles/ 아래에 나눠져 있다(합친 결과는 예전과 동일).
# 여기서는 크기/색 상수와 "합치는 일"만 담당한다
from gui.styles import build_stylesheet  # noqa: E402 - 상수 정의 뒤에 와야 함

STYLE_SHEET = build_stylesheet(TIMESTAMP_BADGE_FONT_PX)
