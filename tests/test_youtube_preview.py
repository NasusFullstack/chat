"""유튜브 링크에 미리보기가 뜨는가(네트워크 없이).

왜 따로 처리하는가: 유튜브 페이지는 og 태그가 문서 한참 뒤에 있어서, 우리가 받는
앞부분(256KB)에는 제목도 그림도 없다. 실측으로 확인했다 - 262KB를 받아도 뽑히는 게
하나도 없었다. 그래서 유튜브가 공식으로 열어둔 oEmbed를 쓴다(실측 0.2~0.3초, 1KB 남짓).

여기서는 진짜 유튜브에 접속하지 않는다. 주소를 알아보는 규칙과, 응답을 카드 정보로
바꾸는 규칙만 확인한다(네트워크에 기대는 검사는 느리고 남의 서버 상태에 흔들린다).
"""
import os as _os
import sys as _sys

_HERE = _os.path.dirname(_os.path.abspath(__file__))
_REPO = _os.path.dirname(_HERE)

_os.environ["QT_QPA_PLATFORM"] = "offscreen"
_sys.path.insert(0, _REPO)

import json  # noqa: E402

from gui.preview import youtube  # noqa: E402

checks = []


def check(name, ok, detail=""):
    checks.append((name, ok, detail))


# ---------- 1) 어떤 주소를 유튜브로 볼 것인가 ----------
YOUTUBE = [
    "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "https://youtube.com/watch?v=dQw4w9WgXcQ",
    "https://m.youtube.com/watch?v=dQw4w9WgXcQ",
    "https://www.youtube.com/watch?list=PL123&v=dQw4w9WgXcQ",
    "https://youtu.be/9bZkp7q19f0",
    "https://www.youtube.com/shorts/abc123XYZ",
    "https://www.youtube.com/embed/abc123XYZ",
    "https://www.youtube.com/live/abc123XYZ",
]
for url in YOUTUBE:
    check(f"유튜브로 알아본다: {url[:52]}", youtube.is_youtube(url), url)

NOT_YOUTUBE = [
    "https://example.com/watch?v=abc123",
    "https://youtube.com.evil.example/watch?v=abc123",
    "https://www.youtube.com/",
    "https://zaksim-lab.com/product/detail.html",
]
for url in NOT_YOUTUBE:
    check(f"유튜브가 아니다: {url[:52]}", not youtube.is_youtube(url), url)

check("영상 id를 정확히 뽑는다",
      youtube.video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ",
      youtube.video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ"))
check("짧은 주소에서도 뽑는다",
      youtube.video_id("https://youtu.be/9bZkp7q19f0") == "9bZkp7q19f0")

# ---------- 2) 요청 주소 ----------
api = youtube.oembed_url("https://youtu.be/9bZkp7q19f0")
check(f"공식 oEmbed 주소를 만든다({api[:60]}...)",
      api.startswith("https://www.youtube.com/oembed?format=json&url=")
      and "youtu.be" in api, api)

# ---------- 3) 응답을 카드 정보로 ----------
answer = json.dumps({
    "title": "PSY - GANGNAM STYLE(강남스타일) M/V",
    "author_name": "officialpsy",
    "thumbnail_url": "https://i.ytimg.com/vi/9bZkp7q19f0/hqdefault.jpg",
}).encode("utf-8")
info = youtube.parse_oembed(answer, "https://youtu.be/9bZkp7q19f0")
check(f"제목을 그대로 쓴다({info.get('title')})",
      info.get("title") == "PSY - GANGNAM STYLE(강남스타일) M/V", info)
check(f"올린 채널을 설명에 넣는다({info.get('description')})",
      info.get("description") == "YouTube · officialpsy", info)
check("대표 그림 주소를 쓴다",
      info.get("image_url") == "https://i.ytimg.com/vi/9bZkp7q19f0/hqdefault.jpg", info)

# 채널 이름이 없어도 카드는 떠야 한다
partial = youtube.parse_oembed(json.dumps({"title": "제목만 있음"}).encode(),
                               "https://youtu.be/abc123XYZ")
check("채널 이름이 없어도 카드를 만든다", partial.get("title") == "제목만 있음", partial)
check("그림 주소가 없으면 영상 id로 만들어 쓴다",
      partial.get("image_url") == "https://i.ytimg.com/vi/abc123XYZ/hqdefault.jpg", partial)

# 응답이 깨졌거나 비어도 조용히 포기해야 한다(미리보기는 덤이다)
for broken in (b"", b"not json", b"{}", b'{"title": ""}', None):
    check(f"이상한 응답에도 안 죽는다({broken!r})",
          youtube.parse_oembed(broken, "https://youtu.be/abc123XYZ") == {}, broken)

# ---------- 4) 실제 화면 경로에 연결돼 있는가 ----------
import io  # noqa: E402

area_source = io.open(_os.path.join(_REPO, "gui/preview/area.py"), encoding="utf-8").read()
check("미리보기 칸이 유튜브 경로를 쓴다",
      "youtube.is_youtube" in area_source and "_on_youtube" in area_source)
check("페이지 전체를 받지 않는다(작은 JSON 하나만)",
      "youtube.oembed_url" in area_source, "")

print("=== 검증 결과 (유튜브 미리보기) ===")
all_ok = True
for name, ok, *detail in checks:
    extra = f"  <- {detail[0]}" if detail and detail[0] and not ok else ""
    print(f"[{'OK' if ok else 'FAIL'}] {name}{extra}")
    all_ok = all_ok and ok
print("\n전체 통과:", all_ok)
_sys.exit(0 if all_ok else 1)
