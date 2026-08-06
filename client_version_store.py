"""한 번 알아낸 "그 사람이 쓰는 프로그램"을 기억해두는 곳.

이게 없으면 앱을 켤 때마다 채널에 있는 모두에게 다시 물어보게 된다. 서버 입장에서는
간격을 두므로 문제가 없지만, **상대 쪽 화면에는 요청이 찍힌다** - WeeChat이나 HexChat은
"CTCP VERSION received from ..."을 서버 창에 남긴다. 하루에 앱을 열 번 켜면 남들에게
열 번 찍히는 셈이라 실례다.

그래서 서버별로 "이 닉네임은 이 프로그램"을 적어두고, 다음에는 묻지 않고 바로 쓴다.

**영원히 기억하지는 않는다.** IRC 닉네임은 주인이 바뀔 수 있고 쓰던 프로그램도 바뀐다.
그래서 기한(REMEMBER_DAYS)을 두고, 지나면 한 번 다시 물어본다.
"""
import json
import os
import sys
import time

REMEMBER_DAYS = 7
REMEMBER_SEC = REMEMBER_DAYS * 24 * 60 * 60
# 서버 하나에서 기억할 사람 수 상한(파일이 끝없이 불어나지 않게)
MAX_PER_HOST = 500


def _app_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


STORE_FILE = os.path.join(_app_dir(), "client_versions.json")


def _read() -> dict:
    if not os.path.exists(STORE_FILE):
        return {}
    try:
        with open(STORE_FILE, "r", encoding="utf-8") as fp:
            data = json.load(fp)
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def _write(data: dict) -> None:
    try:
        with open(STORE_FILE, "w", encoding="utf-8") as fp:
            json.dump(data, fp, ensure_ascii=False)
    except OSError:
        pass


def load(host: str) -> dict:
    """그 서버에서 기억하고 있는 {닉네임: 프로그램}. 기한이 지난 것은 빼고 준다."""
    if not host:
        return {}
    now = time.time()
    known = {}
    for nick, entry in _read().get(host, {}).items():
        if nick == _REFUSED_KEY:
            continue
        if not isinstance(entry, list) or len(entry) != 2:
            continue
        version, saved_at = entry
        if isinstance(version, str) and now - saved_at < REMEMBER_SEC:
            known[nick] = version
    return known


def remember(host: str, nick: str, version: str) -> None:
    """알아낸 것을 적어둔다.

    **같은 값이면 적은 시각을 그대로 둔다.** 기억해둔 값을 쓸 때마다 시각을 새로 찍으면
    기한이 영원히 갱신되어 다시는 확인하지 않게 된다(기한을 둔 의미가 사라짐).
    """
    if not (host and nick and version):
        return
    data = _read()
    per_host = data.setdefault(host, {})
    previous = per_host.get(nick)
    if isinstance(previous, list) and len(previous) == 2 and previous[0] == version:
        return  # 이미 같은 값 - 시각을 건드리지 않는다
    per_host[nick] = [version, time.time()]
    if len(per_host) > MAX_PER_HOST:
        # 오래된 것부터 버린다
        oldest = sorted(per_host.items(), key=lambda kv: kv[1][1])[:len(per_host) - MAX_PER_HOST]
        for key, _ in oldest:
            per_host.pop(key, None)
    _write(data)


# 서버가 "그런 건 못 한다"고 거절한 적이 있는지 적어두는 자리(닉네임과 섞이지 않는 키)
_REFUSED_KEY = "__probe_refused__"


def mark_probe_refused(host: str) -> None:
    """이 서버는 물어보기를 거절한다 - 다시는 보내지 않는다.

    실제 사례: UnrealIRCd가 "Multi-target messaging is not allowed"로 거절했고,
    참여자 수만큼 경고가 채팅창에 쏟아졌다. 한 번 거절당하면 멈추는 게 맞다.
    """
    if not host:
        return
    data = _read()
    data.setdefault(host, {})[_REFUSED_KEY] = [True, time.time()]
    _write(data)


def probe_allowed(host: str) -> bool:
    return not _read().get(host, {}).get(_REFUSED_KEY)


def forget(host: str, nick: str) -> None:
    """그 사람에 대한 기억만 지운다.

    같은 닉네임으로 **다른 프로그램**을 켜고 다시 들어올 수 있다. 그때 예전 기억을
    그대로 쓰면 엉뚱한 로고가 며칠씩 붙어 있게 된다.
    """
    data = _read()
    if data.get(host, {}).pop(nick, None) is not None:
        _write(data)


def forget_host(host: str) -> None:
    data = _read()
    if data.pop(host, None) is not None:
        _write(data)
