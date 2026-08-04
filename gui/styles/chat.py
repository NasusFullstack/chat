"""채팅 - 채널 이름 헤더, 대화 로그 카드 스타일."""

QSS = """
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
"""
