"""색상/크기/타이밍 상수와 전체 QSS 스타일시트.

여기 있는 이름들은 몽키패치 대상이 아니라 어디서든 자유롭게 직접 import해도 안전함
(gui_client.py의 순환참조 노트 참고 - 함수 5개만 그 규칙이 적용됨).
"""
import sys

IS_WINDOWS = sys.platform == "win32"

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

STYLE_SHEET = """
QWidget {
    background-color: #1e1f29;
    color: #e6e6e6;
    font-family: "Malgun Gothic", "맑은 고딕", sans-serif;
    font-size: 14px;
}
QLineEdit {
    background-color: #2a2b38;
    border: 1px solid #3d3f52;
    border-radius: 8px;
    padding: 8px;
    color: #ffffff;
}
QLineEdit:focus {
    border: 1px solid #7c6cf0;
}
QPushButton {
    background-color: #7c6cf0;
    border: none;
    border-radius: 8px;
    padding: 10px 16px;
    color: white;
    font-weight: bold;
}
QPushButton:hover {
    background-color: #6a5be0;
}
QPushButton:pressed {
    background-color: #5a4bd0;
}
QPushButton#secondary {
    background-color: #3d3f52;
}
QPushButton#secondary:hover {
    background-color: #4a4d63;
}
/* --- 공통 디자인 토큰 ---
   테두리색: 기본 #3d3f52 / 강조(포커스·팝업) #7c6cf0
   면색: 기본 #1e1f29, 가라앉은 영역 #16171f, 떠 있는 컨트롤 #2a2b38
   모서리: 컨테이너 10px, 컨트롤 8px, 작은 요소 6px
   위젯마다 제각각이던 값을 이 규칙으로 통일함 */
QFrame#card {
    background-color: #22232e;
    border: 1px solid #3d3f52;
    border-radius: 10px;
    padding: 18px;
}
QScrollArea {
    background-color: #16171f;
    border: 1px solid #3d3f52;
    border-radius: 10px;
}
/* 레이아웃 용도로만 쓰는 스크롤 영역(로그인 폼 감싸기) - 테두리/배경 없이 투명하게 */
QScrollArea#plainScroll, QScrollArea#plainScroll > QWidget > QWidget {
    background: transparent;
    border: none;
}
QListWidget {
    background-color: #16171f;
    border: 1px solid #3d3f52;
    border-radius: 10px;
    padding: 4px;
}
QListWidget::item {
    padding: 4px 6px;
    border-radius: 6px;
}
QListWidget::item:selected {
    background-color: #3d3f52;
    color: #ffffff;
}
QComboBox {
    background-color: #2a2b38;
    border: 1px solid #3d3f52;
    border-radius: 8px;
    padding: 7px 10px;
    color: #ffffff;
}
QComboBox:hover {
    border: 1px solid #4a4d63;
}
QComboBox:focus {
    border: 1px solid #7c6cf0;
}
QComboBox::drop-down {
    border: none;
    width: 22px;
}
QComboBox QAbstractItemView {
    background-color: #22232e;
    border: 1px solid #3d3f52;
    border-radius: 8px;
    selection-background-color: #7c6cf0;
    selection-color: #ffffff;
    outline: none;
    padding: 4px;
}
QCheckBox {
    spacing: 8px;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid #3d3f52;
    border-radius: 4px;
    background-color: #2a2b38;
}
QCheckBox::indicator:hover {
    border: 1px solid #7c6cf0;
}
QCheckBox::indicator:checked {
    background-color: #7c6cf0;
    border: 1px solid #7c6cf0;
}
QLabel#title {
    font-size: 20px;
    font-weight: bold;
    padding-bottom: 8px;
}
QLabel#hint {
    color: #9a9cad;
    font-size: 12px;
}
QLabel#startupTitle {
    font-size: 26px;
    font-weight: bold;
    color: #ffffff;
}
QProgressBar {
    background-color: #2a2b38;
    border: 1px solid #3d3f52;
    border-radius: 6px;
    height: 8px;
}
QProgressBar::chunk {
    background-color: #7c6cf0;
    border-radius: 5px;
}
QLabel#status_err {
    color: #ff6b6b;
}
/* 오류가 아닌 진행/안내 문구 - 서버가 보내는 접속 안내나 "연결 중..." 같은 것들.
   이것까지 빨갛게 보여주면 아무 문제 없는데도 오류가 난 것처럼 보임 */
QLabel#status_info {
    color: #9a9cad;
}
/* font-size 값은 TIMESTAMP_BADGE_FONT_PX 상수와 반드시 일치시킬 것 (아래에서 .replace()로 실제로 대입함) */
QLabel#timestampBadge {
    background-color: rgba(154, 156, 173, 100);
    color: #cfd0da;
    font-size: __TIMESTAMP_BADGE_FONT_PX__px;
    border-radius: 7px;
    padding: 0px 7px;
}
/* 탭 영역에는 테두리를 두지 않음. 예전엔 pane 테두리 + 탭 테두리 + 채팅영역이 겹쳐서
   선이 끊긴 것처럼 보였음. 지금은 채팅 로그(QScrollArea#chatLog)가 참여자 목록과
   완전히 같은 카드 테두리를 갖고, 탭은 그 위에 얹히는 형태라 선이 하나로 깔끔함 */
QTabWidget::pane {
    background: transparent;
    border: none;
    top: 0px;
}
/* 탭은 사방이 닫힌 '칩' 모양으로 두고 채팅 카드와 살짝 띄움. 예전처럼 탭 아래를 열어두면
   그 아래를 지나는 카드 테두리 선과 만나 선이 끊긴 것처럼 보임.
   좌우 여백(padding)은 닫기(×) 버튼 자리를 침범하지 않도록 오른쪽을 넉넉히 둠 */
QTabBar::tab {
    background-color: #23242f;
    color: #9a9cad;
    padding: 0px 8px 0px 12px;
    border: 1px solid #34364a;
    border-radius: 8px;
    margin-right: 6px;
    margin-bottom: 8px;
}
/* 선택된 탭은 테두리 색만 바꾸는 정도로는 눈에 잘 안 띄어서, 면색까지 강조색 계열로
   채워 "지금 보고 있는 채널"이 한눈에 들어오게 함 */
QTabBar::tab:selected {
    background-color: #3a3560;
    color: #ffffff;
    border: 1px solid #7c6cf0;
    font-weight: bold;
}
QTabBar::tab:hover:!selected {
    background-color: #2f3140;
    color: #cfd0da;
    border: 1px solid #4a4d63;
}
/* ---- 왼쪽 채널 사이드바 ---- */
QWidget#channelSidebar {
    background: transparent;
}
/* 채널 목록은 테두리 없는 투명 배경 위에 '알약' 항목만 떠 있는 형태.
   참여자 목록처럼 카드로 감싸지 않는 이유: 감싸면 채팅 카드와 나란히 두 겹으로 보임 */
QListWidget#channelList {
    background: transparent;
    border: none;
    padding: 0px;
    outline: none;
}
QListWidget#channelList::item {
    background-color: #23242f;
    color: #cfd0da;
    border: 1px solid #34364a;
    border-radius: 10px;
    padding: 0px 12px;
    margin-bottom: 6px;
}
QListWidget#channelList::item:hover {
    background-color: #2f3140;
    color: #ffffff;
}
/* 지금 보고 있는 채널 - 면색까지 강조색으로 채워 한눈에 들어오게 */
QListWidget#channelList::item:selected {
    background-color: #5b52d9;
    color: #ffffff;
    border: 1px solid #7c6cf0;
    font-weight: bold;
}
/* 채널 추가 - 마지막 채널 바로 아래에 네모 없이 '+' 기호만.
   채널 항목과 같은 폭을 차지하되 배경/테두리가 없어서 기호만 떠 있는 것처럼 보임 */
QPushButton#addChannelBtn {
    background: transparent;
    color: #7f8296;
    border: none;
    font-size: 20px;
    font-weight: bold;
    padding: 0px;
}
/* 채팅창 위에 지금 보고 있는 채널 이름 */
QLabel#channelHeader {
    color: #e6e6e6;
    font-size: 15px;
    font-weight: bold;
    background: transparent;
}
QPushButton#addChannelBtn:hover {
    background: transparent;
    color: #ffffff;
    border: none;
}
/* 채팅 로그 - 참여자 목록(QListWidget)과 같은 면색/테두리/모서리로 통일.
   viewport와 그 안의 내용 위젯은 반드시 투명해야 함: 불투명하면 사각형인 자식 위젯이
   둥근 모서리 위를 덮어 그려서 모서리가 잘려나간 것처럼 보임(실제로 그 증상이 났었음) */
QScrollArea#chatLog {
    background-color: #16171f;
    border: 1px solid #3d3f52;
    border-radius: 10px;
}
QScrollArea#chatLog > QWidget > QWidget {
    background: transparent;
}
/* '+' 채널 추가 탭 - 항상 마지막 탭이라는 설계상의 불변조건을 이용해 :last로 구분함
   (disabled로 구분하려 했으나 disabled 탭은 마우스 이벤트 자체를 못 받아 클릭이 아예
   안 먹혔던 문제가 있어서 enabled로 바꿈) */
QTabBar::tab:last {
    background-color: #1e1f29;
    color: #9a9cad;
    border: 1px solid #34364a;
    padding: 0px;
    font-weight: bold;
    font-size: 16px;
}
QTabBar::tab:last:hover {
    background-color: #2f3140;
    color: #ffffff;
    border: 1px solid #7c6cf0;
}
QScrollBar:vertical {
    background: transparent;
    width: 8px;
    margin: 0px;
}
QScrollBar::handle:vertical {
    background: #3d3f52;
    border-radius: 4px;
    min-height: 24px;
}
QScrollBar::handle:vertical:hover {
    background: #4a4d63;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
    border: none;
    background: none;
}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: none;
}
QScrollBar:horizontal {
    background: transparent;
    height: 8px;
    margin: 0px;
}
QScrollBar::handle:horizontal {
    background: #3d3f52;
    border-radius: 4px;
    min-width: 24px;
}
QScrollBar::handle:horizontal:hover {
    background: #4a4d63;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0px;
    border: none;
    background: none;
}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
    background: none;
}
QWidget#titleBar {
    background-color: #16171f;
    border-bottom: 1px solid #3d3f52;
}
QLabel#titleBarText {
    color: #cfd0da;
    font-weight: bold;
    font-size: 13px;
}
QPushButton#titleBarMinBtn, QPushButton#titleBarMaxBtn, QPushButton#titleBarCloseBtn {
    background-color: transparent;
    border: none;
    border-radius: 0px;
    color: #cfd0da;
    font-weight: normal;
    font-size: 14px;
    padding: 0px;
}
QPushButton#titleBarMinBtn:hover, QPushButton#titleBarMaxBtn:hover {
    background-color: #3d3f52;
}
QPushButton#titleBarCloseBtn:hover {
    background-color: #e0454b;
    color: #ffffff;
}
/* 링크 미리보기 - 채팅 말풍선 안에 들어가는 작은 카드.
   면색을 채팅 배경(#16171f)보다 한 단계 밝게 둬서 "메시지에 딸린 것"으로 보이게 함 */
QFrame#linkCard {
    background-color: #22232e;
    border: 1px solid #3d3f52;
    border-radius: 8px;
}
QFrame#linkCard:hover {
    border: 1px solid #7c6cf0;
}
/* 카드 안 글자들은 hover 테두리 규칙을 물려받지 않게 테두리를 명시적으로 없앰 */
QLabel#linkCardTitle {
    color: #e6e6e6;
    font-weight: bold;
    border: none;
    background: transparent;
}
QLabel#linkCardDesc {
    color: #9a9cad;
    font-size: 12px;
    border: none;
    background: transparent;
}
QLabel#linkCardHost {
    color: #6e7185;
    font-size: 11px;
    border: none;
    background: transparent;
}
QLabel#linkCardThumb {
    background-color: #16171f;
    border: none;
    border-radius: 6px;
}
QLabel#linkImagePreview {
    background: transparent;
    border: 1px solid #3d3f52;
    border-radius: 8px;
}
/* 팝업(프로필 변경/채널 추가/확인창) - 테두리 색을 다른 창들과 같은 #3d3f52로 통일함.
   원래는 본창과 구분하려고 보라색을 썼는데, 팝업만 색이 튀어서 오히려 이질적이었음.
   구분은 색이 아니라 팝업 자체 배경(#22232e)이 본창(#1e1f29)보다 밝은 것으로 충분함 */
QDialog {
    background-color: #22232e;
    border: 1px solid #3d3f52;
    border-radius: 10px;
}
"""
# 문자열 전체를 f-string으로 만들면 위의 수많은 CSS 중괄호({...})와 충돌해서 위험하므로,
# TIMESTAMP_BADGE_FONT_PX 값 하나만 안전하게 후처리로 끼워넣음 - 예전엔 이 상수가 정의만
# 되고 실제로는 안 쓰여서(QSS에 7px이 리터럴로 박혀있었음) 상수를 바꿔도 배지 글자
# 크기가 안 바뀌는 죽은 코드였음
STYLE_SHEET = STYLE_SHEET.replace("__TIMESTAMP_BADGE_FONT_PX__", str(TIMESTAMP_BADGE_FONT_PX))
