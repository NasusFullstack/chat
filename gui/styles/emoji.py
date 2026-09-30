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
/* 올리는 중에만 보이는 줄 */
QWidget#uploadBar {
    background: __BG_CELL__;
    border: 1px solid __LINE_SOFTER__;
    border-radius: 8px;
}
QLabel#uploadBarName { color: __TEXT_STRONG__; background: transparent; }
QLabel#uploadBarPercent { color: __TEXT_SOFT__; background: transparent; }
QProgressBar#uploadBarProgress {
    background: __BG_CONTROL_ALT__;
    border: none;
    border-radius: 4px;
}
QProgressBar#uploadBarProgress::chunk {
    background: __ACCENT__;
    border-radius: 4px;
}
QPushButton#uploadBarCancel {
    background: transparent;
    color: __TEXT_SOFT__;
    border: 1px solid __LINE_CONTROL__;
    border-radius: 7px;
    padding: 2px 10px;
}
QPushButton#uploadBarCancel:hover { color: __TEXT_STRONG__; background: __BG_HOVER_SOFT__; }
/* 채팅에 뜬 파일 카드 - 무엇인지 보고 누르게 */
QWidget#fileCard {
    background: __BG_CELL__;
    border: 1px solid __LINE_SOFTER__;
    border-radius: 10px;
}
QLabel#fileCardIcon {
    font-size: 22px;
    background: transparent;
}
QLabel#fileCardName {
    color: __TEXT_STRONG__;
    font-weight: bold;
    background: transparent;
}
QLabel#fileCardInfo {
    color: __TEXT_SOFT__;
    font-size: 11px;
    background: transparent;
}
/* 버튼은 눈에 덜 띄게 - 먼저 보여야 하는 건 파일 이름이다 */
QPushButton#fileCardBtn, QPushButton#fileCardDropBtn {
    background: transparent;
    color: __TEXT_MUTED__;
    border: none;
    padding: 2px 4px;
    font-size: 11px;
    text-align: right;
}
QPushButton#fileCardBtn:hover, QPushButton#fileCardDropBtn:hover {
    color: __TEXT_STRONG__;
    text-decoration: underline;
}
QPushButton#fileCardDropBtn {
    color: __TEXT_DIMMER__;
}
QPushButton#fileCardBtn:disabled, QPushButton#fileCardDropBtn:disabled {
    color: __TEXT_DIM__;
    text-decoration: none;
}
/* 두 칸 고르기 - 내 보관함 / 다 같이 쓰는 것. 고른 쪽이 눌린 것처럼 보여야 한다 */
QPushButton#emojiTabBtn {
    background: transparent;
    color: __TEXT_SOFT__;
    border: 1px solid transparent;
    border-radius: 8px;
    padding: 6px 4px;
}
QPushButton#emojiTabBtn:hover {
    background: __BG_HOVER_SOFT__;
    color: __TEXT_STRONG__;
}
QPushButton#emojiTabBtn:checked {
    background: __BG_CONTROL_ALT__;
    color: __TEXT_STRONG__;
    border: 1px solid __LINE_CONTROL__;
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
