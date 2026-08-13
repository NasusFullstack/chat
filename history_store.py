"""채팅 기록 로컬 저장 (클라이언트 전용)
- 서버는 기록을 보관하지 않음 - 재접속/재입장 시 "이어서 보기" 용도로 각 클라이언트가 직접 저장
- GUI/CLI 클라이언트가 공용으로 사용
- 실행 파일과 같은 폴더의 history.json에 저장
"""
import json
import os
import sys

import app_paths

MAX_MESSAGES_PER_CHANNEL = 200




HISTORY_FILE = os.path.join(app_paths.data_dir(), "history.json")


def _server_key(protocol: str, host: str, port: int) -> str:
    return f"{protocol}:{host}:{port}"


def _load_all() -> dict:
    if not os.path.exists(HISTORY_FILE):
        return {}
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_all(data: dict):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_history(protocol: str, host: str, port: int, channel: str) -> list[dict]:
    """[{"from": str, "text": str, "ts": float}, ...] 오래된 순. 없으면 빈 리스트."""
    data = _load_all()
    server = data.get(_server_key(protocol, host, port), {})
    return server.get(channel, [])


def append_message(protocol: str, host: str, port: int, channel: str,
                    sender: str, text: str, ts: float) -> None:
    data = _load_all()
    key = _server_key(protocol, host, port)
    server = data.setdefault(key, {})
    entries = server.setdefault(channel, [])
    entries.append({"from": sender, "text": text, "ts": ts})
    if len(entries) > MAX_MESSAGES_PER_CHANNEL:
        del entries[: len(entries) - MAX_MESSAGES_PER_CHANNEL]
    _save_all(data)
