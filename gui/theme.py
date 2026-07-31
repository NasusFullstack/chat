"""색상/크기/타이밍 상수와 전체 QSS 스타일시트.

여기 있는 이름들은 몽키패치 대상이 아니라 어디서든 자유롭게 직접 import해도 안전함
(gui_client.py의 순환참조 노트 참고 - 함수 5개만 그 규칙이 적용됨).
"""
import sys

IS_WINDOWS = sys.platform == "win32"

CONNECT_TIMEOUT_MS = 10_000
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

CHANNEL_TAB_FIXED_WIDTH = 110  # 채널 탭은 글자 수와 무관하게 항상 이 폭으로 고정
ADD_TAB_LABEL = "+"

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
QScrollArea {
    background-color: #16171f;
    border: 1px solid #3d3f52;
    border-radius: 8px;
}
QListWidget {
    background-color: #16171f;
    border: 1px solid #3d3f52;
    border-radius: 8px;
    padding: 4px;
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
QLabel#status_err {
    color: #ff6b6b;
}
/* font-size 값은 TIMESTAMP_BADGE_FONT_PX 상수와 반드시 일치시킬 것 (아래에서 .replace()로 실제로 대입함) */
QLabel#timestampBadge {
    background-color: rgba(154, 156, 173, 100);
    color: #cfd0da;
    font-size: __TIMESTAMP_BADGE_FONT_PX__px;
    border-radius: 7px;
    padding: 0px 7px;
}
QTabWidget::pane {
    border: 1px solid #3d3f52;
    border-radius: 8px;
    top: -1px;
}
QTabBar::tab {
    background-color: #2a2b38;
    color: #cfd0da;
    padding: 6px 14px;
    border: 1px solid #3d3f52;
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    margin-right: 2px;
}
QTabBar::tab:selected {
    background-color: #16171f;
    color: #ffffff;
}
QTabBar::tab:hover {
    background-color: #3d3f52;
}
/* '+' 채널 추가 탭 - 항상 마지막 탭이라는 설계상의 불변조건을 이용해 :last로 구분함
   (disabled로 구분하려 했으나 disabled 탭은 마우스 이벤트 자체를 못 받아 클릭이 아예
   안 먹혔던 문제가 있어서 enabled로 바꿈) */
QTabBar::tab:last {
    background-color: #22232e;
    color: #9a9cad;
    font-weight: bold;
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
QDialog {
    border: 1px solid #7c6cf0;
    border-radius: 8px;
}
"""
# 문자열 전체를 f-string으로 만들면 위의 수많은 CSS 중괄호({...})와 충돌해서 위험하므로,
# TIMESTAMP_BADGE_FONT_PX 값 하나만 안전하게 후처리로 끼워넣음 - 예전엔 이 상수가 정의만
# 되고 실제로는 안 쓰여서(QSS에 7px이 리터럴로 박혀있었음) 상수를 바꿔도 배지 글자
# 크기가 안 바뀌는 죽은 코드였음
STYLE_SHEET = STYLE_SHEET.replace("__TIMESTAMP_BADGE_FONT_PX__", str(TIMESTAMP_BADGE_FONT_PX))
