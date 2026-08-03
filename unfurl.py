"""서버가 대신 링크 정보를 가져와 주는 모듈 (카톡/슬랙이 하는 'unfurl').

왜 서버가 대신 하는가:
클라이언트가 각자 링크에 접속하면 (1) 채널에 5명이면 대상 사이트에 요청이 5번 가고,
(2) 링크 주인에게 참여자 전원의 IP가 노출되고, (3) 각자 원본 이미지(수 MB)를 통째로
받게 된다. 서버가 한 번만 받아서 캐시해두고 결과만 나눠주면 셋 다 해결된다.

**서버가 '아무 URL이나 대신 접속해주는 기계'가 된다는 점을 반드시 의식할 것.**
그대로 두면 채팅에 http://192.168.0.1/ 을 올리는 것만으로 서버가 자기 집 내부망에
접속하게 만들 수 있다(SSRF). 그래서 _check_url_allowed()의 검사를 절대 빼면 안 되고,
리다이렉트를 따라간 뒤에도 다시 검사해야 한다(공개 주소로 시작해 사설 주소로 튕기는
우회가 가능하므로).

이미지(썸네일)는 코드는 다 있지만 IMAGES_ENABLED로 꺼둔 상태다. 서버 관리자가 트래픽
부담을 확인한 뒤 켜면 된다. 꺼져 있으면 제목/설명만 반환한다.
"""
import html as html_mod
import ipaddress
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request

# 서버 관리자가 트래픽 부담을 확인한 뒤 켜는 스위치.
# 켜면 og:image를 받아 작은 썸네일(JPEG base64)까지 함께 내려줌.
IMAGES_ENABLED = False

USER_AGENT = "Mozilla/5.0 (compatible; FriendChat-unfurl/1.0)"

HTML_LIMIT_BYTES = 256 * 1024    # og 태그는 <head>에 있으므로 앞부분만 받으면 충분
IMAGE_LIMIT_BYTES = 5 * 1024 * 1024
TIMEOUT_SEC = 8
MAX_REDIRECTS = 3

THUMB_PX = 80          # 썸네일 한 변 (원본이 아무리 커도 이 크기로 줄임)
TITLE_MAX = 120        # 지나치게 긴 제목이 채팅창을 밀어내지 않게 자름
DESC_MAX = 200

CACHE_MAX_ENTRIES = 500
CACHE_TTL_SEC = 24 * 60 * 60

# 사용자 한 명이 짧은 시간에 링크를 도배해 서버 자원을 소모하지 못하게 하는 상한
RATE_LIMIT_PER_MIN = 20


class UnfurlError(Exception):
    pass


# ==================== SSRF 방어 ====================

def _is_public_ip(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    # 사설/루프백/링크로컬/멀티캐스트/예약 대역은 전부 거부.
    # 169.254.169.254(클라우드 메타데이터)는 is_link_local에 걸림
    return not (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_multicast or ip.is_reserved or ip.is_unspecified)


def _check_url_allowed(url: str) -> str:
    """접속해도 되는 주소인지 검사하고 정규화된 URL을 반환. 아니면 UnfurlError.

    호스트 이름을 실제로 DNS 조회해서 확인한다. 이름만 보면
    'internal.example.com -> 192.168.0.5' 같은 우회를 막을 수 없기 때문.
    """
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise UnfurlError(f"지원하지 않는 프로토콜: {parts.scheme or '(없음)'}")
    if not parts.hostname:
        raise UnfurlError("주소에 호스트가 없습니다")
    try:
        infos = socket.getaddrinfo(parts.hostname, parts.port or
                                   (443 if parts.scheme == "https" else 80),
                                   proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise UnfurlError(f"주소를 찾을 수 없습니다: {exc}") from exc
    for info in infos:
        ip = info[4][0]
        if not _is_public_ip(ip):
            # 내부망 주소로 해석되면 즉시 거부 - SSRF 방어의 핵심
            raise UnfurlError(f"내부망 주소로는 접속하지 않습니다 ({ip})")
    return url


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """리다이렉트를 자동으로 따라가지 않게 막음.

    urllib 기본 동작은 리다이렉트를 알아서 따라가는데, 그러면 '공개 주소로 시작해서
    사설 주소로 튕기는' 우회를 검사할 틈이 없다. 직접 한 단계씩 따라가면서 매번
    _check_url_allowed()를 다시 통과시킨다.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _open(url: str, limit: int):
    """리다이렉트를 직접 따라가며 매 단계 주소를 검사하고, limit 바이트까지만 읽음."""
    opener = urllib.request.build_opener(_NoRedirect)
    current = _check_url_allowed(url)
    for _ in range(MAX_REDIRECTS + 1):
        request = urllib.request.Request(current, headers={"User-Agent": USER_AGENT})
        try:
            with opener.open(request, timeout=TIMEOUT_SEC) as response:
                return response.read(limit + 1)[:limit], current
        except urllib.error.HTTPError as exc:
            if exc.code in (301, 302, 303, 307, 308):
                location = exc.headers.get("Location")
                if not location:
                    raise UnfurlError("리다이렉트 주소가 없습니다") from exc
                # 리다이렉트로 옮겨간 주소도 반드시 다시 검사
                current = _check_url_allowed(urllib.parse.urljoin(current, location))
                continue
            raise UnfurlError(f"HTTP {exc.code}") from exc
        except (urllib.error.URLError, socket.timeout, OSError) as exc:
            raise UnfurlError(str(exc)) from exc
    raise UnfurlError("리다이렉트가 너무 많습니다")


# ==================== HTML 파싱 ====================

_META_RE = re.compile(
    r"<meta[^>]+?(?:property|name)\s*=\s*[\"'](og:[^\"']+|twitter:[^\"']+)[\"'][^>]*?"
    r"content\s*=\s*[\"'](.*?)[\"'][^>]*>"
    r"|<meta[^>]+?content\s*=\s*[\"'](.*?)[\"'][^>]*?(?:property|name)\s*=\s*[\"']"
    r"(og:[^\"']+|twitter:[^\"']+)[\"'][^>]*>",
    re.IGNORECASE | re.DOTALL,
)
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_CHARSET_RE = re.compile(rb"""charset\s*=\s*["']?\s*([\w\-]+)""", re.IGNORECASE)


def decode_html(raw: bytes) -> str:
    match = _CHARSET_RE.search(raw[:4096])
    if match:
        try:
            return raw.decode(match.group(1).decode("ascii", "ignore"), "replace")
        except (LookupError, UnicodeDecodeError):
            pass
    return raw.decode("utf-8", "replace")


def parse_open_graph(html: str) -> dict:
    """<head>의 og:/twitter: 태그와 <title>에서 제목/설명/이미지주소를 뽑음"""
    tags = {}
    for m in _META_RE.finditer(html):
        key = (m.group(1) or m.group(4) or "").lower()
        value = m.group(2) if m.group(1) else m.group(3)
        if key and value and key not in tags:
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
    if title:
        result["title"] = _clean(title, TITLE_MAX)
    desc = pick("og:description", "twitter:description")
    if desc:
        result["description"] = _clean(desc, DESC_MAX)
    image = pick("og:image", "og:image:url", "twitter:image", "twitter:image:src")
    if image:
        result["image_url"] = image
    return result


def _clean(text: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", html_mod.unescape(text)).strip()
    return text[:limit - 1] + "…" if len(text) > limit else text


# ==================== 썸네일 (기본 꺼짐) ====================

def make_thumbnail_b64(image_bytes: bytes) -> str:
    """원본 이미지를 THUMB_PX 정사각 JPEG로 줄여 base64로 반환. 실패하면 빈 문자열.

    IMAGES_ENABLED가 켜져야만 호출된다. Pillow가 없으면 조용히 포기(서버에 무거운
    의존성을 강제하지 않으려는 것 - 썸네일은 어디까지나 덤).
    """
    try:
        import base64
        import io
        from PIL import Image
    except ImportError:
        return ""
    try:
        img = Image.open(io.BytesIO(image_bytes))
        img = img.convert("RGB")
        # 가운데를 정사각으로 잘라야 카드 높이가 항상 일정함(단순 축소는 납작해짐)
        edge = min(img.size)
        left = (img.width - edge) // 2
        top = (img.height - edge) // 2
        img = img.crop((left, top, left + edge, top + edge))
        img = img.resize((THUMB_PX, THUMB_PX), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=75)
        return base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception:
        return ""


# ==================== 캐시 + 속도 제한 ====================

_cache: dict[str, tuple[float, dict]] = {}
_rate: dict[str, list[float]] = {}


def _cache_get(url: str):
    entry = _cache.get(url)
    if entry is None:
        return None
    stored_at, value = entry
    if time.time() - stored_at > CACHE_TTL_SEC:
        _cache.pop(url, None)
        return None
    return value


def _cache_put(url: str, value: dict):
    if len(_cache) >= CACHE_MAX_ENTRIES:
        # 가장 오래된 것부터 버림 - 디스크/메모리 무한 증식 방지
        oldest = min(_cache, key=lambda k: _cache[k][0])
        _cache.pop(oldest, None)
    _cache[url] = (time.time(), value)


def check_rate_limit(user_id: str) -> bool:
    """도배 방지. 허용되면 True(호출 시각을 기록함)"""
    now = time.time()
    times = [t for t in _rate.get(user_id, []) if now - t < 60]
    if len(times) >= RATE_LIMIT_PER_MIN:
        _rate[user_id] = times
        return False
    times.append(now)
    _rate[user_id] = times
    return True


# ==================== 진입점 ====================

def unfurl(url: str) -> dict:
    """링크 정보를 반환. 실패하면 {} (호출자는 그냥 미리보기를 안 만들면 됨).

    반환 키: title, description, thumb_b64 (있는 것만)
    """
    cached = _cache_get(url)
    if cached is not None:
        return cached
    try:
        raw, final_url = _open(url, HTML_LIMIT_BYTES)
    except UnfurlError:
        _cache_put(url, {})  # 실패도 캐시해서 같은 링크로 계속 재시도하지 않게 함
        return {}

    info = parse_open_graph(decode_html(raw))
    image_url = info.pop("image_url", "")
    result = {k: v for k, v in info.items() if v}

    if IMAGES_ENABLED and image_url and result:
        try:
            absolute = urllib.parse.urljoin(final_url, image_url)
            image_bytes, _ = _open(absolute, IMAGE_LIMIT_BYTES)
            thumb = make_thumbnail_b64(image_bytes)
            if thumb:
                result["thumb_b64"] = thumb
        except UnfurlError:
            pass  # 썸네일은 덤이라 실패해도 제목/설명은 그대로 보냄

    _cache_put(url, result)
    return result
