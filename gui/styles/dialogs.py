"""팝업 창(프로필 변경/채널 추가/확인창) 스타일."""

QSS = """
/* 팝업(프로필 변경/채널 추가/확인창) - 테두리 색을 다른 창들과 같은 __LINE__로 통일함.
   원래는 본창과 구분하려고 보라색을 썼는데, 팝업만 색이 튀어서 오히려 이질적이었음.
   구분은 색이 아니라 팝업 자체 배경(__BG_CARD__)이 본창(__BG__)보다 밝은 것으로 충분함 */
QDialog {
    background-color: __BG_CARD__;
    border: 1px solid __LINE__;
    border-radius: 10px;
}

/* --- 환경설정 창 --- */
QFrame#settingsDivider {
    border: none;
    border-top: 1px solid __LINE_SOFT__;
    max-height: 1px;
}
/* 설정 탭은 채널 탭과 달리 아래 여백이 필요 없다(바로 밑에 내용이 붙음) */
QTabWidget#settingsTabs > QTabBar::tab {
    margin-bottom: 0px;
    padding: 6px 14px;
}
QLabel#infoTitle {
    font-size: 17px;
    font-weight: bold;
    color: __TEXT_STRONG__;
}
QLabel#infoVersion {
    color: __TEXT_DIM__;
    font-size: 12px;
}
QLabel#infoKey {
    color: __TEXT_DIM__;
    font-size: 12px;
}
QLabel#infoValue {
    color: __TEXT_SOFT__;
    font-size: 12px;
}
QLabel#infoCopyright {
    color: __TEXT_FAINT__;
    font-size: 11px;
    padding-top: 6px;
}
"""