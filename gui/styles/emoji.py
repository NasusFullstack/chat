"""이모티콘 - 입력창 옆 버튼과 보관함 창 스타일."""

QSS = """
/* 입력창 왼쪽의 이모티콘 보관함 버튼 - 웃는 얼굴만 있는 정사각형 */
QPushButton#emojiBtn {
    background: __BG_CONTROL_ALT__;
    color: __TEXT_SOFT__;
    border: 1px solid __LINE_CONTROL__;
    border-radius: 8px;
    padding: 0px;
}
QPushButton#emojiAddBtn {
    background: __BG_CONTROL_ALT__;
    color: __TEXT_SOFT__;
    border: 1px solid __LINE_CONTROL__;
    border-radius: 8px;
    padding: 5px 10px;
}
QPushButton#emojiAddBtn:hover {
    background: __BG_HOVER_SOFT__;
    color: __TEXT_STRONG__;
}
QPushButton#emojiBtn:hover {
    background: __BG_HOVER_SOFT__;
    color: __TEXT_STRONG__;
}
/* 이모티콘 보관함 창 */
QWidget#emojiCell {
    background: __BG_CELL__;
    border: 1px solid __LINE_SOFTER__;
    border-radius: 8px;
}
QWidget#emojiCell:hover {
    border: 1px solid __ACCENT_SOFT__;
}
QLabel#emojiName {
    color: __TEXT_DIM__;
    font-size: 11px;
    background: transparent;
}
QLabel#emojiEmpty {
    color: __TEXT_DIMMER__;
    background: transparent;
}
QLabel#emojiPageLabel {
    color: __TEXT_SOFT__;
    background: transparent;
}
QPushButton#emojiNavBtn {
    background: __BG_CONTROL_ALT__;
    color: __TEXT_SOFT__;
    border: 1px solid __LINE_CONTROL__;
    border-radius: 6px;
    padding: 4px 0px;
}
QPushButton#emojiNavBtn:disabled {
    color: __TEXT_DISABLED__;
    border: 1px solid __LINE_DISABLED__;
}
"""
