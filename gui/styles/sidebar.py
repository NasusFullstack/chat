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
    background-color: __BG_ITEM__;
    color: __TEXT_MUTED__;
    border: 1px solid __LINE_SOFT__;
    border-radius: 10px;
    padding: 0px 12px;
    margin-bottom: 6px;
}
QListWidget#channelList::item:hover {
    background-color: __BG_ITEM_HOVER__;
    color: __TEXT_STRONG__;
}
/* 지금 보고 있는 채널 - 면색까지 강조색으로 채워 한눈에 들어오게 */
QListWidget#channelList::item:selected {
    background-color: __ACCENT_DEEP__;
    color: __TEXT_STRONG__;
    border: 1px solid __ACCENT__;
    font-weight: bold;
}
/* 채널 추가 - 마지막 채널 바로 아래에 네모 없이 '+' 기호만.
   채널 항목과 같은 폭을 차지하되 배경/테두리가 없어서 기호만 떠 있는 것처럼 보임 */
QPushButton#addChannelBtn {
    background: transparent;
    color: __TEXT_DIMMER__;
    border: none;
    font-size: 20px;
    font-weight: bold;
    padding: 0px;
}
/* 채널이 많아 자리가 모자랄 때 목록을 미는 화살표 - 배경 없이 기호만 */
QPushButton#channelScrollBtn {
    background: transparent;
    color: __TEXT_DIMMER__;
    border: none;
    font-size: 15px;
    font-weight: bold;
    padding: 0px;
}
QPushButton#channelScrollBtn:hover {
    color: __TEXT_STRONG__;
}
/* 참여자 목록 - 여섯 줄만 보이므로 넘치는 사람은 얇은 스크롤바로 내려서 본다.
   기본 스크롤바(10px)는 좁은 열에서 이름을 가려서 더 얇게 준다 */
QListWidget#memberList QScrollBar:vertical {
    width: 6px;
    background: transparent;
    margin: 0px;
}
QListWidget#memberList QScrollBar::handle:vertical {
    background: __LINE_HOVER__;
    border-radius: 3px;
    min-height: 18px;
}
QListWidget#memberList QScrollBar::handle:vertical:hover {
    background: __ACCENT__;
}
/* 만든이 표시 - 오른쪽(참여자) 열 맨 아래. 예전엔 채널 사이드바에 있었는데 그쪽은
   접을 수 있게 되면서 접으면 통째로 사라져서 옮겼다 */
QWidget#appFooter {
    background: transparent;
    border-top: 1px solid __BG_CONTROL_ALT__;
}
QLabel#footerLogo {
    background: transparent;
}
QLabel#footerTitle {
    background: transparent;
    color: __TEXT_MUTED__;
    font-size: 13px;
    font-weight: bold;
}
QLabel#footerMaker {
    background: transparent;
    font-size: 11px;
}
QLabel#footerGithub {
    background: transparent;
    font-size: 11px;
}
QLabel#footerCopyright {
    background: transparent;
    color: __TEXT_FAINT__;
    font-size: 11px;
}
"""
