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
/* font-size 값은 TIMESTAMP_BADGE_FONT_PX 상수와 반드시 일치시킬 것 (아래에서 .replace()로 실제로 대입함) */
QLabel#timestampBadge {
    background-color: rgba(154, 156, 173, 100);
    color: #cfd0da;
    font-size: __TIMESTAMP_BADGE_FONT_PX__px;
    border-radius: 7px;
    padding: 0px 7px;
}
/* 탭 아래 본문(pane)과 선택된 탭이 같은 면색(#16171f)이라 하나로 이어져 보이게 함 -
   예전엔 pane 모서리(8px)와 탭 모서리(6px)가 달라 살짝 어긋나 보였음 */
QTabWidget::pane {
    background-color: #16171f;
    border: 1px solid #3d3f52;
    border-top-left-radius: 0px;
    border-top-right-radius: 10px;
    border-bottom-left-radius: 10px;
    border-bottom-right-radius: 10px;
    top: -1px;
}
QTabBar::tab {
    background-color: #22232e;
    color: #9a9cad;
    padding: 7px 14px;
    border: 1px solid #3d3f52;
    border-bottom: none;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    margin-right: 2px;
}
QTabBar::tab:selected {
    background-color: #16171f;
    color: #ffffff;
}
QTabBar::tab:hover:!selected {
    background-color: #2f3140;
    color: #cfd0da;
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
/* 팝업(프로필 변경/채널 추가/확인창)은 뒤에 있는 본창과 색이 같아 경계가 안 보이던
   문제가 있어서, 유일하게 강조색 테두리를 씀 - 컨테이너 모서리(10px)로 통일 */
QDialog {
    border: 1px solid #7c6cf0;
    border-radius: 10px;
}
"""
# 문자열 전체를 f-string으로 만들면 위의 수많은 CSS 중괄호({...})와 충돌해서 위험하므로,
# TIMESTAMP_BADGE_FONT_PX 값 하나만 안전하게 후처리로 끼워넣음 - 예전엔 이 상수가 정의만
# 되고 실제로는 안 쓰여서(QSS에 7px이 리터럴로 박혀있었음) 상수를 바꿔도 배지 글자
# 크기가 안 바뀌는 죽은 코드였음
STYLE_SHEET = STYLE_SHEET.replace("__TIMESTAMP_BADGE_FONT_PX__", str(TIMESTAMP_BADGE_FONT_PX))
