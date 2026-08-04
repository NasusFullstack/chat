"""왼쪽 채널 사이드바 - 알약 목록/추가/스크롤 화살표/아래 만든이 표시 스타일."""

QSS = """
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
/* 채널이 많아 자리가 모자랄 때 목록을 미는 화살표 - 배경 없이 기호만 */
QPushButton#channelScrollBtn {
    background: transparent;
    color: #7f8296;
    border: none;
    font-size: 15px;
    font-weight: bold;
    padding: 0px;
}
QPushButton#channelScrollBtn:hover {
    color: #ffffff;
}
/* 사이드바 맨 아래 - 로고/이름/버전/만든이. 채널이 적을 때 비는 자리를 채움 */
QWidget#sidebarFooter {
    background: transparent;
    border-top: 1px solid #2b2d3a;
}
QLabel#footerLogo {
    background: transparent;
}
QLabel#footerTitle {
    background: transparent;
    color: #cfd0da;
    font-size: 13px;
    font-weight: bold;
}
QLabel#footerMaker {
    background: transparent;
    font-size: 11px;
}
QLabel#footerCopyright {
    background: transparent;
    color: #62657a;
    font-size: 11px;
}
"""
