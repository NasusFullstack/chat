import os as _os
import sys as _sys

_HERE = _os.path.dirname(_os.path.abspath(__file__))
_REPO = _os.path.dirname(_HERE)
import os, sys
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, _REPO)
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
import gui_client as g

app = QApplication(sys.argv)
app.setStyleSheet(g.STYLE_SHEET)

checks = []

# ---- _linkify 단위 테스트 ----
checks.append(("http URL이 <a href>로 감싸짐",
               '<a href="http://example.com"' in g._linkify("check http://example.com out")))
checks.append(("https URL도 인식됨",
               '<a href="https://example.com/path?x=1"' in g._linkify("https://example.com/path?x=1")))
checks.append(("www.만 있어도 http:// 붙여서 링크로 만듦",
               '<a href="http://www.example.com"' in g._linkify("가봐 www.example.com 좋아")))
checks.append(("URL 표시 텍스트 자체는 원문 그대로",
               ">www.example.com</a>" in g._linkify("가봐 www.example.com 좋아")))
checks.append(("문장 끝 마침표/괄호는 링크에서 제외됨",
               '<a href="http://example.com">http://example.com</a>.' in g._linkify("(http://example.com).").replace("(", "").replace(")", "", 0) or
               '</a>.' in g._linkify("http://example.com.")))
checks.append(("URL 없는 일반 텍스트는 그대로", g._linkify("그냥 평범한 메시지") == "그냥 평범한 메시지"))
checks.append(("URL 두 개 이상도 각각 링크로 변환됨",
               g._linkify("http://a.com http://b.com").count("<a href=") == 2))

# ---- MessageWidget 통합: 링크 렌더링 + 텍스트 선택 가능 ----
avatar = g._hashed_avatar_pixmap("tester")
msg = g.MessageWidget("alice", "여기 봐 https://example.com/foo 링크야", False, 0, avatar)
# 글자는 이제 텍스트 엔진 위젯이 그린다(gui/components/message_text.py).
# 무엇으로 그리는지가 아니라 "링크가 살아 있는가"를 본다
body = msg._text_label
checks.append(("MessageWidget 안에서 URL이 링크로 렌더링됨",
               'href="https://example.com/foo"' in body.toHtml()))
checks.append(("보이는 글자에는 태그가 안 섞임",
               "<a href=" not in body.text() and "example.com/foo" in body.text()))
flags = body.textInteractionFlags()
checks.append(("텍스트를 마우스로 드래그해서 선택 가능(복사 가능)",
               bool(flags & Qt.TextInteractionFlag.TextSelectableByMouse)))
checks.append(("링크를 마우스로 클릭 가능",
               bool(flags & Qt.TextInteractionFlag.LinksAccessibleByMouse)))
checks.append(("링크 클릭 시 외부 브라우저로 열림", body.openExternalLinks() is True))

print("\n=== 검증 결과 (URL 하이퍼링크 + 채팅 텍스트 드래그 선택) ===")
all_ok = True
for name, ok in checks:
    print(f"[{'OK' if ok else 'FAIL'}] {name}")
    all_ok = all_ok and ok
print("전체 통과:", all_ok)
