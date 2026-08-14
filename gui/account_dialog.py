"""서버 계정 만들기 창.

왜 창으로 만드는가: 예전에는 채팅창에 `/register 비밀번호 이메일`을 치게 했다. 그 줄은
채널로 나가지 않고 서버 서비스에게만 가지만(측정으로 확인), 사람 입장에서는

- 비밀번호가 **입력창에 그대로 보이고**(가려지지 않는다)
- 지웠는지 신경 써야 하며
- 오타로 엉뚱한 명령이 될까 봐 불안하다

그래서 다른 프로그램처럼 가입 창을 띄운다. 비밀번호는 ●●●로 가려지고, 확인란으로 오타를
막고, 무엇을 하는 것인지 화면에서 설명한다.

**암호화되지 않은 연결이면 크게 경고한다.** 지금 기본 접속(6667)은 평문이라 같은
와이파이에 있는 사람이 들여다볼 수 있다. 같은 서버의 6697은 TLS 1.3이 열려 있다(실측).
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout,
                               QWidget)

from gui.theme import DEFAULT_SSL_PORT
from gui.themed_dialogs import ThemedDialog

MIN_PASSWORD_LEN = 6


class AccountDialog(ThemedDialog):
    """계정 만들기에 필요한 것만 받는다(비밀번호, 확인, 이메일)."""

    def __init__(self, nickname: str, encrypted: bool, parent=None):
        super().__init__("서버 계정 만들기", "", [("취소", False), ("만들기", True)],
                         default_value=False, parent=parent)
        self.password = ""
        self.email = ""
        self._nickname = nickname
        self._build_form(nickname, encrypted)

    def _build_form(self, nickname: str, encrypted: bool):
        body = self.findChild(QLabel)          # ThemedDialog가 만든 본문 자리
        if body is not None:
            body.setText(
                f"지금 이름 <b>{nickname}</b> 을(를) 서버에 등록합니다.<br>"
                "등록하면 다음 접속부터 비밀번호로 본인 확인이 되고, "
                "인터넷이 바뀌어 이름이 밀려도 바로 되찾습니다.")
            body.setTextFormat(Qt.TextFormat.RichText)

        host = QWidget()
        form = QVBoxLayout(host)
        form.setContentsMargins(0, 8, 0, 0)
        form.setSpacing(6)

        if not encrypted:
            warning = QLabel(
                "⚠ 지금 접속은 <b>암호화되지 않았습니다</b>. 비밀번호가 그대로 오갑니다.<br>"
                f"먼저 로그인 화면에서 '보안 접속'을 켜고 포트를 {DEFAULT_SSL_PORT}로 "
                "바꿔 다시 접속한 뒤 만드는 것을 권합니다.")
            warning.setTextFormat(Qt.TextFormat.RichText)
            warning.setWordWrap(True)
            warning.setObjectName("status_err")
            form.addWidget(warning)

        self.pw_input = QLineEdit()
        self.pw_input.setPlaceholderText(f"비밀번호 ({MIN_PASSWORD_LEN}자 이상)")
        self.pw_input.setEchoMode(QLineEdit.EchoMode.Password)
        form.addWidget(self.pw_input)

        self.pw_confirm = QLineEdit()
        self.pw_confirm.setPlaceholderText("비밀번호 확인")
        self.pw_confirm.setEchoMode(QLineEdit.EchoMode.Password)
        form.addWidget(self.pw_confirm)

        self.email_input = QLineEdit()
        self.email_input.setPlaceholderText("이메일 (서버가 확인 메일을 보낼 수 있습니다)")
        form.addWidget(self.email_input)

        self.hint = QLabel("")
        self.hint.setObjectName("status_err")
        self.hint.setWordWrap(True)
        form.addWidget(self.hint)

        layout = self.layout()
        # 버튼 줄 바로 위에 끼워 넣는다(맨 아래로 가면 버튼 아래에 붙는다)
        layout.insertWidget(max(0, layout.count() - 1), host)

        for button in self.findChildren(QPushButton):
            if button.text() == "만들기":
                button.clicked.disconnect()
                button.clicked.connect(self._try_accept)

    def _try_accept(self):
        password = self.pw_input.text()
        email = self.email_input.text().strip()
        problem = validate(password, self.pw_confirm.text(), email)
        if problem:
            self.hint.setText(problem)
            return
        self.password = password
        self.email = email
        self.result_value = True
        self.accept()


def validate(password: str, confirm: str, email: str) -> str:
    """입력이 쓸 만한지 본다. 문제가 없으면 빈 문자열.

    서버에 보내기 전에 여기서 걸러야 한다 - 서버가 거절하면 그 이유가 영어로 오고,
    사용자는 무엇이 잘못됐는지 알기 어렵다.
    """
    if len(password) < MIN_PASSWORD_LEN:
        return f"비밀번호는 {MIN_PASSWORD_LEN}자 이상이어야 합니다."
    if " " in password:
        return "비밀번호에 공백은 쓸 수 없습니다."
    if password != confirm:
        return "두 비밀번호가 다릅니다."
    if "@" not in email or "." not in email.split("@")[-1] or " " in email:
        return "이메일 주소를 확인해주세요."
    return ""
