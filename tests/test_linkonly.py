"""링크만 있는 메시지: 미리보기가 뜨면 주소 문자열을 지우고 그림/카드만 남기는지"""
import os as _os
import sys as _sys

_HERE = _os.path.dirname(_os.path.abspath(__file__))
_REPO = _os.path.dirname(_HERE)

import os, sys, threading
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, _REPO)

from http.server import BaseHTTPRequestHandler, HTTPServer
from PySide6.QtCore import QTimer, QEventLoop
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])
import gui_client as g
import link_meta
from gui.helpers import text_is_only_urls
from gui.link_preview import ImagePreview, LinkCard

SP = os.path.dirname(os.path.abspath(__file__))
fails = []


def check(label, cond, extra=""):
    print(("  OK   " if cond else "  FAIL ") + label + ("" if cond else f"  <- {extra}"))
    if not cond:
        fails.append(label)


img = QImage(600, 400, QImage.Format.Format_ARGB32)
img.fill(QColor("#3aa0e8"))
_p = os.path.join(SP, "_lo.png"); img.save(_p)
PHOTO = open(_p, "rb").read(); os.remove(_p)
NEWS = """<!doctype html><html><head><meta charset="utf-8">
<meta property="og:title" content="뉴스 제목입니다">
<meta property="og:description" content="설명입니다"></head><body></body></html>""".encode("utf-8")


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        t = {"/p.png": ("image/png", PHOTO), "/news": ("text/html; charset=utf-8", NEWS)}
        if self.path not in t:
            self.send_response(404); self.end_headers(); return
        ct, b = t[self.path]
        self.send_response(200); self.send_header("Content-Type", ct)
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)


srv = HTTPServer(("127.0.0.1", 0), H)
PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = f"http://127.0.0.1:{PORT}"
link_meta.is_safe_public_url = lambda u: u.startswith("http")

LONG = f"{BASE}/p.png"

print("[1] '링크만 있는 메시지' 판별")
check("이미지 주소 하나", text_is_only_urls(LONG))
check("주소 여러 개", text_is_only_urls(f"{LONG} {BASE}/news"))
check("앞뒤 공백 있어도", text_is_only_urls(f"  {LONG}  "))
check("문장 + 주소는 아님", not text_is_only_urls(f"이거 봐 {LONG}"))
check("주소 뒤에 말 붙으면 아님", not text_is_only_urls(f"{LONG} 어때"))
check("주소 없으면 아님", not text_is_only_urls("그냥 대화"))
check("빈 문자열은 아님", not text_is_only_urls("   "))

app.setStyleSheet(g.STYLE_SHEET)
page = g.ChatPage(on_send=lambda c, t: None, on_add_channel=lambda: None,
                  on_leave_channel=lambda c: None, on_set_avatar=lambda: None)
page.resize(900, 640)
page.show()
page.my_id = "me"
page.add_channel("#a")
page.set_active_channel("#a")
app.processEvents(); app.processEvents()
view = page._log_views["#a"]


def wait(ms=2500):
    loop = QEventLoop(); QTimer.singleShot(ms, loop.quit); loop.exec()
    app.processEvents()


print("\n[2] 이미지 주소만 보냈을 때")
page.append_message("#a", "Mong", LONG, False, 1.0)
w = view._messages[-1]
before = w._text_label.text()
check("응답 전에는 주소가 보임", LONG in before, before[:60])
wait()
after = w._text_label.text()
check("미리보기가 뜬 뒤 주소가 사라짐", LONG not in after, after[:80])
check("보낸 사람은 남음", "Mong" in after, after[:80])
prev = w.findChildren(ImagePreview)
check("이미지가 표시됨", len(prev) == 1, len(prev))
check("이미지를 눌러 열 수 있음(주소를 들고 있음)",
      prev and prev[0]._url == LONG, prev[0]._url if prev else None)

print("\n[3] 뉴스 주소만 보냈을 때")
page.append_message("#a", "Mong", f"{BASE}/news", False, 2.0)
w2 = view._messages[-1]
wait()
after2 = w2._text_label.text()
check("주소가 사라짐", "/news" not in after2, after2[:80])
cards = w2.findChildren(LinkCard)
check("카드가 표시됨", len(cards) == 1, len(cards))
check("카드에 제목", cards and cards[0].title_label.text() == "뉴스 제목입니다")
check("카드를 눌러 열 수 있음", cards and cards[0]._url == f"{BASE}/news")

print("\n[4] 문장 + 링크는 글자를 남겨야 함")
page.append_message("#a", "Mong", f"이거 봐 {LONG} 좋지", False, 3.0)
w3 = view._messages[-1]
wait()
after3 = w3._text_label.text()
check("문장이 남음", "이거 봐" in after3 and "좋지" in after3, after3[:80])
check("주소도 남음(링크만 있는 게 아니므로)", "p.png" in after3, after3[:80])
check("그래도 미리보기는 뜸", len(w3.findChildren(ImagePreview)) == 1)

print("\n[5] 미리보기를 못 받으면 주소가 그대로 남아야 함(못 여는 일 없게)")
dead = f"{BASE}/missing.png"
page.append_message("#a", "Mong", dead, False, 4.0)
w4 = view._messages[-1]
wait()
after4 = w4._text_label.text()
check("주소가 그대로 남음", "missing.png" in after4, after4[:80])
check("미리보기는 없음", len(w4.findChildren(ImagePreview)) == 0)

print("\n[6] 지난 기록은 그대로 주소만(미리보기 안 함)")
page.load_history("#a", [{"from": "Mong", "text": LONG, "ts": 1.0}])
w5 = view._messages[-1]
wait(800)
check("기록은 주소가 남음", "p.png" in w5._text_label.text())
check("기록엔 미리보기 없음", len(w5.findChildren(ImagePreview)) == 0)

srv.shutdown()
print()
if fails:
    print(f"실패 {len(fails)}건: {fails}")
    sys.exit(1)
print("전부 통과")
