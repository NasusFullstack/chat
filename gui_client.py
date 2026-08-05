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
호출부는 여전히 원본 함수를 참조하게 됨(몽키패치가 무효화됨). 대신 각 호출 지점은
그 메서드 "본문 안에서" `import gui_client`를 한 뒤, 실제 호출 시점에
`gui_client.themed_question(...)`처럼 매번 모듈 속성으로 조회해서 씀.

**중요**: 이 `import gui_client`는 반드시 함수/메서드 "본문 안"에 있어야 하고, 절대
파일 맨 위(모듈 최상단)에 두면 안 됨. 처음엔 파일 맨 위에 둬도 될 거라 생각했는데
(gui_client -> gui.main_window -> gui.pages -> gui_client로 이어지는 순환참조가
"sys.modules에 이미 등록된 부분초기화 모듈을 그대로 돌려받으니 안전하다"는 논리),
로컬 개발 환경(CPython 소스 실행)에서는 실제로 통과했지만 **PyInstaller로 빌드한
실행 파일에서 사용자가 "cannot import name 'X' from partially initialized module"
크래시를 실제로 겪었음** - PyInstaller의 프로즌 임포터(pyimod02_importers)는 버전에
따라 모듈 최상단의 순환참조를 CPython만큼 관대하게 처리하지 못하는 것으로 보임(로컬
PyInstaller 버전에서는 재현 안 됐지만 CI가 빌드한 실행 파일에서는 크래시가 남 - 즉
이 문제는 PyInstaller 버전에 따라 재현 여부가 갈릴 수 있어 로컬 빌드 테스트만으로는
안심할 수 없음). 함수 본문 안에서의 지연 import는 그 함수가 실제로 호출되는 시점
(=gui_client.py의 모든 import가 완전히 끝난 뒤, 앱이 실제로 동작하는 훨씬 나중 시점)
에만 실행되므로 이 순환참조 위험이 원천적으로 없음 - 앞으로 gui/ 하위 모듈에 새 함수를
추가할 때도 gui_client의 5개 함수를 쓰려면 반드시 이 패턴(본문 안 지연 import)을 따를 것.

ProfileDialog 같은 "클래스"는 이 규칙과 무관함 - 테스트가 패치하는 건 인스턴스의 exec
메서드(클래스 속성)라서, 클래스 객체 자체는 어디서 import하든 항상 같은 객체를 가리키므로
gui/profile_dialog.py처럼 자유롭게 `from gui.profile_dialog import ProfileDialog`로
직접 가져와도 안전함.
"""
import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

import server_registry
import irc_protocol
import error_log
import history_store
import avatar_store
import login_prefs
from version import APP_VERSION

from gui.theme import (
    ADD_TAB_LABEL, APP_TITLE, AVATAR_CELL_PX, AVATAR_GRID_SIZE, AVATAR_LIST_PX,
    AVATAR_MAX_B64_CHARS, AVATAR_MSG_PX, CHANNEL_TAB_FIXED_WIDTH, CONNECT_TIMEOUT_MS,
    DEFAULT_PLAIN_PORT, DEFAULT_SSL_PORT, IS_WINDOWS, MENTION_COOLDOWN_SEC, NICKNAME_MAX_LEN,
    STYLE_SHEET, TIMESTAMP_BADGE_FONT_PX, TIMESTAMP_BADGE_HEIGHT_PX, UNREAD_BLINK_COLOR,
    UNREAD_BLINK_COUNT, UNREAD_BLINK_INTERVAL_MS,
)
from gui.helpers import (
    _MENTION_TOKEN_RE, _app_dir, _decode_avatar_pixmap,
    _find_app_icon, _find_default_cert, _format_ts, _friendly_connection_error,
    _hashed_avatar_pixmap, _linkify, _titlebar_icon,
)
from gui.themed_dialogs import (
    ThemedDialog, ThemedInputDialog, _MiniTitleBar, themed_get_text, themed_question,
    themed_warning,
)
from gui.mention_alerts import _flash_taskbar_icon, _shake_window
from gui.network import ChatClient
from gui.widgets import ChannelLogView, MessageWidget, _build_system_label
from gui.title_bar import TitleBar
from gui.profile_dialog import ColorPickerDialog, ProfileDialog, _AvatarGridWidget
from gui.pages import ChannelPage, ChatPage, LoginPage
from gui.startup_page import StartupPage
from gui.main_window import MainWindow

if IS_WINDOWS:
    import ctypes  # 작업표시줄 아이콘 그룹핑(AppUserModelID)에만 사용


def main():
    # 배포된 앱은 콘솔이 없어서 예외 트레이스백이 어디에도 안 남는다. PySide6는 슬롯 안에서
    # 예외가 나도 앱을 죽이지 않고 넘어가기 때문에, 화면 갱신이 중간에 끊겨 "채팅과 참여자가
    # 빈 공간으로 보이는" 식의 증상만 남고 원인은 알 수 없게 된다. 파일로 남겨둔다.
    error_log.install()

    if IS_WINDOWS:
        # 작업표시줄이 python.exe 기본 아이콘 대신 우리 아이콘/앱 이름으로 묶이게 함
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("FriendChat.GuiClient")
        except Exception:  # noqa: BLE001
            pass

    app = QApplication(sys.argv)
    app.setStyleSheet(STYLE_SHEET)
    # 창을 닫아도 프로그램이 끝나지 않게 함(트레이에 남아 계속 메시지를 받는다).
    # 이걸 안 끄면 창을 숨기는 순간 Qt가 "마지막 창이 닫혔다"고 보고 종료해버린다.
    # 실제 종료는 트레이 메뉴의 '종료'(MainWindow.quit_app)가 담당한다
    app.setQuitOnLastWindowClosed(False)

    icon_path = _find_app_icon()
    if icon_path:
        app.setWindowIcon(QIcon(icon_path))

    window = MainWindow()
    if icon_path:
        window.set_window_icon(QIcon(icon_path))
    window.show()

    # 창(시작화면)을 먼저 띄운 뒤에 업데이트를 확인/적용함. 반대로 하면 업데이트가 계속
    # 실패하는 환경에서 앱 화면을 한 번도 못 보여주고 끝남(실제 사고 이력).
    # 실제 진행은 MainWindow가 시작화면에 표시하면서 처리함.
    window.start_boot_sequence()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
