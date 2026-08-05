"""링크 미리보기 카드 스타일."""

QSS = """
/* 링크 미리보기 - 채팅 말풍선 안에 들어가는 작은 카드.
   면색을 채팅 배경(__BG_SUNKEN__)보다 한 단계 밝게 둬서 "메시지에 딸린 것"으로 보이게 함 */
QFrame#linkCard {
    background-color: __BG_CARD__;
    border: 1px solid __LINE__;
    border-radius: 8px;
}
QFrame#linkCard:hover {
    border: 1px solid __ACCENT__;
}
/* 카드 안 글자들은 hover 테두리 규칙을 물려받지 않게 테두리를 명시적으로 없앰 */
QLabel#linkCardTitle {
    color: __TEXT__;
    font-weight: bold;
    border: none;
    background: transparent;
}
QLabel#linkCardDesc {
    color: __TEXT_DIM__;
    font-size: 12px;
    border: none;
    background: transparent;
}
QLabel#linkCardHost {
    color: __TEXT_PLACEHOLDER__;
    font-size: 11px;
    border: none;
    background: transparent;
}
QLabel#linkCardThumb {
    background-color: __BG_SUNKEN__;
    border: none;
    border-radius: 6px;
}
QLabel#linkImagePreview {
    background: transparent;
    border: 1px solid __LINE__;
    border-radius: 8px;
}
"""
