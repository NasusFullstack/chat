"""IRC가 글자를 꾸미는 방식(mIRC 규약)을 화면에 그대로 그려준다.

왜 필요한가: IRC에서는 색과 굵게를 **보이지 않는 제어문자**로 표시한다.
`\\x03` 뒤에 숫자가 색, `\\x02`가 굵게, `\\x0f`가 원래대로다. 이걸 모르는 채로 글자를
그대로 뿌리면 제어문자는 안 보이고 **숫자만 남는다.**

실제로 그랬다(2026-08-13). PDLab 서버의 환영 인사가 이렇게 보였다:

    * [#pdlab] 11⟦ PDLab. IRC ⟧ 환영합니다!

앞의 `11`은 "색 11번"이라는 뜻인데 그게 글자로 튀어나온 것이다. 다른 IRC 클라이언트에서는
색이 입혀진 안내문으로 예쁘게 보이는 줄이, 우리 앱에서만 오류 문구처럼 보였다.

두 가지를 제공한다.
- `to_html()`  꾸밈을 실제 색/굵게로 바꾼다(대화창처럼 서식을 쓸 수 있는 곳)
- `strip()`    꾸밈을 걷어내고 글자만 남긴다(알림 팝업, 상태줄처럼 서식이 없는 곳)
"""
import re

# mIRC 16색. 어두운 배경에서 읽히도록 고른 값이다 - 규약의 원래 색(검정 등)을 그대로 쓰면
# 배경과 같아져서 글자가 사라진다(안 보이는 글자가 되느니 밝은 회색이 낫다)
PALETTE = {
    0: "#ffffff", 1: "#c8ccd8", 2: "#5b7cfa", 3: "#3fbf6f", 4: "#ff6b61",
    5: "#c2703f", 6: "#b07ce8", 7: "#e0902f", 8: "#ffd75f", 9: "#6fdc6f",
    10: "#2fb5b5", 11: "#63d7d7", 12: "#7aa7ff", 13: "#ff87d7", 14: "#9a9cad",
    15: "#c8ccd8",
}

BOLD = "\x02"
ITALIC = "\x1d"
UNDERLINE = "\x1f"
COLOR = "\x03"
HEX_COLOR = "\x04"
REVERSE = "\x16"
RESET = "\x0f"

# 색 지정: \x03[글자색][,배경색] - 숫자는 한두 자리, 없으면 색을 원래대로
_COLOR_RE = re.compile(r"\x03(\d{1,2})?(?:,(\d{1,2}))?")
# 16진수 색(\x04RRGGBB)을 쓰는 서버도 있다
_HEX_RE = re.compile(r"\x04([0-9a-fA-F]{6})?")
_ALL_CODES_RE = re.compile(r"[\x02\x1d\x1f\x16\x0f]|\x03(\d{1,2})?(?:,(\d{1,2}))?"
                           r"|\x04[0-9a-fA-F]{6}?")


def strip(text: str) -> str:
    """꾸밈을 걷어내고 글자만 남긴다(서식을 쓸 수 없는 자리용)."""
    return _ALL_CODES_RE.sub("", text or "")


def has_formatting(text: str) -> bool:
    return bool(text) and any(code in text for code in
                              (BOLD, ITALIC, UNDERLINE, COLOR, HEX_COLOR, REVERSE, RESET))


def to_html(escaped_text: str) -> str:
    """`<`, `>`가 이미 이스케이프된 글자를 받아 꾸밈을 HTML로 바꾼다.

    이스케이프를 여기서 하지 않는 이유: 부르는 쪽이 이미 이스케이프한 뒤 링크까지
    붙이는 순서라, 여기서 또 하면 `&lt;`가 `&amp;lt;`가 된다.
    """
    if not escaped_text:
        return ""
    if not has_formatting(escaped_text):
        return escaped_text

    out = []
    state = {"color": "", "bold": False, "italic": False, "underline": False}
    open_span = False

    def close():
        """열어둔 span을 닫는다. 안에 글자가 하나도 안 들어갔으면 통째로 지운다.

        색 지정이 연달아 나오면(색 -> 굵게) 빈 span이 남는데, 눈에는 안 보여도
        HTML이 지저분해지고 나중에 글자 수를 세는 곳에서 헷갈린다.
        """
        nonlocal open_span
        if not open_span:
            return
        if out and out[-1].startswith("<span "):
            out.pop()
        else:
            out.append("</span>")
        open_span = False

    def open_new():
        nonlocal open_span
        styles = []
        if state["color"]:
            styles.append(f"color:{state['color']}")
        if state["bold"]:
            styles.append("font-weight:bold")
        if state["italic"]:
            styles.append("font-style:italic")
        if state["underline"]:
            styles.append("text-decoration:underline")
        if styles:
            out.append('<span style="' + ";".join(styles) + '">')
            open_span = True

    def restyle():
        close()
        open_new()

    index = 0
    length = len(escaped_text)
    while index < length:
        char = escaped_text[index]
        if char == COLOR:
            match = _COLOR_RE.match(escaped_text, index)
            number = match.group(1)
            state["color"] = PALETTE.get(int(number) % 16, "") if number else ""
            index = match.end()
            restyle()
            continue
        if char == HEX_COLOR:
            match = _HEX_RE.match(escaped_text, index)
            state["color"] = f"#{match.group(1)}" if match.group(1) else ""
            index = match.end()
            restyle()
            continue
        if char in (BOLD, ITALIC, UNDERLINE):
            key = {BOLD: "bold", ITALIC: "italic", UNDERLINE: "underline"}[char]
            state[key] = not state[key]
            index += 1
            restyle()
            continue
        if char == RESET:
            state.update(color="", bold=False, italic=False, underline=False)
            index += 1
            close()
            continue
        if char == REVERSE:      # 배경/글자 뒤집기 - 배경색을 안 쓰므로 무시한다
            index += 1
            continue
        out.append(char)
        index += 1

    close()
    return "".join(out)
