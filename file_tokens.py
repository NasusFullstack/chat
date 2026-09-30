"""내가 올린 파일의 표 - 이것이 있어야 도로 내릴 수 있다(클라이언트 전용).

중계 서버에는 계정이 없어서 "누가 올렸는가"를 물어볼 데가 없다. 올릴 때 서버가 표를
하나 주는데, 그 표를 가진 사람만 그 파일을 지울 수 있다. 여기에 적어둔다.

**표가 있다는 것이 곧 '내가 올린 것'이라는 표시**이기도 하다 - 채팅에 뜬 파일 카드는
이걸 보고 '내리기' 버튼을 보여줄지 정한다.

파일은 기한이 지나면 저절로 사라지므로, 표도 같이 오래 들고 있을 이유가 없다.
"""
import json
import os
import time

import app_paths

TOKEN_FILE = os.path.join(app_paths.data_dir(), "file_tokens.json")

# 파일 자체가 하루면 사라진다. 표를 그보다 오래 들고 있어 봐야 쓸 데가 없다
KEEP_DAYS = 3


def _load_raw() -> dict:
    try:
        with open(TOKEN_FILE, encoding="utf-8") as fp:
            saved = json.load(fp)
        return saved if isinstance(saved, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(data: dict):
    try:
        os.makedirs(os.path.dirname(TOKEN_FILE), exist_ok=True)
        with open(TOKEN_FILE, "w", encoding="utf-8") as fp:
            json.dump(data, fp)
    except OSError:
        pass


def _fresh(data: dict) -> dict:
    cutoff = time.time() - KEEP_DAYS * 86400
    return {key: value for key, value in data.items()
            if isinstance(value, dict) and value.get("at", 0) >= cutoff}


def remember(file_id: str, token: str):
    if not file_id or not token:
        return
    data = _fresh(_load_raw())
    data[file_id] = {"token": token, "at": time.time()}
    _save(data)


def token_for(file_id: str) -> str:
    entry = _fresh(_load_raw()).get(file_id) or {}
    return entry.get("token", "")


def is_mine(file_id: str) -> bool:
    """내가 올린 것인가 - 표가 있으면 내 것이다."""
    return bool(token_for(file_id))


def forget(file_id: str):
    data = _fresh(_load_raw())
    if data.pop(file_id, None) is not None:
        _save(data)
