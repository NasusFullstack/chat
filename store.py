"""
사용자 계정 / 채널 데이터 저장소
- 비밀번호는 절대 평문 저장하지 않고 salt + sha256 해시로 저장
- 데이터는 JSON 파일에 저장 (server_data.json)
"""
import json
import os
import hashlib
import secrets
import threading
import base64
import binascii

DATA_FILE = os.path.join(os.path.dirname(__file__), "server_data.json")
_lock = threading.Lock()

# gui_client.py의 AVATAR_MAX_B64_CHARS와 값을 맞춰야 함 (16x16 ARGB32 PNG는
# 아무리 복잡해도 이론상 최대 약 1400자 정도라 여유를 두고 2000자로 제한)
AVATAR_MAX_B64_CHARS = 2000


def _empty_data():
    return {"users": {}, "channels": {}}


def load_data():
    if not os.path.exists(DATA_FILE):
        return _empty_data()
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return _empty_data()


def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def hash_password(password: str, salt: str = None) -> tuple[str, str]:
    if salt is None:
        salt = secrets.token_hex(16)
    digest = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
    return digest, salt


class Store:
    def __init__(self):
        self.data = load_data()

    # ---------------- 계정 ----------------
    def register_user(self, user_id: str, password: str) -> tuple[bool, str]:
        with _lock:
            if not user_id or not password:
                return False, "아이디와 비밀번호를 모두 입력하세요."
            if len(password) < 4:
                return False, "비밀번호는 4자 이상이어야 합니다."
            if user_id in self.data["users"]:
                return False, "이미 존재하는 아이디입니다."
            digest, salt = hash_password(password)
            self.data["users"][user_id] = {"hash": digest, "salt": salt}
            save_data(self.data)
            return True, "회원가입 완료"

    def verify_user(self, user_id: str, password: str) -> tuple[bool, str]:
        with _lock:
            user = self.data["users"].get(user_id)
            if not user:
                return False, "존재하지 않는 아이디입니다."
            digest, _ = hash_password(password, user["salt"])
            if digest != user["hash"]:
                return False, "비밀번호가 일치하지 않습니다."
            return True, "로그인 성공"

    # ---------------- 채널 ----------------
    def create_channel(self, channel: str, key: str, owner: str) -> tuple[bool, str]:
        with _lock:
            if channel in self.data["channels"]:
                return False, "이미 존재하는 채널입니다."
            digest, salt = hash_password(key) if key else (None, None)
            self.data["channels"][channel] = {
                "hash": digest,
                "salt": salt,
                "owner": owner,
            }
            save_data(self.data)
            return True, "채널 생성 완료"

    def verify_channel(self, channel: str, key: str) -> tuple[bool, str]:
        with _lock:
            chan = self.data["channels"].get(channel)
            if not chan:
                return False, "존재하지 않는 채널입니다. (새 채널을 먼저 만드세요)"
            if chan["hash"] is None:
                return True, "입장 성공"
            digest, _ = hash_password(key or "", chan["salt"])
            if digest != chan["hash"]:
                return False, "채널 비밀번호가 일치하지 않습니다."
            return True, "입장 성공"

    # ---------------- 아이콘 ----------------
    def set_avatar(self, user_id: str, avatar_b64: str) -> tuple[bool, str]:
        with _lock:
            if user_id not in self.data["users"]:
                return False, "존재하지 않는 사용자입니다."
            if not avatar_b64:
                self.data["users"][user_id]["avatar"] = None
                save_data(self.data)
                return True, "아이콘이 삭제되었습니다."
            if len(avatar_b64) > AVATAR_MAX_B64_CHARS:
                return False, "아이콘 데이터가 너무 큽니다."
            try:
                base64.b64decode(avatar_b64, validate=True)
            except (binascii.Error, ValueError):
                return False, "아이콘 데이터 형식이 올바르지 않습니다."
            self.data["users"][user_id]["avatar"] = avatar_b64
            save_data(self.data)
            return True, "아이콘 저장 완료"

    def get_avatar(self, user_id: str) -> str | None:
        with _lock:
            user = self.data["users"].get(user_id)
            return user.get("avatar") if user else None
