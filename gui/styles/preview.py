"""링크 미리보기 카드 스타일."""

QSS = """
/* 링크 미리보기 - 채팅 말풍선 안에 들어가는 작은 카드.
   면색을 채팅 배경(#16171f)보다 한 단계 밝게 둬서 "메시지에 딸린 것"으로 보이게 함 */
QFrame#linkCard {
    background-color: #22232e;
    border: 1px solid #3d3f52;
    border-radius: 8px;
}
QFrame#linkCard:hover {
    border: 1px solid #7c6cf0;
}
/* 카드 안 글자들은 hover 테두리 규칙을 물려받지 않게 테두리를 명시적으로 없앰 */
QLabel#linkCardTitle {
    color: #e6e6e6;
    font-weight: bold;
    border: none;
    background: transparent;
}
QLabel#linkCardDesc {
    color: #9a9cad;
    font-size: 12px;
    border: none;
    background: transparent;
}
QLabel#linkCardHost {
    color: #6e7185;
    font-size: 11px;
    border: none;
    background: transparent;
}
QLabel#linkCardThumb {
    background-color: #16171f;
    border: none;
    border-radius: 6px;
}
QLabel#linkImagePreview {
    background: transparent;
    border: 1px solid #3d3f52;
    border-radius: 8px;
}
"""
