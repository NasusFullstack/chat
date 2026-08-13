"""유튜브 링크 미리보기.

왜 따로 두는가: 유튜브 페이지는 og 태그가 문서 한참 뒤에 있어서, 우리가 받는 앞부분
(256KB)만으로는 제목도 그림도 못 찾는다. 실측으로 확인했다 - 262KB를 받아도 뽑히는 것이
하나도 없었다.

대신 유튜브가 공식으로 열어둔 oEmbed를 쓴다(로그인·키 필요 없음).
제목/채널/썸네일 주소를 작은 JSON 한 번으로 준다(실측 0.2~0.3초).

    https://www.youtube.com/oembed?format=json&url=<주소>

이 방식은 페이지 전체를 받지 않으므로 오히려 가볍다(262KB -> 1KB 남짓).
"""
import json
import re
import urllib.parse

OEMBED = "https://www.youtube.com/oembed?format=json&url="

# youtube.com/watch?v=..., youtu.be/..., /shorts/..., /embed/... 를 모두 받는다
_PATTERNS = (
    re.compile(r"^https?://(?:www\.|m\.)?youtube\.com/watch\?(?:.*&)?v=([\w-]{6,})", re.I),
    re.compile(r"^https?://youtu\.be/([\w-]{6,})", re.I),
    re.compile(r"^https?://(?:www\.|m\.)?youtube\.com/shorts/([\w-]{6,})", re.I),
    re.compile(r"^https?://(?:www\.|m\.)?youtube\.com/embed/([\w-]{6,})", re.I),
    re.compile(r"^https?://(?:www\.|m\.)?youtube\.com/live/([\w-]{6,})", re.I),
)


def video_id(url: str) -> str:
    """유튜브 주소면 영상 id, 아니면 빈 문자열."""
    for pattern in _PATTERNS:
        match = pattern.match(url or "")
        if match:
            return match.group(1)
    return ""


def is_youtube(url: str) -> bool:
    return bool(video_id(url))


def oembed_url(url: str) -> str:
    return OEMBED + urllib.parse.quote(url, safe="")


def thumbnail_url(url: str) -> str:
    """영상 대표 그림. oEmbed가 주는 것과 같은 주소를 직접 만들 수도 있다."""
    vid = video_id(url)
    return f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg" if vid else ""


def parse_oembed(raw: bytes, url: str) -> dict:
    """oEmbed 응답을 우리 미리보기 카드가 쓰는 모양으로 바꾼다.

    실패하면 빈 dict - 미리보기는 덤이라 실패해도 조용히 포기한다(그래도 링크는 남는다).
    """
    try:
        data = json.loads(raw.decode("utf-8", "replace"))
    except (ValueError, AttributeError):
        return {}
    title = str(data.get("title") or "").strip()
    if not title:
        return {}
    author = str(data.get("author_name") or "").strip()
    return {
        "title": title,
        # 카드 설명 자리에 채널 이름을 넣는다 - 유튜브는 설명이 따로 없다
        "description": f"YouTube · {author}" if author else "YouTube",
        "image_url": str(data.get("thumbnail_url") or thumbnail_url(url)),
    }
