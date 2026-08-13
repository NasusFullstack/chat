"""IRC가 색/굵게를 표시하는 제어문자를 화면에 제대로 그리는가.

실제 신고(2026-08-13): PDLab 서버의 환영 인사가 우리 앱에서만 이렇게 보였다.

    * [#pdlab] 11⟦ PDLab. IRC ⟧ 환영합니다!

앞의 `11`은 "색 11번"이라는 뜻의 제어문자(`\\x03` 뒤 숫자)인데, 그걸 모르고 그대로
뿌려서 숫자만 글자로 튀어나왔다. 다른 IRC 클라이언트에서는 색이 입혀진 안내로 보이는
줄이라, 우리 앱만 오류 문구처럼 허접해 보였다.

여기서 확인하는 것:
1. 색/굵게가 실제 색과 굵기로 바뀌는가(대화창처럼 서식을 쓸 수 있는 곳)
2. 제어문자가 글자로 새어나오지 않는가 - 이번 사고의 핵심
3. 서식을 못 쓰는 자리(알림 팝업, 로그인 상태줄)에서는 깔끔히 걷어내는가
"""
import os as _os
import sys as _sys

_HERE = _os.path.dirname(_os.path.abspath(__file__))
_REPO = _os.path.dirname(_HERE)

_os.environ["QT_QPA_PLATFORM"] = "offscreen"
_sys.path.insert(0, _REPO)

from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])

from gui import irc_format  # noqa: E402
from gui.components.message_item import _build_system_label  # noqa: E402

checks = []


def check(name, ok, detail=""):
    checks.append((name, ok, detail))


# 실제로 서버가 보낸 줄(로그에서 그대로 가져옴)
WELCOME = "[#pdlab] \x0311\x02⟦ PDLab. IRC ⟧\x0f 환영합니다!"
MENU = "[#pdlab] \x0310▸\x0f \x02메인 채널\x0f #pdlab    \x0310▸\x0f \x02문의\x0f @hjsong"

html = _build_system_label(WELCOME).text()

# ---------- 1) 제어문자가 글자로 새지 않는가 ----------
leaked = [code for code in ("\x02", "\x03", "\x0f", "\x1d", "\x1f") if code in html]
check(f"제어문자가 화면 글자에 남지 않는다({leaked})", not leaked, leaked)
check("색 번호가 글자로 튀어나오지 않는다('11⟦'이 아니라 '⟦')",
      "11⟦" not in html and "⟦ PDLab. IRC ⟧" in html, html[:160])

# ---------- 2) 색과 굵게가 실제로 적용되는가 ----------
check(f"색이 입혀진다({irc_format.PALETTE[11]})", irc_format.PALETTE[11] in html, html[:160])
check("굵게가 적용된다", "font-weight:bold" in html, html[:160])

menu_html = _build_system_label(MENU).text()
check("여러 번 꾸민 줄도 그대로 그려진다",
      irc_format.PALETTE[10] in menu_html and "메인 채널" in menu_html, menu_html[:200])

# ---------- 3) 우리가 만든 안내는 예전 그대로 ----------
plain = _build_system_label("#pdlab 채널에 입장했습니다.").text()
check("꾸밈 없는 우리 안내문은 예전처럼 흐린 회색 기울임",
      "<i>* #pdlab 채널에 입장했습니다.</i>" in plain, plain)

# ---------- 4) 서식을 못 쓰는 자리에서는 걷어낸다 ----------
stripped = irc_format.strip(WELCOME)
check(f"알림/상태줄용으로 걷어낸 글자({stripped})",
      stripped == "[#pdlab] ⟦ PDLab. IRC ⟧ 환영합니다!", stripped)
check("걷어낸 글자에는 제어문자가 하나도 없다",
      not any(code in stripped for code in ("\x02", "\x03", "\x0f")), repr(stripped))

# ---------- 5) 안전 ----------
# 꾸밈을 그리느라 남의 HTML을 실행하면 안 된다(이스케이프는 부르는 쪽이 먼저 한다)
escaped = "&lt;b&gt;태그처럼 생긴 글자&lt;/b&gt;"
check("이미 이스케이프된 글자를 다시 건드리지 않는다",
      irc_format.to_html(escaped) == escaped, irc_format.to_html(escaped))
check("꾸밈이 없으면 글자를 그대로 둔다",
      irc_format.to_html("평범한 문장") == "평범한 문장")
check("빈 값도 안전하다", irc_format.to_html("") == "" and irc_format.strip("") == "")

# 색 번호가 범위를 넘어도(예: \x0399) 죽지 않아야 한다 - 서버가 뭘 보낼지 모른다
odd = irc_format.to_html("\x0399이상한 색\x0f")
check("이상한 색 번호가 와도 죽지 않는다", "이상한 색" in odd, odd)

print("=== 검증 결과 (IRC 색/굵게 표시) ===")
all_ok = True
for name, ok, *detail in checks:
    extra = f"  <- {detail[0]}" if detail and detail[0] and not ok else ""
    print(f"[{'OK' if ok else 'FAIL'}] {name}{extra}")
    all_ok = all_ok and ok
print("\n전체 통과:", all_ok)
_sys.exit(0 if all_ok else 1)
