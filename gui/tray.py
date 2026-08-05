"""작업표시줄 오른쪽 알림 영역(트레이)에 뜨는 아이콘과 그 메뉴.

이걸 두는 이유는 두 가지다.

1. **창을 닫아도 계속 받기** - 메신저는 창을 닫았다고 나가버리면 곤란하다. 창은 숨기고
   연결은 유지하다가, 트레이 메뉴에서 '종료'를 눌러야 실제로 끝난다.
2. **새 메시지 알림** - 창을 안 보고 있을 때 오른쪽 아래에 누가 뭐라고 했는지 띄운다.

알림은 Qt가 운영체제에 맡긴다(QSystemTrayIcon.showMessage). 그래서 윈도우에서는 평소 보던
그 알림 모양 그대로 나온다 - 우리가 창을 직접 그리면 모양이 겉돌고, 알림 센터에도 안 쌓인다.

바깥으로 나가는 신호:
  open_requested()   아이콘을 누르거나 메뉴에서 '열기'
  quit_requested()   메뉴에서 '종료' (진짜 종료는 창 쪽에서 처리)
"""
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

import app_prefs
from gui.theme import APP_TITLE

# 알림에 넣을 본문 길이 상한. 길면 운영체제가 알아서 자르지만, 그 전에 우리가 잘라야
# 줄바꿈이 이상하게 끊기지 않는다
NOTIFY_BODY_MAX = 120
NOTIFY_TIMEOUT_MS = 5000


class TrayIcon(QObject):
    open_requested = Signal()
    quit_requested = Signal()

    def __init__(self, icon, parent=None):
        super().__init__(parent)
        self.available = QSystemTrayIcon.isSystemTrayAvailable()
        if not self.available:
            # 트레이가 없는 환경(일부 리눅스 데스크톱 등) - 아무 것도 안 하고 조용히 넘어간다.
            # 이 경우 창을 닫으면 그냥 종료되도록 창 쪽에서 available을 보고 판단한다
            self._tray = None
            return

        self._tray = QSystemTrayIcon(icon, parent)
        self._tray.setToolTip(APP_TITLE)
        self._tray.activated.connect(self._on_activated)

        menu = QMenu()
        menu.addAction("열기", self.open_requested.emit)
        menu.addSeparator()
        self._notify_action = menu.addAction("알림 표시")
        self._notify_action.setCheckable(True)
        self._notify_action.setChecked(app_prefs.get("notifications"))
        self._notify_action.toggled.connect(self._on_notify_toggled)
        menu.addAction("환경설정...", self._open_settings)
        menu.addSeparator()
        menu.addAction("종료", self.quit_requested.emit)
        self._menu = menu   # 참조를 들고 있어야 메뉴가 사라지지 않음
        self._tray.setContextMenu(menu)
        self._tray.show()

    # ---------------- 사용자 조작 ----------------

    def _on_activated(self, reason):
        # 왼쪽 클릭/더블클릭이면 창을 다시 보여줌(오른쪽 클릭은 메뉴라 그대로 둔다)
        if reason in (QSystemTrayIcon.ActivationReason.Trigger,
                      QSystemTrayIcon.ActivationReason.DoubleClick):
            self.open_requested.emit()

    def _on_notify_toggled(self, checked: bool):
        app_prefs.set_value("notifications", checked)

    def _open_settings(self):
        from gui.settings_dialog import SettingsDialog

        dialog = SettingsDialog()
        if dialog.exec():
            self.refresh_from_prefs()

    def refresh_from_prefs(self):
        """설정 창에서 바꾼 값을 메뉴 체크 표시에 반영."""
        if self._tray is None:
            return
        self._notify_action.blockSignals(True)
        self._notify_action.setChecked(app_prefs.get("notifications"))
        self._notify_action.blockSignals(False)

    # ---------------- 알림 ----------------

    def notify(self, sender: str, text: str, channel: str = ""):
        """새 메시지를 오른쪽 아래에 띄움. 설정이 꺼져 있으면 아무 것도 안 함."""
        if self._tray is None or not app_prefs.get("notifications"):
            return
        body = text.strip()
        if len(body) > NOTIFY_BODY_MAX:
            body = body[:NOTIFY_BODY_MAX - 1] + "…"
        title = f"{sender} ({channel})" if channel else sender
        self._tray.showMessage(title, body, QSystemTrayIcon.MessageIcon.Information,
                               NOTIFY_TIMEOUT_MS)

    def set_icon(self, icon):
        if self._tray is not None:
            self._tray.setIcon(icon)

    def hide(self):
        if self._tray is not None:
            self._tray.hide()
