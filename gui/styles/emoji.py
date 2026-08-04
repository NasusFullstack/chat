"""이모티콘 - 입력창 옆 버튼과 보관함 창 스타일."""

QSS = """
/* 입력창 왼쪽의 이모티콘 보관함 버튼 - 웃는 얼굴만 있는 정사각형 */
QPushButton#emojiBtn {
    background: #2b2d3a;
    color: #c8cad8;
    border: 1px solid #3a3d4e;
    border-radius: 8px;
    padding: 0px;
}
QPushButton#emojiAddBtn {
    background: #2b2d3a;
    color: #c8cad8;
    border: 1px solid #3a3d4e;
    border-radius: 8px;
    padding: 5px 10px;
}
QPushButton#emojiAddBtn:hover {
    background: #343747;
    color: #ffffff;
}
QPushButton#emojiBtn:hover {
    background: #343747;
    color: #ffffff;
}
/* 이모티콘 보관함 창 */
QWidget#emojiCell {
    background: #24262f;
    border: 1px solid #33364a;
    border-radius: 8px;
}
QWidget#emojiCell:hover {
    border: 1px solid #6c5ce7;
}
QLabel#emojiName {
    color: #9a9cad;
    font-size: 11px;
    background: transparent;
}
QLabel#emojiEmpty {
    color: #7f8296;
    background: transparent;
}
QLabel#emojiPageLabel {
    color: #c8cad8;
    background: transparent;
}
QPushButton#emojiNavBtn {
    background: #2b2d3a;
    color: #c8cad8;
    border: 1px solid #3a3d4e;
    border-radius: 6px;
    padding: 4px 0px;
}
QPushButton#emojiNavBtn:disabled {
    color: #55586a;
    border: 1px solid #2f3242;
}
"""
