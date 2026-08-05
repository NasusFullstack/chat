"""화면 스타일(QSS)을 영역별로 나눠둔 곳.

예전엔 theme.py 안에 476줄짜리 문자열 하나였다. 어느 규칙이 어느 화면 것인지 알려면 전부
훑어야 했고, 규칙을 고칠 때 엉뚱한 화면이 같이 바뀌는지도 알기 어려웠다.

파일을 나눴을 뿐 **합쳐진 결과는 예전과 글자 하나까지 같다**(실제로 비교해서 확인함).
순서를 바꾸면 안 된다 - QSS는 나중에 나온 규칙이 앞을 덮으므로 순서가 곧 의미다.

색은 여기 직접 쓰지 않고 `__ACCENT__`처럼 이름으로 적는다. 실제 색은 palette.py가 정하고,
테마를 바꾸면 그 색표만 갈아끼우면 된다(QSS는 안 건드림).
"""
from gui.styles import base, chat, dialogs, emoji, preview, sidebar, tabs, toast
from gui.styles.palette import DEFAULT_THEME, colors

# 순서 중요: 뒤에 오는 규칙이 앞을 덮는다. 예전 theme.py에 있던 순서 그대로다
SECTIONS = (base.QSS, tabs.QSS, sidebar.QSS, emoji.QSS, chat.QSS, preview.QSS,
            dialogs.QSS, toast.QSS)

_NEWLINE = "\n"


def build_stylesheet(timestamp_badge_font_px: int, theme: str = DEFAULT_THEME) -> str:
    """영역별 조각을 이어 붙여 앱 전체 스타일시트를 만든다.

    조각 사이에 빈 줄이 끼지 않게 앞뒤 줄바꿈을 정리한 뒤 이어 붙인다.

    시간 배지 글자 크기만 후처리로 끼워넣는 이유: 문자열 전체를 f-string으로 만들면 수많은
    CSS 중괄호({...})와 충돌한다. 예전엔 이 상수가 정의만 되고 QSS에는 7px이 리터럴로
    박혀 있어서, 상수를 바꿔도 배지 크기가 안 바뀌는 죽은 코드였다.
    """
    joined = _NEWLINE.join(section.strip(_NEWLINE) for section in SECTIONS)
    sheet = (_NEWLINE + joined + _NEWLINE).replace(
        "__TIMESTAMP_BADGE_FONT_PX__", str(timestamp_badge_font_px))
    # 색 이름을 실제 색으로 바꾼다. 테마를 바꾸면 여기서 다른 색표가 들어온다
    for name, value in colors(theme).items():
        sheet = sheet.replace(f"__{name}__", value)
    return sheet
