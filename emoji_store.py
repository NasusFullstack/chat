"""내 이모티콘 보관함 (로컬 저장, 클라이언트 전용).

**이미지 파일은 저장하지 않고 주소만 저장한다.** 그림 자체는 쓸 때 받아서 캐시하면 되고,
주소 목록은 몇 KB밖에 안 돼서 서버가 필요 없다.

목록을 채널에 뿌리지도 않는다. 200개짜리 목록을 IRC로 보내면 512바이트 한 줄 제한 때문에
50줄 넘게 쪼개져 나가고, 그건 서버가 폭주로 보고 연결을 끊어버린다. 남이 알아야 하는 건
'내가 방금 쓴 그 하나'뿐이므로, 쓸 때 그 주소만 메시지에 실어 보낸다.

항목 하나는 {"url": 주소, "name": 내가 붙인 이름}. 이름은 보관함에서 찾기 쉬우라고 붙이는
것이고 비어 있어도 된다(이름은 내 PC에만 있고 남에게 전달되지 않는다).
저장 위치는 avatars.json / login_prefs.json과 같은 앱 폴더의 emojis.json.
"""
import json
import os
import sys

import link_meta

MAX_EMOJIS = 300          # 이 이상은 받지 않음(고르는 창이 감당 못 할 정도로 늘지 않게)
MAX_URL_LEN = 400         # IRC 한 줄(512바이트)에 여유 있게 들어가는 길이
MAX_NAME_LEN = 20


def _app_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


EMOJI_STORE_FILE = os.path.join(_app_dir(), "emojis.json")


def is_valid_emoji_url(url: str) -> bool:
    """보관함에 넣어도 되는 주소인가.

    사설망/내부 주소를 걸러야 한다 - 누가 채팅에 공유기 주소를 올리고 그걸 보관함에 넣으면
    이모티콘을 볼 때마다 각자 자기 공유기를 두드리게 된다(link_meta 설명 참고).
    """
    if not url or len(url) > MAX_URL_LEN:
        return False
    return link_meta.is_image_url(url) and link_meta.is_safe_public_url(url)


def load_emojis() -> list[dict]:
    """보관함 목록. 항목은 {"url": ..., "name": ...} (먼저 넣은 것부터)."""
    if not os.path.exists(EMOJI_STORE_FILE):
        return []
    try:
        with open(EMOJI_STORE_FILE, "r", encoding="utf-8") as fp:
            data = json.load(fp)
    except (json.JSONDecodeError, OSError):
        return []
    if not isinstance(data, list):
        return []
    out = []
    for item in data[:MAX_EMOJIS]:
        # 예전 형식(주소 문자열만 있던 목록)도 그대로 읽을 수 있게 함
        if isinstance(item, str) and item:
            out.append({"url": item, "name": ""})
        elif isinstance(item, dict) and item.get("url"):
            out.append({"url": item["url"], "name": str(item.get("name", ""))[:MAX_NAME_LEN]})
    return out


def _save(items: list[dict]) -> None:
    try:
        with open(EMOJI_STORE_FILE, "w", encoding="utf-8") as fp:
            json.dump(items, fp, ensure_ascii=False)
    except OSError:
        pass


def _index_of(items: list[dict], url: str) -> int:
    for i, item in enumerate(items):
        if item["url"] == url:
            return i
    return -1


def add_emoji(url: str, name: str = "") -> tuple[bool, str]:
    """보관함에 추가. (성공 여부, 사용자에게 보여줄 말)"""
    url = (url or "").strip()
    if not is_valid_emoji_url(url):
        return False, "이모티콘으로 쓸 수 없는 주소입니다."
    items = load_emojis()
    if _index_of(items, url) >= 0:
        return False, "이미 보관함에 있습니다."
    if len(items) >= MAX_EMOJIS:
        return False, f"보관함이 가득 찼습니다(최대 {MAX_EMOJIS}개)."
    items.append({"url": url, "name": (name or "").strip()[:MAX_NAME_LEN]})
    _save(items)
    return True, "이모티콘 보관함에 저장했습니다."


def rename_emoji(url: str, name: str) -> bool:
    """이름 바꾸기(빈 이름이면 이름을 지움)."""
    items = load_emojis()
    index = _index_of(items, (url or "").strip())
    if index < 0:
        return False
    items[index]["name"] = (name or "").strip()[:MAX_NAME_LEN]
    _save(items)
    return True


def remove_emoji(url: str) -> bool:
    items = load_emojis()
    index = _index_of(items, (url or "").strip())
    if index < 0:
        return False
    items.pop(index)
    _save(items)
    return True


def has_emoji(url: str) -> bool:
    return _index_of(load_emojis(), (url or "").strip()) >= 0
