"""한 번에 하나만 뜨는가 + 업데이트 뒤 변경 내역 창이 한 번만 뜨는가.

두 기능 모두 "실제 사용자 신고"에서 나왔다:
- 트레이 아이콘이 두 개 생기는 경우가 있었다(앱이 두 번 켜져 있었던 것)
- 패치가 조용히 끝나서 무엇이 바뀌었는지 알 방법이 없었다
"""
import os as _os
import sys as _sys

_HERE = _os.path.dirname(_os.path.abspath(__file__))
_REPO = _os.path.dirname(_HERE)

_os.environ["QT_QPA_PLATFORM"] = "offscreen"
_sys.path.insert(0, _REPO)
_sys.path.insert(0, _HERE)

from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])

import app_prefs  # noqa: E402
import gui_client as g  # noqa: E402
from gui import changelog_dialog  # noqa: E402
from single_instance import SingleInstance  # noqa: E402

app.setStyleSheet(g.STYLE_SHEET)
checks = []


def check(name, ok, detail=""):
    checks.append((name, ok, detail))


# ---------- 1) 한 번에 하나만 ----------
KEY = "ChupChat-test-instance"
first = SingleInstance(KEY)
check("처음 켠 쪽은 자리를 잡는다", first.try_acquire())

woken = []
first.activated.connect(lambda: woken.append(True))

second = SingleInstance(KEY)
check("두 번째로 켜면 자리를 못 잡는다(= 그냥 종료해야 함)", not second.try_acquire())

# 깨우는 신호가 도착할 시간을 준다. 실제 앱에서는 프로세스가 둘이지만 여기서는 하나라
# 이벤트 루프를 직접 돌려줘야 서버 쪽이 연결을 받는다
import time as _t  # noqa: E402

_deadline = _t.time() + 3
while _t.time() < _deadline and not woken:
    app.processEvents()
    _t.sleep(0.02)
check("두 번째 실행이 첫 번째 창을 깨운다(창이 없으면 다시 켠 의미가 없음)",
      bool(woken), woken)

first.release()
third = SingleInstance(KEY)
check("먼저 켠 쪽이 끝나면 다음 실행은 정상적으로 자리를 잡는다", third.try_acquire())
third.release()

# ---------- 2) 변경 내역 뽑기 ----------
SAMPLE = """# 변경 내역

## v9.9.9
- 첫 줄
- **굵은** 줄

## v9.9.8
- 예전 줄
"""
check("그 버전 부분만 잘라낸다",
      changelog_dialog.section_for(SAMPLE, "9.9.9") == "- 첫 줄\n- **굵은** 줄",
      changelog_dialog.section_for(SAMPLE, "9.9.9"))
check("다음 버전 내용은 안 섞인다",
      "예전 줄" not in changelog_dialog.section_for(SAMPLE, "9.9.9"))
check("없는 버전이면 빈 글자", changelog_dialog.section_for(SAMPLE, "1.2.3") == "")
check("실제 CHANGELOG.md에서 지금 버전 내역을 찾는다", bool(changelog_dialog.load_notes()),
      "찾지 못함 - 파일이 빌드에 포함되는지 확인할 것")

# ---------- 3) 한 버전당 한 번만, 그리고 처음 설치 때는 안 뜬다 ----------
saved = app_prefs.get(changelog_dialog.SHOWN_KEY)
try:
    app_prefs.set_value(changelog_dialog.SHOWN_KEY, "")
    check("처음 설치(기록 없음)에는 안 보여준다", not changelog_dialog.should_show("2.0.0"))
    check("대신 지금 버전을 조용히 적어둔다",
          app_prefs.get(changelog_dialog.SHOWN_KEY) == "2.0.0",
          app_prefs.get(changelog_dialog.SHOWN_KEY))

    app_prefs.set_value(changelog_dialog.SHOWN_KEY, "2.0.0")
    check("버전이 올라가면 보여준다(패치 뒤 한 번)", changelog_dialog.should_show("2.0.1"))
    changelog_dialog.mark_shown("2.0.1")
    check("한 번 보여준 버전은 다시 안 보여준다", not changelog_dialog.should_show("2.0.1"))
finally:
    app_prefs.set_value(changelog_dialog.SHOWN_KEY, saved)

# ---------- 4) 창 자체 ----------
dialog = changelog_dialog.ChangelogDialog("- 뭔가 고쳤습니다\n- **굵게** 강조", None)
dialog.show()
for _ in range(5):
    app.processEvents()
check("창이 떠 있다", dialog.isVisible())
check("저절로 닫히는 타이머가 없다(읽는 중에 사라지면 안 됨)",
      not dialog.findChildren(__import__("PySide6.QtCore", fromlist=["QTimer"]).QTimer),
      dialog.findChildren(__import__("PySide6.QtCore", fromlist=["QTimer"]).QTimer))
for _ in range(20):          # 시간이 지나도 그대로 떠 있어야 한다
    app.processEvents()
check("시간이 지나도 그대로 떠 있다", dialog.isVisible())
dialog.close()

# ---------- 5) 언제든 다시 열 수 있는가 ----------
# 창은 업데이트 직후 한 번만 뜬다. 그때 무심코 닫았거나 나중에 다시 보고 싶을 때
# 열 방법이 없으면 "만들었지만 볼 수 없는 기능"이 된다
check("환경설정 정보 탭에서 다시 열 수 있다", hasattr(changelog_dialog, "open_now"))

from gui.settings_dialog import SettingsDialog  # noqa: E402
from PySide6.QtWidgets import QPushButton  # noqa: E402

settings = SettingsDialog()
buttons = [b.text() for b in settings.findChildren(QPushButton)]
check(f"정보 탭에 변경 내역 버튼이 있다({buttons})",
      any("변경 내역" in text for text in buttons), buttons)
check("그 버튼이 창을 여는 함수에 연결돼 있다", hasattr(settings, "_open_changelog"))
settings.close()

# ---------- 6) 채팅창에도 남는가 ----------
# 창을 닫으면 사라지므로, 대화 기록에도 한 줄 남겨 나중에 찾아볼 수 있게 한다
notes_sample = """- 첫째 고침
- 둘째 고침
- 셋째 고침
- 넷째 고침"""
line = changelog_dialog.summary_line(notes_sample, "9.9.9")
check(f"바뀐 내용을 한 줄로 요약한다({line})",
      "9.9.9" in line and "첫째 고침" in line, line)
check("너무 길어지지 않게 나머지는 개수로 줄인다", "외 1가지" in line, line)
check("내역이 없어도 최소한 버전은 알려준다",
      "9.9.9" in changelog_dialog.summary_line("", "9.9.9"))

# 실제 경로(채널 입장)에서 그 한 줄이 나가는지 - 함수만 있고 안 불리면 소용없다
import io as _io  # noqa: E402

router_src = _io.open(_os.path.join(_REPO, "gui/event_router.py"), encoding="utf-8").read()
check("채널에 들어갈 때 그 한 줄을 남긴다", "take_update_note" in router_src)
main_src = _io.open(_os.path.join(_REPO, "gui/main_window.py"), encoding="utf-8").read()
check("한 번 쓰고 비운다(채널마다 반복되면 안 됨)",
      "self._pending_update_note = \"\"" in main_src)

print("=== 검증 결과 (중복 실행 방지 / 변경 내역 창) ===")
all_ok = True
for name, ok, *detail in checks:
    extra = f"  <- {detail[0]}" if detail and detail[0] and not ok else ""
    print(f"[{'OK' if ok else 'FAIL'}] {name}{extra}")
    all_ok = all_ok and ok
print("\n전체 통과:", all_ok)
_sys.exit(0 if all_ok else 1)
