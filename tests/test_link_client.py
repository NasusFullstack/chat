"""링크 미리보기(전부 클라이언트 처리) - 로컬 HTTP 서버로 실제 네트워크 경로 검증."""
import os as _os
import sys as _sys

_HERE = _os.path.dirname(_os.path.abspath(__file__))
_REPO = _os.path.dirname(_HERE)

import os, sys, threading, time
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, _REPO)

from http.server import BaseHTTPRequestHandler, HTTPServer

from PySide6.QtCore import Qt, QTimer, QEventLoop
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])

import link_meta
from gui import link_preview as lp
from gui.link_preview import ImageFetcher, LinkCard, LinkPreviewArea

SP = os.path.dirname(os.path.abspath(__file__))
fails = []


def check(label, cond, extra=""):
    print(("  OK   " if cond else "  FAIL ") + label + ("" if cond else f"  <- {extra}"))
    if not cond:
        fails.append(label)


def png(w, h, color="#3aa0e8"):
    img = QImage(w, h, QImage.Format.Format_ARGB32)
    img.fill(QColor(color))
    p = os.path.join(SP, "_t.png"); img.save(p)
    d = open(p, "rb").read(); os.remove(p); return d


WIDE = png(1200, 400)
SMALL = png(64, 64)
GIF = (b"GIF89a\x02\x00\x02\x00\x80\x00\x00\xff\x00\x00\x00\x00\xff"
       b"!\xff\x0bNETSCAPE2.0\x03\x01\x00\x00\x00"
       b"!\xf9\x04\x00\x0a\x00\x00\x00,\x00\x00\x00\x00\x02\x00\x02\x00\x00\x02\x02D\x01\x00"
       b"!\xf9\x04\x00\x0a\x00\x00\x00,\x00\x00\x00\x00\x02\x00\x02\x00\x00\x02\x02L\x01\x00;")

NEWS = ("""<!doctype html><html><head><meta charset="utf-8">
<meta property="og:title" content="삼성전자, 신형 반도체 공개">
<meta property="og:description" content="업계 판도가 바뀔지 주목된다.">
<meta property="og:image" content="/thumb.png">
<title>무시되어야 할 title</title></head><body>""" + "본문 " * 5000 + "</body></html>").encode("utf-8")
PLAIN = "<html><head><title>  그냥   페이지  </title></head><body>x</body></html>".encode("utf-8")
NOTITLE = b"<html><head></head><body>nothing</body></html>"

hits = []


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        hits.append(self.path)
        table = {"/wide.png": ("image/png", WIDE), "/small.png": ("image/png", SMALL),
                 "/thumb.png": ("image/png", WIDE), "/anim.gif": ("image/gif", GIF),
                 "/news": ("text/html; charset=utf-8", NEWS),
                 "/plain": ("text/html; charset=utf-8", PLAIN),
                 "/notitle": ("text/html", NOTITLE)}
        if self.path not in table:
            self.send_response(404); self.end_headers(); return
        ct, body = table[self.path]
        self.send_response(200); self.send_header("Content-Type", ct)
        self.send_header("Content-Length", str(len(body))); self.end_headers()
        self.wfile.write(body)


srv = HTTPServer(("127.0.0.1", 0), H)
PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = f"http://127.0.0.1:{PORT}"

print("\n[1] 메타태그 파싱 (순수 함수, Qt 없이 동작)")
# base_url은 공인 주소로 둠 - 로컬 주소를 주면 아래 '내부망 차단'이 정상 동작해서
# image_url이 일부러 빠지기 때문(그 동작 자체는 [2]와 아래 별도 항목에서 확인)
info = link_meta.parse_meta(link_meta.decode_html(NEWS), base_url="https://news.example.com/a/b")
check("og:title 사용(=<title> 무시)", info.get("title") == "삼성전자, 신형 반도체 공개", info)
check("og:description", info.get("description") == "업계 판도가 바뀔지 주목된다.", info)
check("og:image가 절대주소로", info.get("image_url") == "https://news.example.com/thumb.png",
      info.get("image_url"))
local_info = link_meta.parse_meta(link_meta.decode_html(NEWS), base_url=f"{BASE}/news")
check("og:image가 내부망을 가리키면 빼버림(내 PC 보호)", "image_url" not in local_info,
      local_info.get("image_url"))
check("og 없으면 <title> 폴백 + 공백 정리",
      link_meta.parse_meta(link_meta.decode_html(PLAIN)).get("title") == "그냥 페이지")
check("제목 없으면 빈 결과", link_meta.parse_meta(link_meta.decode_html(NOTITLE)) == {})
long_title = link_meta.parse_meta(f"<title>{'가' * 300}</title>")["title"]
check(f"긴 제목 {link_meta.TITLE_MAX}자로 자름 + 말줄임",
      len(long_title) <= link_meta.TITLE_MAX and long_title.endswith("…"), len(long_title))
check("head_only가 본문을 잘라냄",
      len(link_meta.head_only(NEWS)) < len(NEWS) / 2, len(link_meta.head_only(NEWS)))

print("\n[2] 접속하면 안 되는 주소 차단 (내 PC/내부망 보호)")
for url, why in (("http://127.0.0.1/", "루프백"), ("http://localhost:8080/x", "localhost"),
                 ("http://192.168.0.1/", "공유기"), ("http://10.0.0.5/", "사설망"),
                 ("http://169.254.169.254/", "클라우드 메타데이터"),
                 ("file:///C:/Windows/win.ini", "file://"), ("ftp://a.com/x", "ftp://")):
    check(f"{why} 차단", not link_meta.is_safe_public_url(url), url)
check("정상 웹주소는 통과", link_meta.is_safe_public_url("https://news.example.com/a"))

print("\n[3] 이미지 직링크 판별")
for url, want in ((f"{BASE}/wide.png", True), (f"{BASE}/anim.gif", True),
                  ("https://a.com/x.JPEG", True), ("https://a.com/x.png?w=1", True),
                  (f"{BASE}/news", False)):
    check(f"{url[-20:]:>20} -> {'이미지' if want else '웹페이지'}", lp.is_image_url(url) is want)

print("\n[4] 실제 다운로드 (차단 주소는 요청조차 안 함)")
fetcher = ImageFetcher()


def fetch_sync(url, limit=lp.DOWNLOAD_LIMIT_BYTES, wait=8000):
    box, loop = {}, QEventLoop()
    fetcher.fetch(url, lambda d: (box.__setitem__("d", d), loop.quit()), limit=limit)
    QTimer.singleShot(wait, loop.quit)
    loop.exec()
    return box.get("d")


hits.clear()
check("사설망 주소는 아예 요청 안 함", fetch_sync("http://192.168.0.1/x.png") is None)
check("  (실제로 네트워크 요청이 안 나감)", len(hits) == 0, hits)

# 테스트 서버가 127.0.0.1이라 차단됨 - 검사만 잠시 우회해서 나머지를 검증
_orig = link_meta.is_safe_public_url
link_meta.is_safe_public_url = lambda u: u.startswith("http")
try:
    check("이미지 받아짐", fetch_sync(f"{BASE}/small.png") == SMALL)
    check("404는 None", fetch_sync(f"{BASE}/missing.png") is None)
    check("HTML 상한이 적용됨(본문까지 다 안 받음)",
          len(fetch_sync(f"{BASE}/news", limit=lp.HTML_LIMIT_BYTES)) <= lp.HTML_LIMIT_BYTES)

    print("\n[5] 이미지 미리보기 크기")
    prev = lp.ImagePreview()
    check("1200x400 로드됨", prev.set_image_data(fetch_sync(f"{BASE}/wide.png")))
    check(f"가로 {lp.IMAGE_PREVIEW_WIDTH}px로 축소", prev.pixmap().width() == lp.IMAGE_PREVIEW_WIDTH,
          prev.pixmap().width())
    small = lp.ImagePreview()
    small.set_image_data(fetch_sync(f"{BASE}/small.png"))
    check("작은 이미지는 확대 안 함", small.pixmap().width() == 64, small.pixmap().width())
    check("깨진 데이터는 False", lp.ImagePreview().set_image_data(b"not an image") is False)

    print("\n[6] GIF 움짤")
    gif = lp.ImagePreview()
    check("GIF 로드됨", gif.set_image_data(fetch_sync(f"{BASE}/anim.gif")))
    check("재생 중", gif.movie() is not None
          and gif.movie().state() == gif.movie().MovieState.Running)
    check("프레임 2개 이상", gif.movie() is not None and gif.movie().frameCount() >= 2)

    print("\n[7] 메시지에 붙은 링크가 끝까지 처리되는가 (서버 없이)")
    import gui_client as g
    page = g.ChatPage(on_send=lambda c, t: None, on_add_channel=lambda: None,
                      on_leave_channel=lambda c: None, on_set_avatar=lambda: None)
    page.resize(800, 600)
    page.my_id = "me"
    page.add_channel("#a")
    page.set_active_channel("#a")
    view = page._log_views["#a"]

    page.append_message("#a", "Mong", "링크 없음", False, 1.0)
    check("링크 없으면 미리보기 자리도 없음", len(view.findChildren(LinkPreviewArea)) == 0)

    hits.clear()
    page.append_message("#a", "Mong", f"사진 {BASE}/wide.png", False, 2.0)
    page.append_message("#a", "Mong", f"뉴스 {BASE}/news", False, 3.0)
    loop = QEventLoop(); QTimer.singleShot(4000, loop.quit); loop.exec()

    previews = view.findChildren(lp.ImagePreview)
    cards = view.findChildren(LinkCard)
    check("이미지 미리보기 생김", len(previews) == 1, len(previews))
    check("뉴스 카드 생김", len(cards) == 1, len(cards))
    if cards:
        check("제목", cards[0].title_label.text() == "삼성전자, 신형 반도체 공개")
        check("설명", cards[0].desc_label.text() == "업계 판도가 바뀔지 주목된다.")
        # isVisible()은 부모 창을 show()하지 않으면 항상 False라 여기선 못 씀.
        # 실제로 그림이 붙었는지는 픽스맵으로 확인
        thumb_pm = cards[0].thumb.pixmap()
        check("썸네일까지 받아옴(og:image)", thumb_pm is not None and not thumb_pm.isNull(),
              "썸네일이 안 붙음")
        check(f"썸네일이 {lp.CARD_THUMB_PX}px 정사각으로 잘림",
              thumb_pm is not None and thumb_pm.width() == thumb_pm.height() == lp.CARD_THUMB_PX,
              (thumb_pm.width(), thumb_pm.height()) if thumb_pm else None)
    check("서버에 물어보지 않고 직접 받아옴", f"/news" in hits and "/thumb.png" in hits, hits)

    print("\n[8] 지난 기록은 미리보기를 안 만듦")
    hits.clear()
    page.load_history("#a", [{"from": "Mong", "text": f"옛날 {BASE}/wide.png", "ts": 1.0}] * 20)
    loop = QEventLoop(); QTimer.singleShot(1200, loop.quit); loop.exec()
    check("기록 20개에 링크가 있어도 요청 0건", len(hits) == 0, hits)
    check("기록 메시지 자체는 정상 표시", len(view._messages) >= 20, len(view._messages))

    print("\n[9] 제목 못 뽑는 페이지는 카드 안 만듦")
    before = len(view.findChildren(LinkCard))
    page.append_message("#a", "Mong", f"제목없음 {BASE}/notitle", False, 4.0)
    loop = QEventLoop(); QTimer.singleShot(1500, loop.quit); loop.exec()
    check("카드가 안 늘어남(하이퍼링크만)", len(view.findChildren(LinkCard)) == before)

    print("\n[10] 죽은 링크는 조용히 무시")
    before_p = len(view.findChildren(lp.ImagePreview))
    page.append_message("#a", "Mong", "http://127.0.0.1:1/dead.png", False, 5.0)
    loop = QEventLoop(); QTimer.singleShot(1500, loop.quit); loop.exec()
    check("미리보기 안 늘어남", len(view.findChildren(lp.ImagePreview)) == before_p)
    check("메시지 본문은 정상", "dead.png" in view._messages[-1]._text_label.text())
finally:
    link_meta.is_safe_public_url = _orig

srv.shutdown()
print()
if fails:
    print(f"실패 {len(fails)}건: {fails}")
    sys.exit(1)
print("전부 통과")
