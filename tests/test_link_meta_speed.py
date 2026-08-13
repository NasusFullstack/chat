"""링크 미리보기 해석이 페이지 크기에 정비례해서 끝나는가.

실제 사고(2026-08-13): 채팅에 쇼핑몰 링크 하나를 붙였더니 **앱이 13.7초 동안 통째로
멈췄다.** 원인은 meta 태그를 통째로 잡던 큰 정규식이었다. `.*?`와 `[^>]*?`가 겹쳐 있어
조건에 안 맞는 `<meta`를 만날 때마다 뒤로 되돌아가며 문서를 다시 훑었다
(catastrophic backtracking).

폭주 조건을 실제 페이지에서 찾아보니 이거였다: **따옴표는 많은데 `>`가 거의 없는 긴
구간**(인라인 스크립트/JSON)이 meta 사이에 끼어 있는 것. 옛 정규식은 그 구간의 따옴표마다
다시 시도하고, 그때마다 `>`를 만날 때까지 멀리 달려간다. 그래서 문서가 두 배가 되면
시간은 네 배가 된다. 실측(옛 방식): 13KB 1.1초 / 26KB 4.2초 / 53KB 16.9초 / 107KB 68초.

여기서 확인하는 것: 큰 문서에서도 **금방 끝나는가**(시간), 그리고 그 와중에 예전과
**같은 값을 뽑는가**(정확도). 속도만 보면 파서를 망가뜨려도 통과하므로 둘 다 본다.
"""
import os as _os
import sys as _sys

_HERE = _os.path.dirname(_os.path.abspath(__file__))
_REPO = _os.path.dirname(_HERE)
_sys.path.insert(0, _REPO)

import time

import link_meta

checks = []


def check(name, ok, detail=""):
    checks.append((name, ok, detail))


def build_page(script_lines: int) -> str:
    """앱을 멈추게 했던 페이지와 같은 구조(스크립트가 meta 사이에 끼어 있음)."""
    script = "".join(
        '  var item%d = {"name": "상품 %d", "price": "12900"};\n' % (i, i)
        for i in range(script_lines)
    )
    return (
        "<html><head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="keywords" content="콤부차 애사비">\n'
        '<meta name="description" content="상관없는 설명">\n'
        "<script>\n" + script + "</script>\n"
        '<meta property="og:title" content="작심랩">\n'
        '<meta property="og:description" content="설명입니다">\n'
        '<meta property="og:image" content="https://example.com/a.png">\n'
        "<title>제목</title></head><body></body></html>"
    )


big_page = build_page(400)          # 옛 방식으로 4.2초 걸리던 크기(약 26KB)

started = time.time()
meta = link_meta.parse_meta(big_page, "https://example.com/x.html")
elapsed = time.time() - started

check(f"큰 페이지({len(big_page) // 1024}KB)를 1초 안에 해석한다({elapsed:.2f}초)",
      elapsed < 1.0, f"{elapsed:.2f}초")
check("제목을 제대로 뽑는다", meta.get("title") == "작심랩", meta)
check("설명을 제대로 뽑는다", meta.get("description") == "설명입니다", meta)
check("이미지 주소를 제대로 뽑는다",
      meta.get("image_url") == "https://example.com/a.png", meta)

# 문서가 두 배가 되면 시간도 두 배 언저리여야 한다.
# 되돌아가며 훑는 방식이면 두 배가 아니라 네 배로 뛴다(그게 이번 사고의 정체다)
double_page = build_page(800)
started = time.time()
link_meta.parse_meta(double_page, "https://example.com/x.html")
doubled = time.time() - started
check(f"문서가 두 배여도 시간이 폭발하지 않는다({elapsed:.3f}초 -> {doubled:.3f}초)",
      doubled < max(0.5, elapsed * 4), f"{elapsed:.3f} -> {doubled:.3f}")

# ---------- 태그 모양이 달라도 읽어야 한다 ----------
variants = [
    ('<meta content="뒤에 온 경우" property="og:title">', "뒤에 온 경우"),
    ("<meta property='og:title' content='홑따옴표'>", "홑따옴표"),
    ('<meta property="og:title" content="꺾쇠 > 포함">', "꺾쇠 > 포함"),
    ('<META PROPERTY="OG:TITLE" CONTENT="대문자">', "대문자"),
]
for html, expected in variants:
    got = link_meta.parse_meta("<html><head>" + html + "</head></html>").get("title")
    check(f"{expected!r} 모양도 읽는다", got == expected, got)

# ---------- 미리보기와 무관한 meta는 무시 ----------
noise = link_meta.parse_meta('<meta name="viewport" content="width=device-width">')
check("상관없는 meta는 제목으로 쓰지 않는다", not noise.get("title"), noise)

print("=== 검증 결과 (링크 해석 속도/정확도) ===")
all_ok = True
for name, ok, *detail in checks:
    extra = f"  <- {detail[0]}" if detail and detail[0] and not ok else ""
    print(f"[{'OK' if ok else 'FAIL'}] {name}{extra}")
    all_ok = all_ok and ok
print("\n전체 통과:", all_ok)
_sys.exit(0 if all_ok else 1)
