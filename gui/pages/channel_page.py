"""채널 선택 화면 - 채널 이름과 열쇠를 받아 생성/입장.

주의: 이 모듈은 themed_get_text/themed_question/themed_warning/_flash_taskbar_icon/
_shake_window를 호출하는데, 이 5개는 테스트가 gui_client 모듈에 직접 몽키패치하는 대상이다.
그래서 모듈 맨 위에서 바인딩하지 않고 호출하는 메서드 "본문 안에서" `import gui_client`를 한 뒤
`gui_client.xxx(...)`로 조회한다. 맨 위에 두면 PyInstaller 빌드에서 순환참조로 크래시가 난다
(자세한 이유는 gui_client.py 상단 주석 참고).
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QVBoxLayout, QWidget)


class ChannelPage(QWidget):
    def __init__(self, on_submit, on_back=None):
        super().__init__()
        self.on_submit = on_submit
        self.on_back = on_back
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        box = QVBoxLayout()
        box.setSpacing(8)
        title = QLabel("채널 입장 / 생성")
        title.setObjectName("title")
        box.addWidget(title)

        self.channel_input = QLineEdit()
        self.channel_input.setPlaceholderText("채널명 (예: #친구들)")
        # 채널명/비번 입력창에서 Enter로 바로 입장 (매번 마우스로 버튼 누르지 않게)
        self.channel_input.returnPressed.connect(lambda: self.on_submit("join"))
        box.addWidget(self.channel_input)

        self.key_input = QLineEdit()
        self.key_input.setPlaceholderText("채널 비밀번호 (선택)")
        self.key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_input.returnPressed.connect(lambda: self.on_submit("join"))
        box.addWidget(self.key_input)

        btn_row = QHBoxLayout()
        join_btn = QPushButton("입장")
        join_btn.clicked.connect(lambda: self.on_submit("join"))
        self.create_btn = QPushButton("새 채널 만들기")
        self.create_btn.setObjectName("secondary")
        self.create_btn.clicked.connect(lambda: self.on_submit("create"))
        btn_row.addWidget(join_btn)
        btn_row.addWidget(self.create_btn)
        box.addLayout(btn_row)

        self.status_label = QLabel("")
        self.status_label.setObjectName("status_err")
        self.status_label.setWordWrap(True)
        box.addWidget(self.status_label)

        # 로그인 화면으로 되돌아갈 수단이 없으면 계정을 잘못 골랐을 때 앱을 껐다 켜야 함
        self.back_btn = QPushButton("← 로그인 화면으로")
        self.back_btn.setObjectName("secondary")
        self.back_btn.clicked.connect(lambda: self.on_back() if self.on_back else None)
        box.addWidget(self.back_btn)

        container = QFrame()
        container.setObjectName("card")   # 로그인/채널 화면의 카드 - QSS에서 테두리/여백을 줌
        container.setLayout(box)
        container.setFixedWidth(360)
        layout.addWidget(container)
        self.setLayout(layout)

    def set_mode(self, protocol: str):
        self.create_btn.setVisible(protocol != "irc")

    def show_status(self, text: str, error: bool = True):
        """상태 문구 표시. error=False면 오류색(빨강) 대신 안내색(회색)으로 보여줌.

        구분이 필요한 이유: IRC 서버가 접속 중에 보내는 안내(예: "hostname을 못 찾아
        IP 주소를 대신 씁니다")나 "연결 중..." 같은 진행 문구까지 빨간 글씨로 나와서
        아무 문제가 없는데도 오류가 난 것처럼 보였음.

        기본값을 True로 둔 이유: 새로 추가되는 호출부가 표시를 빠뜨렸을 때 진짜 오류를
        조용히 감추는 쪽보다, 안내가 좀 눈에 띄는 쪽이 안전하기 때문.
        """
        self.status_label.setText(text)
        name = "status_err" if error else "status_info"
        if self.status_label.objectName() != name:
            self.status_label.setObjectName(name)
            # objectName을 바꾸면 스타일시트를 다시 먹여야 색이 반영됨
            self.status_label.style().unpolish(self.status_label)
            self.status_label.style().polish(self.status_label)

    def get_values(self):
        return {
            "channel": self.channel_input.text().strip(),
            "key": self.key_input.text(),
        }
