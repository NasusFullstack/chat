"""트레이 아이콘 - 창을 닫아도 유지, 알림, 환경설정.

트레이/알림은 운영체제가 그리는 부분이라 화면으로는 확인할 수 없다. 대신 우리가 정하는
규칙(언제 알릴지, 닫으면 어떻게 되는지, 설정이 지켜지는지)을 확인한다.
"""
import os as _os
import sys as _sys

_HERE = _os.path.dirname(_os.path.abspath(__file__))
_REPO = _os.path.dirname(_HERE)

_os.environ["QT_QPA_PLATFORM"] = "offscreen"
_sys.path.insert(0, _REPO)
_sys.path.insert(0, _HERE)

import tempfile

from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QApplication

import app_prefs

app_prefs.PREFS_FILE = _os.path.join(tempfile.gettempdir(), "test_app_prefs.json")
if _os.path.exists(app_prefs.PREFS_FILE):
    _os.remove(app_prefs.PREFS_FILE)

app = QApplication.instance() or QApplication([])
import gui_client as g
from gui.settings_dialog import SettingsDialog

checks = []

# ---------- 1) 설정 저장 ----------
checks.append(("기본값은 알림 켜짐", app_prefs.get("notifications")))
checks.append(("기본값은 닫으면 트레이로", app_prefs.get("close_to_tray")))
app_prefs.set_value("notifications", False)
checks.append(("끈 값이 저장됨", not app_prefs.get("notifications")))
checks.append(("다른 설정은 안 건드림", app_prefs.get("close_to_tray")))
app_prefs.set_value("notifications", True)

# ---------- 2) 환경설정 창 ----------
dialog = SettingsDialog()
dialog.notify_check.setChecked(False)
dialog.tray_check.setChecked(True)
dialog._save()
checks.append(("환경설정에서 끄면 저장됨", not app_prefs.get("notifications")))
checks.append(("환경설정에서 켠 값도 저장됨", app_prefs.get("close_to_tray")))

cancel_dialog = SettingsDialog()
cancel_dialog.notify_check.setChecked(True)
cancel_dialog.reject()
checks.append(("취소하면 저장 안 됨", not app_prefs.get("notifications")))
app_prefs.set_value("notifications", True)

# ---------- 3) 창 닫기 = 트레이로 ----------
window = g.MainWindow()
window.show()
for _ in range(4):
    app.processEvents()

notified = []
window._tray.notify = lambda sender, text, channel="": notified.append((sender, text))
window._tray.available = True   # 오프스크린에는 진짜 트레이가 없으므로 있다고 가정

event = QCloseEvent()
window.closeEvent(event)
checks.append(("창을 닫아도 종료되지 않음(닫기가 무시됨)", not event.isAccepted()))
checks.append(("창은 숨겨짐", not window.isVisible()))
checks.append(("트레이에 남아있다고 알려줌", bool(notified)))

window.show_from_tray()
for _ in range(4):
    app.processEvents()
checks.append(("트레이에서 다시 열면 창이 보임", window.isVisible()))

# 설정을 끄면 예전처럼 그냥 닫혀야 함
app_prefs.set_value("close_to_tray", False)
event2 = QCloseEvent()
window.closeEvent(event2)
checks.append(("설정을 끄면 창 닫기가 그대로 진행됨", event2.isAccepted()))
app_prefs.set_value("close_to_tray", True)

# ---------- 4) 알림 규칙 ----------
notified.clear()
window.show()
window.activateWindow()
for _ in range(4):
    app.processEvents()
window.notify_new_message("지현", "안녕", "#일반")
seen_while_active = list(notified)

window.hide()
for _ in range(4):
    app.processEvents()
window.notify_new_message("지현", "이건 알림 떠야 함", "#일반")
checks.append(("창이 안 보일 때는 알림이 뜬다", len(notified) > len(seen_while_active)))

app_prefs.set_value("notifications", False)
notified.clear()
window._tray.notify = lambda sender, text, channel="": (
    notified.append((sender, text)) if app_prefs.get("notifications") else None)
window.notify_new_message("지현", "설정 껐으니 안 떠야 함", "#일반")
checks.append(("설정을 끄면 알림이 안 뜬다", not notified))
app_prefs.set_value("notifications", True)

print("=== 검증 결과 (트레이/알림/환경설정) ===")
all_ok = True
for name, ok in checks:
    print(f"[{'OK' if ok else 'FAIL'}] {name}")
    all_ok = all_ok and ok
print("\n전체 통과:", all_ok)
_sys.exit(0 if all_ok else 1)
