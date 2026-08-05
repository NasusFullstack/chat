"""테마 - 화면에 쓰는 색을 이름으로 모아둔 곳.

예전에는 색이 QSS 여기저기에 16진수로 흩어져 있었다(서로 다른 색 32개, 129번 사용).
"강조색을 바꾸자"는 한마디에 파일 일곱 개를 뒤져야 했고, 어떤 색이 같은 뜻으로 쓰인
것인지도 구분이 안 됐다.

지금은 QSS가 `__이름__` 자리표시자를 쓰고, 그 이름의 실제 색을 여기서 정한다.
**테마를 하나 더 만들려면 아래 THEMES에 색표 하나를 추가하면 된다** - QSS는 안 건드린다.

이름은 '무슨 색인가'가 아니라 **'어떤 역할인가'**로 짓는다. `PURPLE`이 아니라 `ACCENT`인
이유는, 나중에 파란 테마를 만들 때 `PURPLE = "#3b82f6"` 같은 우스운 코드가 되지 않게
하기 위함이다.
"""

# 지금 쓰는 기본 테마. 값은 예전 QSS에 박혀 있던 것을 그대로 옮긴 것이라 화면이 안 바뀐다
DARK = {
    # --- 바탕 ---
    "BG": "#1e1f29",              # 창 전체 바탕
    "BG_SUNKEN": "#16171f",       # 가라앉은 영역(대화 로그, 참여자 목록)
    "BG_CARD": "#22232e",         # 떠 있는 카드/팝업
    "BG_CONTROL": "#2a2b38",      # 입력창 같은 컨트롤
    "BG_CONTROL_ALT": "#2b2d3a",  # 보조 버튼(이모티콘/화살표)
    "BG_ITEM": "#23242f",         # 목록 항목(채널 알약, 탭)
    "BG_ITEM_HOVER": "#2f3140",   # 항목에 마우스 올렸을 때
    "BG_CELL": "#24262f",         # 이모티콘 보관함 칸
    "BG_HOVER_SOFT": "#343747",   # 보조 버튼에 마우스 올렸을 때

    # --- 테두리 ---
    "LINE": "#3d3f52",            # 기본 테두리
    "LINE_SOFT": "#34364a",       # 옅은 테두리(항목)
    "LINE_SOFTER": "#33364a",     # 더 옅은 테두리(보관함 칸)
    "LINE_CONTROL": "#3a3d4e",    # 컨트롤 테두리
    "LINE_HOVER": "#4a4d63",      # 마우스 올렸을 때
    "LINE_DIVIDER": "#2b2d3a",    # 구분선(사이드바 아래)
    "LINE_DISABLED": "#2f3242",   # 못 누르는 버튼

    # --- 강조(브랜드) ---
    "ACCENT": "#7c6cf0",          # 강조색 - 선택/포커스/주 버튼
    "ACCENT_HOVER": "#6a5be0",
    "ACCENT_PRESSED": "#5a4bd0",
    "ACCENT_DEEP": "#5b52d9",     # 선택된 채널 면색
    "ACCENT_MUTED": "#3a3560",    # 선택된 탭 면색
    "ACCENT_SOFT": "#6c5ce7",     # 보관함 칸 hover 테두리

    # --- 글자 ---
    "TEXT": "#e6e6e6",            # 본문
    "TEXT_STRONG": "#ffffff",     # 강조된 글자
    "TEXT_MUTED": "#cfd0da",      # 조금 옅은 글자
    "TEXT_SOFT": "#c8cad8",       # 보조 글자
    "TEXT_DIM": "#9a9cad",        # 안내/설명
    "TEXT_DIMMER": "#7f8296",     # 더 옅은 안내
    "TEXT_FAINT": "#62657a",      # 저작권 등 거의 안 보여도 되는 글자
    "TEXT_DISABLED": "#55586a",   # 못 누르는 버튼 글자
    "TEXT_PLACEHOLDER": "#6e7185",

    # --- 상태 ---
    "DANGER": "#ff6b6b",          # 오류 문구
    "DANGER_STRONG": "#e0454b",   # 닫기 버튼 hover
}

THEMES = {"dark": DARK}
DEFAULT_THEME = "dark"

# 환경설정에서 고를 때 보여줄 이름. 테마를 추가하면 THEMES와 여기 한 줄씩만 늘어난다
THEME_LABELS = {"dark": "기본 (다크)"}


def theme_choices() -> list[tuple[str, str]]:
    """(테마 키, 사람이 읽을 이름) 목록. 기본 테마가 항상 맨 앞."""
    keys = [DEFAULT_THEME] + [k for k in THEMES if k != DEFAULT_THEME]
    return [(k, THEME_LABELS.get(k, k)) for k in keys]


def colors(name: str = DEFAULT_THEME) -> dict:
    return THEMES.get(name, DARK)
