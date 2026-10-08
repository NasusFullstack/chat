"""로그인 화면 입력값을 검사해서 '접속 요청' 한 덩어리로 만든다.

위젯도 소켓도 모르는 순수 함수라 Qt 없이 시험할 수 있다. 예전에는 이 검사가 MainWindow의
_handle_login_submit 안에 접속 절차와 뒤섞여 있어서, "무엇이 잘못된 입력인가"를 확인하려면
소켓을 여는 코드까지 같이 읽어야 했다.

프로토콜마다 필수 항목이 다르다는 게 핵심이다:
- 실제 IRC 서버는 비밀번호 없이 접속하는 게 보통이다(NickServ 비번은 선택)
- 우리 커스텀 서버는 계정 개념이 있어 비밀번호가 반드시 있어야 한다
- **서버 채팅**은 계정이 있고, 주소는 **우리가 안다** - 사람이 적을 것이 없다
"""
from dataclasses import dataclass

IRC = "irc"
SERVER = "server"

# 서버 채팅은 우리 서버 하나뿐이라 주소를 사람이 적지 않는다. 적게 두면 오타로
# "왜 안 되지"가 생기고, 그 오타를 기억까지 해버린다.
#
# **이 값을 바꾸지 말 것.** 기록·이모티콘·프로필이 놓이는 자리가 (프로토콜, 호스트,
# 포트) 해시로 정해지므로(relay.room_id), 이걸 바꾸면 쌓아둔 것이 통째로 다른 자리로
# 가서 안 보이게 된다. 화면에 보여줄 말은 따로 둔다(SERVER_LABEL)
SERVER_HOST = "chupchat"
SERVER_PORT = 0
SERVER_LABEL = "춥채팅 서버"


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
    def is_server(self) -> bool:
        """우리가 돌리는 서버 채팅인가(IRC 가 아닌 쪽)."""
        return self.protocol == SERVER

    @property
    def mode_label(self) -> str:
        if self.protocol == SERVER:
            return "춥채팅 서버"       # 늘 암호화된다(wss) - 고를 것이 없다
        return "SSL" if self.use_ssl else "평문(암호화 없음)"


def parse_login_values(values: dict) -> tuple[LoginRequest | None, str]:
    """로그인 화면 입력값 -> (요청, "") 또는 (None, 사용자에게 보여줄 이유)."""
    protocol = values.get("protocol", "custom")
    # **막아둔 쪽은 여기서 거른다.** 화면에서 흐리게 해도, 예전에 저장해둔 자동
    # 로그인은 화면을 안 거치고 이 길로 바로 온다 - 그래서 거르는 곳은 여기 하나다
    from gui import availability
    if not availability.protocol_enabled(values.get("protocol") or "irc"):
        return None, availability.PROTOCOL_BLOCKED_TEXT

    host = (values.get("host") or "").strip()
    port_text = (values.get("port") or "").strip()
    user_id = (values.get("user_id") or "").strip()
    password = values.get("password") or ""

    if protocol == SERVER:
        # **주소는 받지 않는다.** 우리 서버 하나뿐이라 적을 것이 없다
        if not user_id or not password:
            return None, "아이디와 비밀번호를 입력하세요."
        host, port_text = SERVER_HOST, str(SERVER_PORT)
    elif protocol == IRC:
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
        # 서버 채팅은 늘 암호화된다(wss) - 고를 것이 없다
        use_ssl=True if protocol == SERVER else bool(values.get("ssl")),
        auto_login=bool(values.get("auto_login")),
    ), ""
