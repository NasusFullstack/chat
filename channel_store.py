"""지난번에 **들어가 있던 채널**을 기억해두는 곳.

앱을 다시 켤 때마다 채널 선택 화면에서 같은 방을 손으로 다시 골라야 했다. 늘 들어가는
방이 정해져 있으면 그 과정이 매번 똑같은 수고다.

## 닉네임마다 따로 적는다
한 컴퓨터를 두 이름으로 쓸 수 있다. 한 이름으로 들어갔던 방을 다른 이름으로 켤 때
멋대로 들어가면 안 된다 - 그래서 열쇠에 서버와 닉네임을 같이 넣는다.
IRC 닉네임은 대소문자를 가리지 않으므로 소문자로 맞춰 적는다.

## 서버에 두지 않는 이유
이건 **이 기기에서 쓰는 사람의 습관**이지 계정 정보가 아니다. 서버에 올리면 누가 어느
방에 들어가 있는지를 서버가 알게 되고, 로그인도 없는 구조에서 그걸 보관할 이유가 없다.
모바일도 같은 방식으로 기기에 적는다(mobile/lib/login_store.dart).
"""
import json
import os

import app_paths

STORE_FILE = os.path.join(app_paths.data_dir(), "channels.json")

# 기억할 서버+이름 조합 수 상한(파일이 끝없이 불어나지 않게)
MAX_KEYS = 50

# 한 사람이 기억할 채널 수 상한. 이보다 많이 들어가 있으면 앞엣것만 적는다 -
# 다시 들어갈 때 그 수만큼 JOIN 이 나가므로 무한정 늘어나면 폭주로 보인다
MAX_CHANNELS = 20


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
        # 적어두지 못하면 다음에 손으로 고르면 된다 - 앱이 죽을 일은 아니다
        pass


def _key(host: str, port: int, nick: str) -> str:
    return f"{host}:{port}/{(nick or '').lower()}"


def load(host: str, port: int, nick: str) -> list:
    """이 이름으로 들어가 있던 채널들(순서 그대로). 없으면 빈 목록."""
    if not nick:
        return []
    rooms = _read().get(_key(host, port, nick))
    if not isinstance(rooms, list):
        return []
    return [str(room) for room in rooms if str(room).strip()]


def save(host: str, port: int, nick: str, channels) -> None:
    """지금 들어가 있는 채널을 적어둔다.

    들어가고 나갈 때마다 부른다. 빈 목록도 그대로 적는다 - 다 나왔으면 다음에 아무
    방에도 안 들어가는 게 맞다.
    """
    if not nick:
        return
    data = _read()
    data[_key(host, port, nick)] = list(channels)[:MAX_CHANNELS]
    # 오래된 조합부터 버린다(파이썬 dict 는 넣은 순서를 지킨다)
    while len(data) > MAX_KEYS:
        data.pop(next(iter(data)))
    _write(data)
