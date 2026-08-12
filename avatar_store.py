"""아이콘(아바타) 로컬 영구 저장 (클라이언트 전용, GUI 전용).

커스텀 프로토콜은 서버가 계정별로 아이콘을 저장해줘서 재접속해도 유지되지만,
실제 IRC 서버는 그런 기능이 전혀 없어서(CTCP로 우리 클라이언트끼리만 실시간으로 주고받음)
재시작할 때마다 서로의 아이콘을 처음부터 다시 받아야만 보였음. 사용자 ID(닉네임) 기준으로
한 번 본 아이콘을 로컬에도 남겨둬서, 재시작 직후에도(서버 응답을 기다리지 않고) 곧바로
기본 도트 대신 예전 아이콘이 보이게 함. 실행 파일과 같은 폴더의 avatars.json에 저장.
"""
import json
import os
import sys

import app_paths


def _app_dir() -> str:
    return app_paths.data_dir()


AVATAR_STORE_FILE = os.path.join(_app_dir(), "avatars.json")


def load_avatars() -> dict[str, str]:
    """{user_id: avatar_base64_png} 형태로 반환. 파일이 없거나 읽을 수 없으면 빈 딕셔너리."""
    if not os.path.exists(AVATAR_STORE_FILE):
        return {}
    try:
        with open(AVATAR_STORE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def save_avatar(user_id: str, avatar_b64: str) -> None:
    if not user_id or not avatar_b64:
        return
    data = load_avatars()
    if data.get(user_id) == avatar_b64:
        return  # 변화 없으면 디스크에 다시 쓰지 않음
    data[user_id] = avatar_b64
    try:
        with open(AVATAR_STORE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except OSError:
        pass
