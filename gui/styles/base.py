"""공통 - 버튼/입력/카드/목록/체크박스/상태 문구/시간 배지 스타일."""

QSS = """
QWidget {
    background-color: __BG__;
    color: __TEXT__;
    font-family: "Malgun Gothic", "맑은 고딕", sans-serif;
    font-size: 14px;
}
QLineEdit {
    background-color: __BG_CONTROL__;
    border: 1px solid __LINE__;
    border-radius: 8px;
    padding: 8px;
    color: __TEXT_STRONG__;
}
QLineEdit:focus {
    border: 1px solid __ACCENT__;
}
QPushButton {
    background-color: __ACCENT__;
    border: none;
    border-radius: 8px;
    padding: 10px 16px;
    color: white;
    font-weight: bold;
}
QPushButton:hover {
    background-color: __ACCENT_HOVER__;
}
QPushButton:pressed {
    background-color: __ACCENT_PRESSED__;
}
QPushButton#secondary {
    background-color: __LINE__;
}
QPushButton#secondary:hover {
    background-color: __LINE_HOVER__;
}
/* --- 공통 디자인 토큰 ---
   테두리색: 기본 __LINE__ / 강조(포커스·팝업) __ACCENT__
   면색: 기본 __BG__, 가라앉은 영역 __BG_SUNKEN__, 떠 있는 컨트롤 __BG_CONTROL__
   모서리: 컨테이너 10px, 컨트롤 8px, 작은 요소 6px
   위젯마다 제각각이던 값을 이 규칙으로 통일함 */
QFrame#card {
    background-color: __BG_CARD__;
    border: 1px solid __LINE__;
    border-radius: 10px;
    padding: 18px;
}
QScrollArea {
    background-color: __BG_SUNKEN__;
    border: 1px solid __LINE__;
    border-radius: 10px;
}
/* 레이아웃 용도로만 쓰는 스크롤 영역(로그인 폼 감싸기) - 테두리/배경 없이 투명하게 */
QScrollArea#plainScroll, QScrollArea#plainScroll > QWidget > QWidget {
    background: transparent;
    border: none;
}
QListWidget {
    background-color: __BG_SUNKEN__;
    border: 1px solid __LINE__;
    border-radius: 10px;
    padding: 4px;
}
QListWidget::item {
    padding: 4px 6px;
    border-radius: 6px;
}
QListWidget::item:selected {
    background-color: __LINE__;
    color: __TEXT_STRONG__;
}
QComboBox {
    background-color: __BG_CONTROL__;
    border: 1px solid __LINE__;
    border-radius: 8px;
    padding: 7px 10px;
    color: __TEXT_STRONG__;
}
QComboBox:hover {
    border: 1px solid __LINE_HOVER__;
}
QComboBox:focus {
    border: 1px solid __ACCENT__;
}
QComboBox::drop-down {
    border: none;
    width: 22px;
}
QComboBox QAbstractItemView {
    background-color: __BG_CARD__;
    border: 1px solid __LINE__;
    border-radius: 8px;
    selection-background-color: __ACCENT__;
    selection-color: __TEXT_STRONG__;
    outline: none;
    padding: 4px;
}
QCheckBox {
    spacing: 8px;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid __LINE__;
    border-radius: 4px;
    background-color: __BG_CONTROL__;
}
QCheckBox::indicator:hover {
    border: 1px solid __ACCENT__;
}
QCheckBox::indicator:checked {
    background-color: __ACCENT__;
    border: 1px solid __ACCENT__;
}
/* 위 항목이 꺼져서 못 고르는 상태 - 숨기지 않고 짙은 회색으로 흐린다.
   숨겨버리면 그런 설정이 있다는 것 자체를 모르게 된다 */
QCheckBox:disabled, QRadioButton:disabled, QLabel#hint:disabled {
    color: __TEXT_DISABLED__;
}
QCheckBox::indicator:disabled, QRadioButton::indicator:disabled {
    border: 1px solid __LINE_DISABLED__;
    background-color: __BG__;
}
/* 라디오는 체크박스와 같은 모양새로 두되 동그라미로 - 하나만 고르는 것임이 보이게 */
QRadioButton {
    spacing: 8px;
}
QRadioButton::indicator {
    width: 14px;
    height: 14px;
    border: 1px solid __LINE__;
    border-radius: 8px;
    background-color: __BG_CONTROL__;
}
QRadioButton::indicator:hover {
    border: 1px solid __ACCENT__;
}
QRadioButton::indicator:checked {
    background-color: __ACCENT__;
    border: 4px solid __BG_CONTROL__;
}
/* 체크/선택된 상태여도 못 고르는 중이면 강조색이 남으면 안 된다. 순서 주의 - QSS는
   나중에 나온 규칙이 이기므로 이 두 줄이 위의 checked 규칙보다 뒤에 있어야 한다 */
QCheckBox::indicator:checked:disabled {
    background-color: __LINE_DISABLED__;
    border: 1px solid __LINE_DISABLED__;
}
QRadioButton::indicator:checked:disabled {
    background-color: __TEXT_DISABLED__;
    border: 4px solid __BG__;
}
QLabel#title {
    font-size: 20px;
    font-weight: bold;
    padding-bottom: 8px;
}
QLabel#hint {
    color: __TEXT_DIM__;
    font-size: 12px;
}
QLabel#startupTitle {
    font-size: 26px;
    font-weight: bold;
    color: __TEXT_STRONG__;
}
QProgressBar {
    background-color: __BG_CONTROL__;
    border: 1px solid __LINE__;
    border-radius: 6px;
    height: 8px;
}
QProgressBar::chunk {
    background-color: __ACCENT__;
    border-radius: 5px;
}
QLabel#status_err {
    color: __DANGER__;
}
/* 오류가 아닌 진행/안내 문구 - 서버가 보내는 접속 안내나 "연결 중..." 같은 것들.
   이것까지 빨갛게 보여주면 아무 문제 없는데도 오류가 난 것처럼 보임 */
QLabel#status_info {
    color: __TEXT_DIM__;
}
/* font-size 값은 TIMESTAMP_BADGE_FONT_PX 상수와 반드시 일치시킬 것 (아래에서 .replace()로 실제로 대입함) */
QLabel#timestampBadge {
    background-color: rgba(154, 156, 173, 100);
    color: __TEXT_MUTED__;
    font-size: __TIMESTAMP_BADGE_FONT_PX__px;
    border-radius: 7px;
    padding: 0px 7px;
}
"""
