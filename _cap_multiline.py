"""CAP 목록이 여러 줄로 나뉘어 오는 경우를 제대로 처리한다.

IRCv3에서 서버는 지원 목록이 길면 나눠 보내고, "아직 더 있다"를 `*`로 표시한다:

    :server CAP * LS * :첫째묶음 ...
    :server CAP * LS :마지막묶음 ...

실측(home.pdlab.kr): 우리가 첫 줄만 보고 "sasl 없네" 하고 협상을 끝내버려서,
그 뒤에 나간 AUTHENTICATE가 순서를 잃고 인증이 안 됐다.
"""
import io

path = "irc_protocol.py"
text = io.open(path, encoding="utf-8").read()
old = '''def parse_cap(msg) -> tuple:
    """CAP 응답에서 (하위명령, 기능목록)을 뽑는다. 예: ("LS", ["sasl=PLAIN", "tls"])"""
    params = list(msg.params)
    sub = params[1] if len(params) > 1 else ""
    body = msg.trailing or (params[-1] if params else "")
    return sub.upper(), body.split()'''
new = '''def parse_cap(msg) -> tuple:
    """CAP 응답에서 (하위명령, 기능목록, 더_있음)을 뽑는다.

    목록이 길면 서버가 여러 줄로 나눠 보내고 "아직 더 있다"를 `*`로 표시한다:

        :server CAP * LS * :첫째묶음
        :server CAP * LS :마지막묶음

    이걸 모르고 첫 줄만 보면 뒤에 오는 기능(sasl 등)을 놓친다(실측으로 겪었다).
    """
    params = list(msg.params)
    sub = (params[1] if len(params) > 1 else "").upper()
    body = msg.trailing or ""
    middle = params[2:-1] if len(params) > 2 else []
    more = "*" in middle
    return sub, body.split(), more'''
assert old in text
io.open(path, "w", encoding="utf-8").write(text.replace(old, new, 1))

# ---------- 프로토콜: 여러 줄을 모아서 판단 ----------
path = "chat_core/protocols/irc.py"
text = io.open(path, encoding="utf-8").read()
old = '''        sub, items = irc_protocol.parse_cap(msg)
        if sub == "LS":
            supports_sasl = any(item.split("=")[0].lower() == "sasl" for item in items)
            if supports_sasl and session.irc_password:
                session.sasl_state = "요청함"
                session.transport(irc_protocol.format_cap_req("sasl"))
                return
            self._end_cap(session)          # 못 쓰면 붙잡고 있지 않는다
        elif sub == "ACK" and any("sasl" in item.lower() for item in items):'''
new = '''        sub, items, more = irc_protocol.parse_cap(msg)
        if sub == "LS":
            # 목록이 여러 줄로 나뉘어 올 수 있다 - 다 모은 뒤에 판단해야 한다
            session.cap_available.extend(items)
            if more:
                return
            supports_sasl = any(item.split("=")[0].lower() == "sasl"
                                for item in session.cap_available)
            if supports_sasl and session.irc_password:
                session.sasl_state = "요청함"
                session.transport(irc_protocol.format_cap_req("sasl"))
                return
            self._end_cap(session)          # 못 쓰면 붙잡고 있지 않는다
        elif sub == "ACK" and any("sasl" in item.lower() for item in items):'''
assert old in text
text = text.replace(old, new, 1)
text = text.replace("""        session.cap_negotiating = False
        session.sasl_state = ""
        if password:""",
                    """        session.cap_negotiating = False
        session.sasl_state = ""
        session.cap_available = []
        if password:""", 1)
io.open(path, "w", encoding="utf-8").write(text)

# ---------- 세션 상태 ----------
path = "chat_core/session.py"
text = io.open(path, encoding="utf-8").read()
old = '''        self.sasl_state = ""     # "" / "요청함" / "진행중" / "성공" / "실패"'''
new = '''        self.sasl_state = ""     # "" / "요청함" / "진행중" / "성공" / "실패"
        # 서버가 알려준 기능 목록(여러 줄로 나뉘어 오므로 모아둔다)
        self.cap_available: list = []'''
assert old in text
io.open(path, "w", encoding="utf-8").write(text.replace(old, new, 1))
print("여러 줄 CAP 처리 추가")
