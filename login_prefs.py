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


def _app_dir() -> str:
    return app_paths.data_dir()


LOGIN_PREFS_FILE = os.path.join(_app_dir(), "login_prefs.json")


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
