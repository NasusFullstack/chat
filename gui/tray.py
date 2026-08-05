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
from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

import app_prefs
from chat_core.commands import split_emoji_parts
from gui.theme import APP_TITLE
from gui.toast import ToastPopup

# 알림 본문 길이 상한. 알림은 "누가 뭐라고 했는지" 훑어보는 용도라 짧아야 한다 -
# 길면 알림 자체가 화면을 오래 가리고, 어차피 다 읽을 거면 창을 열게 된다
NOTIFY_BODY_MAX = 20

# 연달아 온 메시지를 하나로 묶는 시간. 카톡/라인처럼 알림이 세로로 여러 개 쌓이지 않고
# 항상 '가장 최근 것 하나'만 보이게 하기 위함이다. 이 시간 안에 더 오면 앞의 것을 대체한다.
# 너무 길면 알림이 굼떠 보이고, 너무 짧으면 연속 대화에서 알림이 우수수 쌓인다
NOTIFY_COALESCE_MS = 700

# 내용을 숨기는 설정일 때 대신 보여줄 문구. 누가 무슨 말을 했는지는 감추되 "왔다"는 사실은
# 알려야 알림을 켜둔 의미가 있다
HIDDEN_TITLE = APP_TITLE
HIDDEN_BODY = "새 메시지가 도착했습니다"


def compose_notification(items: list, preview: bool, detail: str) -> tuple[str, str]:
    """모아둔 메시지들로 알림 제목과 본문을 만든다(위젯을 모르는 순수 함수라 시험하기 쉽다).

    보여주는 정도는 네 가지다:
      preview=True   보낸 사람과 내용 둘 다
      detail=sender  누가 보냈는지만 (내용은 가림)
      detail=message 내용만 (누가 보냈는지는 가림)
      detail=none    둘 다 가림 - "새 메시지가 도착했습니다"만

    여러 건이 묶였을 때: 보여주는 게 있으면 가장 최근 것 + "외 N건", 다 가렸으면 건수만.
    """
    sender, text, channel = items[-1]          # 가장 최근 메시지를 보여줌
    show_sender = preview or detail == "sender"
    show_body = preview or detail == "message"

    if show_sender:
        title = f"{sender} ({channel})" if channel else sender
    else:
        title = HIDDEN_TITLE

    if show_body:
        body = notification_body(text)
    else:
        body = HIDDEN_BODY

    if len(items) > 1:
        others = len(items) - 1
        if not show_sender and not show_body:
            return title, f"{HIDDEN_BODY} ({len(items)}건)"
        senders = {who for who, _, _ in items}
        # 보낸 사람을 보여주는 중일 때만 몇 명인지가 뜻이 있다
        if show_sender and len(senders) > 1:
            extra = f"외 {others}건 · {len(senders)}명"
        else:
            extra = f"외 {others}건"
        body = f"{body}  ({extra})"
    return title, body


def notification_body(text: str) -> str:
    """알림 본문으로 쓸 글자.

    이모티콘은 메시지 안에 '표시로 감싼 주소'로 들어 있어서, 그대로 띄우면 알림에 긴 주소가
    노출된다. 사람이 읽을 수 있는 말로 바꾼다.
    """
    pieces = []
    for kind, value in split_emoji_parts(text):
        if kind == "emoji":
            pieces.append("(이모티콘)")
        else:
            pieces.append(value)
    body = " ".join(" ".join(pieces).split())   # 이어 붙이며 생긴 공백 정리
    if len(body) > NOTIFY_BODY_MAX:
        body = body[:NOTIFY_BODY_MAX] + "..."
    return body


class TrayIcon(QObject):
    open_requested = Signal()
    quit_requested = Signal()

    def __init__(self, icon, parent=None):
        super().__init__(parent)
        # 알림은 운영체제 기본 알림 대신 우리가 그린 팝업으로 띄운다(gui/toast.py 설명 참고).
        # 누르면 창을 열어주는 것까지 같은 신호로 이어붙인다
        self._toast = ToastPopup(icon)
        self._toast.clicked.connect(self.open_requested.emit)
        # 짧은 시간에 몰려온 메시지를 하나로 묶기 위한 대기열.
        # 트레이가 없는 환경에서도 만들어 둔다 - 있고 없고에 따라 코드가 갈리면
        # 그 경로만 시험이 안 되고, 나중에 트레이가 생겨도 대응이 안 된다
        self._pending: list[tuple[str, str, str]] = []
        self._coalesce = QTimer(self)
        self._coalesce.setSingleShot(True)
        self._coalesce.timeout.connect(self._flush_pending)

        self.available = QSystemTrayIcon.isSystemTrayAvailable()
        if not self.available:
            # 트레이가 없는 환경(일부 리눅스 데스크톱 등) - 아무 것도 안 하고 조용히 넘어간다.
            # 이 경우 창을 닫으면 그냥 종료되도록 창 쪽에서 available을 보고 판단한다
            self._tray = None
            return

        self._tray = QSystemTrayIcon(icon, parent)
        self._tray.setToolTip(APP_TITLE)
        self._tray.activated.connect(self._on_activated)

        # 알림 켜고 끄기는 여기 두지 않는다 - 환경설정 창에 계층으로 정리돼 있고(알림 표시 ->
        # 내용 표시 -> 무엇까지), 같은 설정이 두 곳에 있으면 한쪽만 고쳐져 어긋난다.
        # 메뉴는 '열기 / 환경설정 / 종료'로만 둔다
        menu = QMenu()
        menu.addAction("열기", self.open_requested.emit)
        menu.addSeparator()
        menu.addAction("환경설정...", self.open_settings)
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

    def open_settings(self):
        """환경설정 창. 트레이 메뉴와 채널 목록 아래 톱니바퀴가 같이 쓴다."""
        from gui.settings_dialog import SettingsDialog

        dialog = SettingsDialog()
        dialog.exec()

    # ---------------- 알림 ----------------

    def notify(self, sender: str, text: str, channel: str = ""):
        """새 메시지를 오른쪽 아래에 띄움. 설정이 꺼져 있으면 아무 것도 안 함.

        제목은 "보낸사람 (#채널)", 본문은 메시지 내용이다.
        """
        if not app_prefs.get("notifications"):
            return
        # 바로 띄우지 않고 잠깐 모은다. 연달아 오면 앞의 것을 대체해서, 우리 알림이
        # 세로로 여러 개 쌓이지 않고 항상 최신 하나만 보이게 한다(카톡/라인과 같은 방식).
        # 다른 앱 알림과의 배치는 운영체제가 정하는 것이라 우리가 관여하지 않는다
        self._pending.append((sender, text, channel))
        self._coalesce.start(NOTIFY_COALESCE_MS)

    def _flush_pending(self):
        if not self._pending:
            return
        items, self._pending = self._pending, []
        title, body = compose_notification(
            items, app_prefs.get("notify_preview"), app_prefs.get("notify_detail"))
        self._toast.show_message(title, body)

    def set_icon(self, icon):
        self._toast.set_icon(icon)
        if self._tray is not None:
            self._tray.setIcon(icon)

    def hide(self):
        self._toast.hide()
        if self._tray is not None:
            self._tray.hide()
