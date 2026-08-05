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
checks.append(("처음 닫을 때는 트레이에 남아있다고 알려줌", bool(notified)))

# 두 번째부터는 안내가 안 떠야 함(매번 뜨면 성가심)
notified.clear()
window.show()
for _ in range(3):
    app.processEvents()
event_again = QCloseEvent()
window.closeEvent(event_again)
checks.append(("두 번째부터는 안내가 안 뜬다", not notified))
checks.append(("두 번째에도 창은 여전히 트레이로 내려간다",
               not event_again.isAccepted() and not window.isVisible()))

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

# ---------- 5) 알림 본문 (누가 / 뭐라고) ----------
from chat_core.commands import format_emoji
from gui.tray import notification_body

plain = notification_body("새 버전 올렸어?")
checks.append(("평범한 메시지는 그대로 보인다", plain == "새 버전 올렸어?"))

mixed = notification_body("이거 봐 " + format_emoji("https://example.com/dog.gif"))
checks.append((f"이모티콘은 주소 대신 말로 바뀐다 -> {mixed!r}",
               "example.com" not in mixed and "(이모티콘)" in mixed))

only = notification_body(format_emoji("https://example.com/cat.png"))
checks.append(("이모티콘만 보낸 경우도 주소가 안 뜬다",
               only == "(이모티콘)"))

long_body = notification_body("가" * 300)
checks.append((f"긴 메시지는 20자에서 잘리고 ...이 붙는다 -> {long_body!r}",
               long_body == "가" * 20 + "..."))

short_body = notification_body("짧은 말")
checks.append(("짧은 메시지에는 ...이 안 붙는다", short_body == "짧은 말"))

# ---------- 6) 연달아 와도 알림이 쌓이지 않고 최신 하나만 ----------
from PySide6.QtCore import QEventLoop, QTimer as _QTimer
from gui.tray import NOTIFY_COALESCE_MS, TrayIcon

shown = []


class FakeToast:
    """진짜 팝업 대신 호출만 받아 적는다(뜨는 모양 자체는 화면으로 확인해야 함)."""

    def show_message(self, title, body):
        shown.append((title, body))

    def set_icon(self, icon):
        pass

    def hide(self):
        pass


tray = TrayIcon(window.windowIcon(), window)
# 알림은 이제 우리 팝업(gui/toast.py)으로 뜨므로 거기에 가짜를 꽂는다
tray._toast = FakeToast()
app_prefs.set_value("notifications", True)
if True:

    # 한꺼번에 몰려온 상황
    tray.notify("지현", "첫 번째", "#일반")
    tray.notify("지현", "두 번째", "#일반")
    tray.notify("태호", "세 번째", "#일반")

    loop = QEventLoop()
    _QTimer.singleShot(NOTIFY_COALESCE_MS + 300, loop.quit)
    loop.exec()

    checks.append((f"연달아 3건이 와도 알림은 한 번만 뜬다({len(shown)}회)", len(shown) == 1))
    if shown:
        title, body = shown[0]
        checks.append((f"가장 최근 메시지를 보여준다 -> {body!r}", "세 번째" in body))
        checks.append((f"제목은 마지막 보낸 사람 -> {title!r}", title.startswith("태호")))
        checks.append(("나머지가 몇 건인지 알려준다", "외 2건" in body))
        checks.append(("여러 사람이면 인원도 알려준다", "2명" in body))

    # 시간이 지난 뒤 온 메시지는 따로 뜬다
    shown.clear()
    tray.notify("민수", "나중에 온 것", "#일반")
    loop2 = QEventLoop()
    _QTimer.singleShot(NOTIFY_COALESCE_MS + 300, loop2.quit)
    loop2.exec()
    checks.append(("나중에 온 메시지는 새로 뜬다", len(shown) == 1))

print("=== 검증 결과 (트레이/알림/환경설정) ===")
all_ok = True
for name, ok in checks:
    print(f"[{'OK' if ok else 'FAIL'}] {name}")
    all_ok = all_ok and ok
# --- 알림에 무엇까지 보여줄지 네 가지 (순수 함수라 화면 없이 검사) ---
from gui.tray import compose_notification   # noqa: E402

one = [("앨리스", "비밀 이야기", "#일반")]
full = compose_notification(one, True, "none")
only_sender = compose_notification(one, False, "sender")
only_msg = compose_notification(one, False, "message")
nothing = compose_notification(one, False, "none")
checks.append((f"전부 표시{full}", "앨리스" in full[0] and "비밀" in full[1]))
checks.append((f"사람만 표시{only_sender}", "앨리스" in only_sender[0] and "비밀" not in only_sender[1]))
checks.append((f"메시지만 표시{only_msg}", "앨리스" not in only_msg[0] and "비밀" in only_msg[1]))
checks.append((f"모두 숨김{nothing}", "앨리스" not in nothing[0] and "비밀" not in nothing[1]))

many = [("앨리스", "안녕", "#일반"), ("밥", "나도", "#일반"), ("앨리스", "저녁 먹자", "#일반")]
checks.append(("여러 건이면 사람 수까지 알려줌", "2명" in compose_notification(many, True, "none")[1]))
checks.append(("모두 숨김일 때는 건수만", "3건" in compose_notification(many, False, "none")[1]
               and "앨리스" not in compose_notification(many, False, "none")[1]))

# --- 내용 숨김 설정: 알림은 뜨되 누가 뭐라 했는지는 감춘다 ---
app_prefs.set_value("notify_preview", False)
app_prefs.set_value("notify_detail", "none")
shown.clear()
tray.notify("앨리스", "비밀 이야기", "#일반")
tray._flush_pending()
hidden_title, hidden_body = shown[-1] if shown else ("", "")
checks.append(("내용 숨김이어도 알림은 뜬다", bool(shown)))
checks.append((f"보낸 사람이 안 보임({hidden_title})", "앨리스" not in hidden_title))
checks.append((f"내용이 안 보임({hidden_body})", "비밀" not in hidden_body))
checks.append(("대신 새 메시지가 왔다고 알려줌", "새 메시지" in hidden_body))

shown.clear()
for i in range(3):
    tray.notify(f"사람{i}", f"내용{i}", "#일반")
tray._flush_pending()
checks.append((f"여러 건이어도 건수만 알려줌({shown[-1][1] if shown else ''})",
               bool(shown) and "3건" in shown[-1][1] and "사람" not in shown[-1][1]))
app_prefs.set_value("notify_preview", True)

# --- 환경설정 창: 위가 꺼지면 아래가 흐려진다 ---
dlg = SettingsDialog()
dlg.notify_check.setChecked(True)
dlg.preview_check.setChecked(True)
app.processEvents()
checks.append(("전부 표시 중이면 세부 선택은 잠김",
               not any(r.isEnabled() for r in dlg._detail_radios)))
dlg.preview_check.setChecked(False)
app.processEvents()
checks.append(("전부 표시를 끄면 세부 선택이 열림",
               all(r.isEnabled() for r in dlg._detail_radios)))
dlg.notify_check.setChecked(False)
app.processEvents()
checks.append(("알림 자체를 끄면 아래가 전부 잠김",
               not dlg.preview_check.isEnabled()
               and not any(r.isEnabled() for r in dlg._detail_radios)))
checks.append(("고른 세부 항목을 읽을 수 있음", dlg.selected_detail() in ("sender", "message", "none")))
dlg.deleteLater()

# --- 알림 팝업 닫기 버튼 ---
from gui.toast import ToastPopup   # noqa: E402

popup = ToastPopup()
opened = []
popup.clicked.connect(lambda: opened.append(1))
popup.show_message("앨리스", "안녕")
for _ in range(3):
    app.processEvents()
checks.append(("알림이 떠 있음", popup.isVisible()))
popup.close_btn.clicked.emit()
for _ in range(3):
    app.processEvents()
checks.append(("닫기를 누르면 알림이 사라짐", not popup.isVisible()))
checks.append(("닫기는 창을 열지 않음(내용만 치움)", not opened))
checks.append(("닫은 뒤 자동 숨김 타이머도 멈춤", not popup._hide_timer.isActive()))

print("\n전체 통과:", all_ok)
_sys.exit(0 if all_ok else 1)
