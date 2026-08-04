"""공통 - 버튼/입력/카드/목록/체크박스/상태 문구/시간 배지 스타일."""

QSS = """
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
"""
