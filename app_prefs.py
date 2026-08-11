"""앱 동작 설정 (알림 표시 여부 등) - 로컬 저장.

로그인 정보(login_prefs.py)와 파일을 나눈 이유: 로그인 정보는 계정/서버가 바뀌면 통째로
덮어써지는데, 알림 설정은 그것과 무관하게 유지돼야 한다. 한 파일에 두면 로그아웃 한 번에
알림 설정까지 초기화된다.
"""
import json
import os
import sys

DEFAULTS = {
    # 창이 안 보이거나 다른 창을 쓰는 중일 때 새 메시지를 오른쪽 아래에 띄울지
    "notifications": True,
    # 알림에 보낸 사람과 내용을 다 보여줄지(남이 화면을 볼 수 있는 자리에서 유용)
    "notify_preview": True,
    # 위를 껐을 때 그래도 무엇까지 보여줄지: sender(사람만) / message(메시지만) / none(모두 숨김)
    "notify_detail": "none",
    # 창을 닫으면 종료하지 않고 트레이(작업표시줄 오른쪽 아이콘)로 내려보낼지
    "close_to_tray": True,
    # "창을 닫아도 계속 받습니다" 안내를 이미 보여줬는지. 처음 한 번만 알려주면 되고,
    # 닫을 때마다 뜨면 성가시기만 하다
    "tray_hint_shown": False,
    # 참여자가 무슨 프로그램으로 접속했는지 알아보고 목록에 작은 로고로 표시할지.
    # 알아보려면 상대에게 CTCP VERSION을 한 번 보내야 해서, 원치 않으면 끌 수 있게 둔다
    "show_client_badges": True,
    # 채널 목록을 접어둔 채로 껐다면 다음에도 접힌 채로 열림
    "channel_sidebar_collapsed": False,
    # 화면 테마(gui/styles/palette.py의 THEMES 키). 지금은 기본 테마 하나뿐이고 추가 예정
    "theme": "dark",
    # 변경 내역 창을 이미 보여준 버전. 패치 뒤 한 번만 띄우기 위한 기록
    # (gui/changelog_dialog.py)
    "changelog_shown_version": "",
}


def _app_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


PREFS_FILE = os.path.join(_app_dir(), "app_prefs.json")


def load() -> dict:
    """저장된 설정. 파일이 없거나 깨졌으면 기본값."""
    prefs = dict(DEFAULTS)
    if not os.path.exists(PREFS_FILE):
        return prefs
    try:
        with open(PREFS_FILE, "r", encoding="utf-8") as fp:
            saved = json.load(fp)
    except (json.JSONDecodeError, OSError):
        return prefs
    if isinstance(saved, dict):
        # 모르는 항목은 무시하고, 아는 항목만 덮어씀(옛 파일/새 파일 모두 안전).
        # **기본값의 자료형을 지킬 것.** 예전엔 여기서 전부 bool()로 바꿔버려서, 글자를
        # 담는 설정(테마, 알림 상세, 변경 내역 버전)이 재시작할 때마다 True/False로
        # 뭉개졌다 - "사람만 표시"를 골라도 다음 실행에는 무시되는 버그였다.
        # save()만 고치고 여기를 빠뜨려서 한동안 안 보였다
        for key, default in DEFAULTS.items():
            if key in saved:
                prefs[key] = bool(saved[key]) if isinstance(default, bool) else str(saved[key])
    return prefs


def save(prefs: dict) -> None:
    merged = dict(DEFAULTS)
    for key, value in prefs.items():
        if key in DEFAULTS:
            merged[key] = bool(value) if isinstance(DEFAULTS[key], bool) else str(value)
    try:
        with open(PREFS_FILE, "w", encoding="utf-8") as fp:
            json.dump(merged, fp, ensure_ascii=False)
    except OSError:
        pass


def get(key: str):
    return load().get(key, DEFAULTS.get(key, False))


def set_value(key: str, value) -> None:
    prefs = load()
    prefs[key] = value
    save(prefs)
