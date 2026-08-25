"""확장자가 안 붙은 이미지 주소도 그림으로 뜨는가.

실제 신고(2026-08-14): 다음/카카오 썸네일 주소가 그림으로 안 떴다.

    https://img1.daumcdn.net/thumb/R800x0/?scode=...&fname=...img.png%3Fcredential%3D...

주소 **끝**에 확장자가 없어서(확장자가 물음표 뒤 값 안에 들어 있다) 웹페이지로 보고
og 태그를 찾다 실패했다. 실제로는 `image/png` 481KB짜리 그림이었다(실측).

요즘 이런 주소가 흔하다 - 썸네일 변환, 서명이 붙은 CDN 주소, 확장자 없는 이미지 API.
그래서 "주소가 .png로 끝나는가"로 판단하는 것 자체가 틀렸다. 받아온 **내용의 첫 몇
바이트**를 보면 형식이 확실하다.
"""
import os as _os
import sys as _sys

_HERE = _os.path.dirname(_os.path.abspath(__file__))
_REPO = _os.path.dirname(_HERE)

_os.environ["QT_QPA_PLATFORM"] = "offscreen"
_sys.path.insert(0, _REPO)

import link_meta  # noqa: E402

checks = []


def check(name, ok, detail=""):
    checks.append((name, ok, detail))


DAUM_THUMB = ("https://img1.daumcdn.net/thumb/R800x0/?scode=mtistory2&fname=https%3A%2F%2F"
              "blog.kakaocdn.net%2Fdna%2FM7CBu%2Fimg.png%3Fcredential%3Dabc%26signature%3Dxyz")

# 구글 이미지 썸네일도 같은 모양이다(확장자 없음) - 실제로 둘 다 신고를 받았다
GOOGLE_THUMB = ("https://encrypted-tbn0.gstatic.com/images?"
                "q=tbn:ANd9GcQ6-edgBcVcH2OYfU7KckpjTCDxfveJrdPUT4jnxXTQHA&s=10")

# ---------- 1) 주소만으로는 못 알아본다(그래서 내용을 봐야 한다) ----------
for label, url in (("다음 썸네일", DAUM_THUMB), ("구글 썸네일", GOOGLE_THUMB)):
    check(f"{label}: 주소만으로는 그림인 줄 모른다",
          link_meta.is_image_url(url) is False, link_meta.is_image_url(url))

# ---------- 2) 내용으로는 확실히 알아본다 ----------
SAMPLES = {
    "PNG": b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR",
    "JPEG": b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01",
    "GIF87a": b"GIF87a\x10\x00\x10\x00",
    "GIF89a": b"GIF89a\x10\x00\x10\x00",
    "BMP": b"BM\x36\x00\x00\x00\x00\x00\x00\x00",
    "WEBP": b"RIFF\x24\x00\x00\x00WEBPVP8 ",
}
for name, data in SAMPLES.items():
    check(f"{name}을 그림으로 알아본다", link_meta.looks_like_image(data) is True, data[:8])

NOT_IMAGES = {
    "HTML": b"<!DOCTYPE html><html><head><title>",
    "빈 값": b"",
    "짧은 값": b"ab",
    "JSON": b'{"title": "hello"}',
    "글자": "가나다라".encode("utf-8"),
    "WEBP인 척": b"RIFF\x24\x00\x00\x00WAVEfmt ",     # RIFF지만 WEBP가 아님
}
for name, data in NOT_IMAGES.items():
    check(f"{name}은 그림이 아니라고 본다", link_meta.looks_like_image(data) is False, data[:12])

# ---------- 3) 화면 쪽이 그 판단을 실제로 쓰는가 ----------
import io  # noqa: E402

area_source = io.open(_os.path.join(_REPO, "gui/preview/area.py"), encoding="utf-8").read()
check("미리보기 칸이 내용으로 판단하는 경로를 쓴다",
      "looks_like_image" in area_source and "_on_unknown" in area_source)
check("모르는 주소는 그림일 수 있으니 넉넉히 받는다",
      "UNKNOWN_LIMIT_BYTES" in area_source)

from gui.preview.fetcher import HTML_LIMIT_BYTES, UNKNOWN_LIMIT_BYTES  # noqa: E402

check(f"그 한도가 HTML 한도보다 크다({UNKNOWN_LIMIT_BYTES} > {HTML_LIMIT_BYTES})",
      UNKNOWN_LIMIT_BYTES > HTML_LIMIT_BYTES, (UNKNOWN_LIMIT_BYTES, HTML_LIMIT_BYTES))

# 실제로 문제가 됐던 크기(481KB)를 받을 수 있어야 한다
check("실제로 못 받던 크기(481KB)를 이제 받는다", UNKNOWN_LIMIT_BYTES > 481039,
      UNKNOWN_LIMIT_BYTES)

# ---------- 4) 화면에서 그림으로 뜨는가(네트워크 없이) ----------
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])
import gui_client as g  # noqa: E402
from gui.preview.area import LinkPreviewArea  # noqa: E402

app.setStyleSheet(g.STYLE_SHEET)

# 진짜 PNG 한 장을 만들어, 확장자 없는 주소로 받은 것처럼 흘려 넣는다
from PySide6.QtCore import QBuffer  # noqa: E402
from PySide6.QtGui import QPixmap  # noqa: E402

pixmap = QPixmap(40, 30)
pixmap.fill()
buffer = QBuffer()
buffer.open(QBuffer.OpenModeFlag.WriteOnly)
pixmap.save(buffer, "PNG")
png_bytes = bytes(buffer.data())
check("시험용 PNG를 만들었다", link_meta.looks_like_image(png_bytes))

area = LinkPreviewArea([DAUM_THUMB], fetcher=None)
area._on_unknown(DAUM_THUMB, png_bytes)
for _ in range(6):
    app.processEvents()
kinds = [type(area._layout.itemAt(i).widget()).__name__
         for i in range(area._layout.count())
         if area._layout.itemAt(i).widget() is not None]
check(f"확장자 없는 주소도 그림으로 붙는다({kinds})", "ImagePreview" in kinds, kinds)

# 웹페이지는 예전처럼 카드로
html_area = LinkPreviewArea(["https://example.com/page"], fetcher=None)
html_area._on_unknown("https://example.com/page",
                      b"<html><head><title>\xed\x95\x9c\xea\xb8\x80</title></head></html>")
for _ in range(6):
    app.processEvents()
html_kinds = [type(html_area._layout.itemAt(i).widget()).__name__
              for i in range(html_area._layout.count())
              if html_area._layout.itemAt(i).widget() is not None]
check(f"웹페이지는 여전히 카드로 뜬다({html_kinds})", "LinkCard" in html_kinds, html_kinds)

print("=== 검증 결과 (확장자 없는 이미지 주소) ===")
all_ok = True
for name, ok, *detail in checks:
    extra = f"  <- {detail[0]}" if detail and detail[0] and not ok else ""
    print(f"[{'OK' if ok else 'FAIL'}] {name}{extra}")
    all_ok = all_ok and ok
print("\n전체 통과:", all_ok)
_sys.exit(0 if all_ok else 1)
