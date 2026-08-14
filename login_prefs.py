"""로그인 정보 로컬 저장 (자동로그인용).

사용자가 로그인 화면에서 "자동로그인" 체크박스를 직접 켠 경우에만 비밀번호까지 저장함
(체크 안 하면 아이디/서버 주소 등 민감하지 않은 값만 기억하고 비밀번호는 저장 안 함).
실행 파일과 같은 폴더의 login_prefs.json에 평문으로 저장되므로, 이 파일을 다른 사람과
공유하면 안 됨(개인용 앱이라 같은 컴퓨터를 여럿이 쓰는 상황은 고려하지 않음).
"""
import json
import os
import sys

import app_paths




LOGIN_PREFS_FILE = os.path.join(app_paths.data_dir(), "login_prefs.json")


def load() -> dict:
    if not os.path.exists(LOGIN_PREFS_FILE):
        return {}
    try:
        with open(LOGIN_PREFS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def save(prefs: dict) -> None:
    try:
        with open(LOGIN_PREFS_FILE, "w", encoding="utf-8") as f:
            json.dump(prefs, f)
    except OSError:
        pass


# 예전에 평문으로 저장돼 있던 접속 정보를 보안 접속으로 올려준다.
# 같은 서버의 보안 포트가 열려 있는 것을 확인하고 기본값을 바꿨으므로(실측: TLS 1.3),
# 쓰던 사람도 그대로 따라오게 한다. 다른 포트를 직접 넣어 쓰는 사람은 건드리지 않는다
PLAIN_TO_SECURE = {"6667": "6697"}


def upgrade_to_secure(prefs: dict) -> dict:
    """저장된 값이 '평문 기본 포트'면 보안 접속으로 바꾼 사본을 돌려준다."""
    if not prefs or prefs.get("ssl"):
        return prefs
    port = str(prefs.get("port", "")).strip()
    if port not in PLAIN_TO_SECURE:
        return prefs
    upgraded = dict(prefs)
    upgraded["port"] = PLAIN_TO_SECURE[port]
    upgraded["ssl"] = True
    return upgraded
