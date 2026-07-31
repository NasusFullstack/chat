"""
친구 채팅 - GUI 클라이언트 (PySide6)
실행: python gui_client.py
- 진짜 OS 텍스트 입력창을 쓰기 때문에 한글 조합(쌍자음 등) 문제가 없음
- QSslSocket으로 TLS 통신 (asyncio 대신 Qt 자체 네트워킹 사용 - 이벤트 루프 충돌 방지)

이 파일은 gui/ 패키지로 나눠진 모듈들을 한데 모아 재수출하는 진입점(facade) 역할을 함
(PyInstaller 빌드 스크립트와 모든 테스트가 gui_client.py/`import gui_client`를 참조하므로
파일명은 그대로 유지함).

--- 순환참조 노트 (이 파일과 gui/ 하위 모듈을 고칠 때 반드시 읽을 것) ---
기존 테스트 스크립트들(scratchpad 아래)이 `import gui_client as g`한 뒤 아래 5개 함수를
`g.<이름> = 가짜함수`로 직접 몽키패치해서 진짜 확인창/알림 없이 동작을 검증함:
themed_get_text, themed_question, themed_warning, _flash_taskbar_icon, _shake_window

이 5개는 실제로는 gui/themed_dialogs.py, gui/mention_alerts.py에 정의돼있고, 이 파일이
아래에서 import해서 자기 이름공간에 노출함. 이걸 "호출"하는 다른 gui/ 하위 모듈
(pages.py, profile_dialog.py, main_window.py)은 절대 `from gui.themed_dialogs import
themed_question`처럼 직접 바인딩하면 안 됨 - 파이썬은 `from import`한 이름의 원본이
나중에 재할당돼도 그걸 추적하지 않아서, 테스트가 `g.themed_question`을 아무리 패치해도
호출부는 여전히 원본 함수를 참조하게 됨(몽키패치가 무효화됨). 대신 각 모듈은 파일 맨
위에서 `import gui_client`만 해두고, 실제 호출 시점에 `gui_client.themed_question(...)`
처럼 매번 모듈 속성으로 조회해서 씀.

`import gui_client`가 여기서부터 시작된 import 사슬(gui_client -> gui.main_window ->
gui.pages -> gui_client) 안에서 다시 등장하니 순환참조처럼 보이지만 안전함: 파이썬은
모듈 실행을 시작하자마자 sys.modules에 그 모듈을 등록하므로, gui.pages가 로드되는
시점에 `import gui_client`를 실행하면 (아직 이 파일의 아래쪽 import들이 안 끝났더라도)
이미 등록된 gui_client 모듈 객체를 그대로 돌려받음 - gui.pages는 로드 시점(모듈 최상단)
에는 gui_client.themed_question을 건드리지 않고, 실제 사용자가 버튼을 눌러 메서드가
호출되는 훨씬 나중 시점(이 파일의 import가 전부 끝난 뒤)에만 접근하므로 문제없음.

ProfileDialog 같은 "클래스"는 이 규칙과 무관함 - 테스트가 패치하는 건 인스턴스의 exec
메서드(클래스 속성)라서, 클래스 객체 자체는 어디서 import하든 항상 같은 객체를 가리키므로
gui/profile_dialog.py처럼 자유롭게 `from gui.profile_dialog import ProfileDialog`로
직접 가져와도 안전함.
"""
import sys

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QProgressDialog

import server_registry
import irc_protocol
import history_store
import avatar_store
import login_prefs
from version import APP_VERSION

from gui.theme import (
    ADD_TAB_LABEL, APP_TITLE, AVATAR_CELL_PX, AVATAR_GRID_SIZE, AVATAR_LIST_PX,
    AVATAR_MAX_B64_CHARS, AVATAR_MSG_PX, CHANNEL_TAB_FIXED_WIDTH, CONNECT_TIMEOUT_MS,
    DEFAULT_PLAIN_PORT, DEFAULT_SSL_PORT, IS_WINDOWS, MENTION_COOLDOWN_SEC, NICKNAME_MAX_LEN,
    STYLE_SHEET, TIMESTAMP_BADGE_FONT_PX, TIMESTAMP_BADGE_HEIGHT_PX, UNREAD_BLINK_COLOR,
    UNREAD_BLINK_COUNT, UNREAD_BLINK_INTERVAL_MS, UNREAD_DOT_PX,
)
from gui.helpers import (
    _MENTION_TOKEN_RE, _app_dir, _build_unread_dot_icon, _decode_avatar_pixmap,
    _find_app_icon, _find_default_cert, _format_ts, _friendly_connection_error,
    _hashed_avatar_pixmap, _linkify, _titlebar_icon,
)
from gui.themed_dialogs import (
    ThemedDialog, ThemedInputDialog, _MiniTitleBar, themed_get_text, themed_question,
    themed_warning,
)
from gui.mention_alerts import _flash_taskbar_icon, _shake_window
from gui.network import ChatClient
from gui.widgets import ChannelLogView, MessageWidget, _build_system_label, _ChannelTabBar
from gui.title_bar import TitleBar
from gui.profile_dialog import ColorPickerDialog, ProfileDialog, _AvatarGridWidget
from gui.pages import ChannelPage, ChatPage, LoginPage
from gui.main_window import MainWindow

if IS_WINDOWS:
    import ctypes  # 작업표시줄 아이콘 그룹핑(AppUserModelID)에만 사용


def _try_auto_update() -> bool:
    """exe로 빌드되어 실행 중일 때만 새 버전을 확인해서 있으면 적용하고 True를 반환함
    (True면 apply_update_and_relaunch()가 이미 현재 프로세스를 종료시켰거나 곧 종료시킴).
    소스 실행 중이거나, 확인/다운로드에 실패하면 아무 것도 안 하고 조용히 False를 반환해서
    평소처럼 앱이 계속 뜨게 함 - 업데이트 기능 때문에 실행 자체가 막히면 안 되므로."""
    if not getattr(sys, "frozen", False):
        return False

    import updater
    info = updater.check_for_update()
    if info is None:
        return False

    dlg = QProgressDialog(f"새 버전({info['version']})을 받는 중입니다...", None, 0, 100)
    dlg.setWindowTitle("업데이트")
    dlg.setWindowModality(Qt.WindowModality.ApplicationModal)
    dlg.setMinimumDuration(0)
    dlg.setValue(0)
    dlg.show()

    def on_progress(read: int, total: int):
        dlg.setValue(int(read / total * 100) if total else 0)
        QApplication.processEvents()

    try:
        new_package_path = updater.download_update(info["download_url"], progress_cb=on_progress)
    except Exception:  # noqa: BLE001
        dlg.close()
        return False

    dlg.setLabelText("적용 중입니다... 곧 다시 시작됩니다.")
    dlg.setValue(100)
    QApplication.processEvents()
    # 이 시도 자체를 기록해둠 - 이 프로세스는 곧 종료돼서 성공했는지 알 방법이 없지만,
    # 같은 버전으로 너무 여러 번 시도했다면 다음 실행의 check_for_update()가 알아서
    # 더 이상 시도하지 않게 해줌(그래야 이 컴퓨터에서 계속 실패하는 경우에도 "패치만
    # 뜨고 앱은 영영 못 켜는" 무한 루프에 갇히지 않음)
    updater.record_update_attempt(info["version"])
    try:
        updater.apply_update_and_relaunch(new_package_path)  # 성공하면 여기서 프로세스가 끝남
    except Exception:  # noqa: BLE001
        dlg.close()
        return False
    return True


def main():
    if IS_WINDOWS:
        # 작업표시줄이 python.exe 기본 아이콘 대신 우리 아이콘/앱 이름으로 묶이게 함
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("FriendChat.GuiClient")
        except Exception:  # noqa: BLE001
            pass

    app = QApplication(sys.argv)
    app.setStyleSheet(STYLE_SHEET)

    icon_path = _find_app_icon()
    if icon_path:
        app.setWindowIcon(QIcon(icon_path))

    window = MainWindow()
    if icon_path:
        window.set_window_icon(QIcon(icon_path))
    window.show()

    # 창을 먼저 띄운 뒤에 업데이트를 확인/적용함 - 예전에는 반대 순서였는데(업데이트
    # 확인이 끝나야 창을 띄움), 그러면 이 컴퓨터에서만 계속 실패하는 경우 "적용 중입니다"
    # 화면만 뜨고 앱 자체는 한 번도 못 보여준 채로 끝나버림(실제로 한 사용자가 겪음).
    # 창을 먼저 띄워두면 업데이트가 몇 번을 실패하더라도 최소한 그동안은 앱을 계속
    # 쓸 수 있음 - 회로차단기(MAX_UPDATE_ATTEMPTS)와 함께 이중으로 방지함
    QTimer.singleShot(300, _try_auto_update)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
