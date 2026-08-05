"""탭 영역(지금은 대화 내용을 겹쳐 담는 용도로만 쓰고 탭 막대는 숨김) 스타일."""

QSS = """
/* 탭 영역에는 테두리를 두지 않음. 예전엔 pane 테두리 + 탭 테두리 + 채팅영역이 겹쳐서
   선이 끊긴 것처럼 보였음. 지금은 채팅 로그(QScrollArea#chatLog)가 참여자 목록과
   완전히 같은 카드 테두리를 갖고, 탭은 그 위에 얹히는 형태라 선이 하나로 깔끔함 */
QTabWidget::pane {
    background: transparent;
    border: none;
    top: 0px;
}
/* 탭은 사방이 닫힌 '칩' 모양으로 두고 채팅 카드와 살짝 띄움. 예전처럼 탭 아래를 열어두면
   그 아래를 지나는 카드 테두리 선과 만나 선이 끊긴 것처럼 보임.
   좌우 여백(padding)은 닫기(×) 버튼 자리를 침범하지 않도록 오른쪽을 넉넉히 둠 */
QTabBar::tab {
    background-color: __BG_ITEM__;
    color: __TEXT_DIM__;
    padding: 0px 8px 0px 12px;
    border: 1px solid __LINE_SOFT__;
    border-radius: 8px;
    margin-right: 6px;
    margin-bottom: 8px;
}
/* 선택된 탭은 테두리 색만 바꾸는 정도로는 눈에 잘 안 띄어서, 면색까지 강조색 계열로
   채워 "지금 보고 있는 채널"이 한눈에 들어오게 함 */
QTabBar::tab:selected {
    background-color: __ACCENT_MUTED__;
    color: __TEXT_STRONG__;
    border: 1px solid __ACCENT__;
    font-weight: bold;
}
QTabBar::tab:hover:!selected {
    background-color: __BG_ITEM_HOVER__;
    color: __TEXT_MUTED__;
    border: 1px solid __LINE_HOVER__;
}
"""
