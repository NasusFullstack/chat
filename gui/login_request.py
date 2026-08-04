"""로그인 화면 입력값을 검사해서 '접속 요청' 한 덩어리로 만든다.

위젯도 소켓도 모르는 순수 함수라 Qt 없이 시험할 수 있다. 예전에는 이 검사가 MainWindow의
_handle_login_submit 안에 접속 절차와 뒤섞여 있어서, "무엇이 잘못된 입력인가"를 확인하려면
소켓을 여는 코드까지 같이 읽어야 했다.

프로토콜마다 필수 항목이 다르다는 게 핵심이다:
- 실제 IRC 서버는 비밀번호 없이 접속하는 게 보통이다(NickServ 비번은 선택)
- 우리 커스텀 서버는 계정 개념이 있어 비밀번호가 반드시 있어야 한다
"""
from dataclasses import dataclass

IRC = "irc"


@dataclass(frozen=True)
class LoginRequest:
    """접속에 필요한 값 한 묶음. 검사를 통과한 것만 만들어진다."""
    protocol: str
    host: str
    port: int
    user_id: str
    password: str
    cert_path: str
    use_ssl: bool
    auto_login: bool

    @property
    def is_irc(self) -> bool:
        return self.protocol == IRC

    @property
    def mode_label(self) -> str:
        return "SSL" if self.use_ssl else "평문(암호화 없음)"


def parse_login_values(values: dict) -> tuple[LoginRequest | None, str]:
    """로그인 화면 입력값 -> (요청, "") 또는 (None, 사용자에게 보여줄 이유)."""
    protocol = values.get("protocol", "custom")
    host = (values.get("host") or "").strip()
    port_text = (values.get("port") or "").strip()
    user_id = (values.get("user_id") or "").strip()
    password = values.get("password") or ""

    if protocol == IRC:
        if not host or not port_text or not user_id:
            return None, "서버 주소/포트/닉네임을 입력하세요."
    elif not host or not port_text or not user_id or not password:
        return None, "모든 항목을 입력하세요."

    try:
        port = int(port_text)
    except ValueError:
        return None, "포트는 숫자여야 합니다."

    return LoginRequest(
        protocol=protocol,
        host=host,
        port=port,
        user_id=user_id,
        password=password,
        cert_path=values.get("cert_path") or "",
        use_ssl=bool(values.get("ssl")),
        auto_login=bool(values.get("auto_login")),
    ), ""
