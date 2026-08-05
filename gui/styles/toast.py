"""새 메시지 알림 팝업 스타일.

**앱 본체와 같은 스타일시트를 쓴다.** 알림만 다른 색을 쓰면 딴 앱에서 온 것처럼 보이고,
나중에 테마를 갈아끼울 때 여기만 빠져 어긋난다. 색은 아래 규칙(gui/styles/base.py의
디자인 토큰)과 같은 값을 쓴다:
  면색 __BG_CARD__(떠 있는 카드) / 강조 테두리 __ACCENT__ / 본문 글자 __TEXT_SOFT__

테마를 추가한다면 이 파일의 값만 바꾸면 알림까지 같이 따라온다.
"""

QSS = """
/* 새 메시지 알림 팝업 - 오른쪽 아래에 잠깐 떴다 사라지는 우리 창 */
QWidget#toast {
    background-color: __BG_CARD__;
    border: 1px solid __ACCENT__;
    border-radius: 10px;
}
QLabel#toastTitle {
    color: __TEXT_STRONG__;
    font-size: 13px;
    font-weight: bold;
    background: transparent;
}
QLabel#toastBody {
    color: __TEXT_SOFT__;
    font-size: 12px;
    background: transparent;
}
QLabel#toastIcon {
    background: transparent;
}
"""
