"""링크 미리보기용 순수 함수들 - HTML 메타태그 파싱 + 주소 안전성 검사.

네트워크 I/O가 전혀 없다(Qt/urllib 어느 쪽도 안 씀). 실제로 받아오는 일은 클라이언트가
비동기로 하고, 이 파일은 "받아온 바이트에서 무엇을 뽑을지"와 "이 주소에 접속해도 되는지"만
판단한다. 그래서 Qt 없이 그대로 테스트할 수 있다.

미리보기를 클라이언트가 직접 가져오는 구조라, 여기서의 주소 검사는 '내 PC를 지키는' 용도다:
누가 채팅에 http://192.168.0.1/ 같은 걸 올리면 그걸 본 사람들의 앱이 각자 자기 집 공유기에
접속하게 되므로, 그런 주소는 아예 요청하지 않는다.
"""
import html as html_mod
import ipaddress
import re
import urllib.parse

TITLE_MAX = 120   # 지나치게 긴 제목이 채팅창을 밀어내지 않게 자름
DESC_MAX = 200

# og:xxx 와 twitter:xxx 를 둘 다 받음. 속성 순서(content가 앞에 오는 경우)도 있어서
# 양방향으로 찾는다
# 예전에는 meta 태그 하나를 통째로 잡는 큰 정규식을 문서 전체에 돌렸다. 그런데 `.*?`와
# `[^>]*?`가 겹쳐 있어서, 조건에 안 맞는 <meta를 만날 때마다 뒤로 되돌아가며 문서 끝까지
# 훑는 일이 반복됐다(catastrophic backtracking). 실측: 어떤 쇼핑몰 페이지(247KB, meta 30개)
# 에서 **13.7초 동안 화면이 통째로 멈췄다** - 링크 하나 붙였을 뿐인데.
#
# 지금은 되돌아갈 일이 없게 두 단계로 나눈다.
# 1) `<meta ...>` 하나의 범위를 따옴표를 지켜가며 앞에서 뒤로 한 번만 훑어 잘라낸다
# 2) 잘라낸 짧은 태그 안에서만 속성을 읽는다
# 문서 길이에 정비례해서 끝나므로 아무리 큰 페이지가 와도 멈추지 않는다.
_ATTR_RE = re.compile(
    r"""([\w:.-]+)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'>]+))""")
_META_PREFIX = "<meta"

_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_CHARSET_RE = re.compile(rb"""charset\s*=\s*["']?\s*([\w\-]+)""", re.IGNORECASE)

_IMAGE_EXT_RE = re.compile(r"\.(png|jpe?g|gif|webp|bmp)(?:[?#].*)?$", re.IGNORECASE)


def is_image_url(url: str) -> bool:
    """확장자로 이미지 직링크인지 판단.

    확장자가 없는 이미지 서비스는 웹페이지로 취급되는데, 그런 곳은 대개 og:image를
    갖고 있어서 카드로 잘 나오므로 문제되지 않음."""
    return bool(_IMAGE_EXT_RE.search(url))


def is_safe_public_url(url: str) -> bool:
    """접속해도 되는 주소인지. 사설망/루프백이나 http(s)가 아닌 것은 거부.

    호스트가 이름(도메인)이면 통과시킨다 - 여기서 DNS를 조회하면 화면이 멈추기 때문이고,
    실제로 문제가 되는 건 채팅에 사설 IP를 그대로 적어 올리는 경우다.
    """
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ("http", "https"):
        return False
    host = (parts.hostname or "").strip("[]")
    if not host:
        return False
    if host.lower() in ("localhost", "localhost.localdomain"):
        return False
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return True  # 도메인 이름 - 정상적인 웹주소로 봄
    return not (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_multicast or ip.is_reserved or ip.is_unspecified)


def decode_html(raw: bytes) -> str:
    """meta charset을 보고 디코딩. 못 찾으면 utf-8로 시도하고 깨진 글자는 버림."""
    match = _CHARSET_RE.search(raw[:4096])
    if match:
        try:
            return raw.decode(match.group(1).decode("ascii", "ignore"), "replace")
        except (LookupError, UnicodeDecodeError):
            pass
    return raw.decode("utf-8", "replace")



def _iter_meta_tags(html: str):
    """`<meta ...>` 하나씩을 잘라서 돌려준다(앞에서 뒤로 한 번만 훑는다).

    따옴표 안의 `>`는 태그 끝으로 치지 않는다 - content="a > b" 같은 값이 실제로 있다.
    """
    lower = html.lower()
    index = 0
    length = len(html)
    while True:
        start = lower.find(_META_PREFIX, index)
        if start < 0:
            return
        cursor = start + len(_META_PREFIX)
        quote = ""
        while cursor < length:
            char = html[cursor]
            if quote:
                if char == quote:
                    quote = ""
            elif char in "\"'":
                quote = char
            elif char == ">":
                break
            cursor += 1
        yield html[start:cursor]
        index = cursor + 1


def parse_meta(html: str, base_url: str = "") -> dict:
    """<head>의 og:/twitter: 태그와 <title>에서 미리보기 정보를 뽑음.

    반환 키(있는 것만): title, description, image_url
    image_url은 절대주소로 바꾸고, 접속하면 안 되는 주소면 빼버린다.
    """
    tags = {}
    for tag in _iter_meta_tags(html):
        attrs = {}
        for m in _ATTR_RE.finditer(tag):
            name = m.group(1).lower()
            attrs[name] = m.group(2) or m.group(3) or m.group(4) or ""
        key = (attrs.get("property") or attrs.get("name") or "").lower()
        value = attrs.get("content", "")
        # og:/twitter: 만 본다(그 외 meta는 미리보기와 상관없음)
        if key.startswith(("og:", "twitter:")) and value and key not in tags:
            tags[key] = value.strip()

    def pick(*names):
        for name in names:
            if tags.get(name):
                return tags[name]
        return ""

    result = {}
    title = pick("og:title", "twitter:title")
    if not title:
        m = _TITLE_RE.search(html)
        if m:
            title = m.group(1)
    if not title:
        return {}  # 제목조차 없으면 카드를 만들 게 없음
    result["title"] = _clean(title, TITLE_MAX)

    desc = pick("og:description", "twitter:description")
    if desc:
        result["description"] = _clean(desc, DESC_MAX)

    image = pick("og:image", "og:image:url", "twitter:image", "twitter:image:src")
    if image and base_url:
        absolute = urllib.parse.urljoin(base_url, image)
        if is_safe_public_url(absolute):
            result["image_url"] = absolute
    return result


def _clean(text: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", html_mod.unescape(text)).strip()
    return text[:limit - 1] + "…" if len(text) > limit else text


def head_only(raw: bytes) -> bytes:
    """</head>까지만 남김 - 본문은 파싱에 필요 없어 메모리/시간을 아낌."""
    lowered = raw.lower()
    end = lowered.find(b"</head>")
    return raw[:end + 7] if end >= 0 else raw
