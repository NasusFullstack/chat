"""
친구 채팅 - 단순 CLI 클라이언트 (TUI 없이 순수 텍스트)
실행: python cli_client.py [서버주소] [포트] [cert.pem 경로(선택)] [ssl여부: on/off, 기본 on] [프로토콜: custom/irc, 기본 custom]
인자 없이 실행하면 등록된 공용서버 목록에서 골라 접속하거나, 새 서버를 등록할 수 있습니다.
SSL을 켜면 기본 포트 6697(암호화), 끄면 기본 포트 6667(평문)을 사용합니다.
cert.pem 경로를 안 주면, 실행 파일과 같은 폴더의 cert.pem을 자동으로 찾습니다.
프로토콜을 irc로 지정하면 이 프로젝트의 커스텀 서버(server.py)가 아니라 실제 IRC 서버에 접속합니다.
"""
import asyncio
import datetime
import json
import os
import ssl
import sys
import time
from dataclasses import dataclass, field

import server_registry
import irc_protocol
import history_store

CONNECT_TIMEOUT_SEC = 10


def _app_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _auto_cert() -> str:
    candidate = os.path.join(_app_dir(), "cert.pem")
    return candidate if os.path.exists(candidate) else ""


def _format_ts(ts: float) -> str:
    return datetime.datetime.fromtimestamp(ts).strftime("%H:%M")


def _print_history(protocol: str, host: str, port: int, channel: str):
    entries = history_store.load_history(protocol, host, port, channel)
    if not entries:
        return
    print("── 이전 대화 기록 ──")
    for entry in entries:
        print(f"[{_format_ts(entry['ts'])}] {entry['from']}: {entry['text']}")
    print("── 여기까지 이전 기록 ──")


def _prompt_yes_no(prompt: str, default: bool) -> bool:
    ans = input(prompt).strip().lower()
    if not ans:
        return default
    return ans in ("y", "yes")


def _prompt_server_choice() -> tuple[str, int, str, bool, str]:
    """저장된 공용서버 목록에서 고르거나, 직접 입력/새로 등록"""
    servers = server_registry.load_servers()
    print("\n=== 서버 선택 ===")
    for i, s in enumerate(servers, start=1):
        mode = "SSL" if s.get("ssl", True) else "평문"
        proto = "IRC" if s.get("protocol", "custom") == "irc" else "커스텀"
        print(f"  {i}) {s['name']} ({s['host']}:{s['port']}, {mode}, {proto})")
    manual_no = len(servers) + 1
    register_no = len(servers) + 2
    print(f"  {manual_no}) 직접 입력")
    print(f"  {register_no}) 새 공용서버 등록")

    while True:
        choice = input("번호 선택: ").strip()
        if not choice.isdigit():
            print("[오류] 숫자를 입력하세요.")
            continue
        choice = int(choice)

        if 1 <= choice <= len(servers):
            s = servers[choice - 1]
            return (
                s["host"], int(s["port"]), s.get("cert_path", ""),
                s.get("ssl", True), s.get("protocol", "custom"),
            )

        if choice == manual_no:
            return _prompt_server_details()

        if choice == register_no:
            name = input("서버 이름: ").strip()
            host, port, cert_path, use_ssl, protocol = _prompt_server_details()
            if name:
                server_registry.add_server(name, host, port, cert_path, ssl=use_ssl, protocol=protocol)
                print(f"[알림] '{name}' 서버가 등록되었습니다. 다음부터 목록에서 바로 고를 수 있어요.")
            return host, port, cert_path, use_ssl, protocol

        print("[오류] 올바른 번호를 선택하세요.")


def _prompt_server_details() -> tuple[str, int, str, bool, str]:
    host = input("서버 주소: ").strip()
    is_irc = _prompt_yes_no("실제 IRC 서버에 접속합니까? (친구 채팅 서버면 N) (y/N): ", default=False)
    protocol = "irc" if is_irc else "custom"
    use_ssl = _prompt_yes_no("SSL 암호화 연결을 사용할까요? (Y/n): ", default=True)
    default_port = 6697 if use_ssl else 6667
    port_text = input(f"포트 (기본값 {default_port}, Enter로 기본값 사용): ").strip()
    if port_text:
        while True:
            try:
                port = int(port_text)
                break
            except ValueError:
                port_text = input("[오류] 포트는 숫자여야 합니다. 다시 입력: ").strip()
    else:
        port = default_port

    cert_path = ""
    if use_ssl and protocol == "custom":
        cert_path = input("cert.pem 경로 (없으면 Enter): ").strip().strip('"').strip("'")
        if not cert_path:
            cert_path = _auto_cert()
    return host, port, cert_path, use_ssl, protocol


def make_ssl_context(cert_path: str, protocol: str = "custom"):
    if cert_path:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        try:
            ctx.load_verify_locations(cafile=cert_path)
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_REQUIRED
            print(f"[알림] 인증서로 서버 신원 확인 중... ({cert_path})")
        except Exception as e:  # noqa: BLE001
            print(f"[오류] 인증서 파일을 읽을 수 없습니다: {e}")
            print("[알림] 인증서 없이 암호화 연결만 시도합니다.")
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        return ctx
    if protocol == "irc":
        # 실제 IRC 서버는 보통 정식 CA 인증서를 쓰므로 시스템 신뢰 저장소로 표준 검증한다
        # (우리 서버의 자체 서명 인증서처럼 검증을 생략하지 않음).
        print("[알림] 시스템 인증서 저장소로 서버 신원을 표준 검증합니다.")
        return ssl.create_default_context()
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    print("[경고] 인증서 없이 접속 - 통신은 암호화되지만 서버 신원 확인은 안 됩니다.")
    return ctx


async def ainput(prompt: str = "") -> str:
    """입력 대기 중에도 다른 작업(메시지 수신)이 멈추지 않도록 스레드에서 처리"""
    return await asyncio.get_event_loop().run_in_executor(None, input, prompt)


async def send(writer, payload: dict):
    writer.write((json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8"))
    await writer.drain()


async def recv_one(reader) -> dict:
    line = await reader.readline()
    if not line:
        raise ConnectionResetError("서버 연결이 끊겼습니다.")
    return json.loads(line.decode("utf-8").strip())


@dataclass
class CustomSession:
    my_id: str
    host: str
    port: int
    channels: set = field(default_factory=set)
    active_channel: str = ""


async def auth_flow(reader, writer) -> str:
    while True:
        mode = await ainput("회원가입(r) / 로그인(l)? [r/l]: ")
        user_id = await ainput("아이디: ")
        password = await ainput("비밀번호: ")

        cmd = "register" if mode.strip().lower() == "r" else "login"
        await send(writer, {"cmd": cmd, "id": user_id, "pw": password})
        result = await recv_one(reader)
        print(f"[{result.get('text')}]")

        if cmd == "login" and result.get("ok"):
            return user_id
        # 회원가입 성공하면 다시 루프 돌아서 로그인 유도


async def channel_flow(reader, writer, session: CustomSession):
    """최초 채널 1개 입장 (이후 추가 입장은 /입장 명령으로 listen_loop 안에서 비동기 처리)"""
    while True:
        channel = await ainput("채널명 (예: #친구들): ")
        key = await ainput("채널 비밀번호 (없으면 Enter): ")
        create = await ainput("새로 만드는 채널인가요? [y/N]: ")

        if create.strip().lower() == "y":
            await send(writer, {"cmd": "create_channel", "channel": channel, "key": key})
            result = await recv_one(reader)
            print(f"[{result.get('text')}]")
            if not result.get("ok"):
                continue

        await send(writer, {"cmd": "join", "channel": channel, "key": key})
        result = await recv_one(reader)
        print(f"[{result.get('text')}]")
        if result.get("ok"):
            session.channels.add(channel)
            session.active_channel = channel
            return


def _channel_prefix(channel: str, session) -> str:
    """참여 채널이 하나뿐이거나 현재 활성 채널이면 접두사 없음 (기존 단일 채널 동작 그대로 유지)"""
    if channel == session.active_channel or len(session.channels) <= 1:
        return ""
    return f"[{channel}] "


async def _handle_slash_command(send_join, send_leave, session, command: str, normalize=lambda c: c):
    parts = command.split(maxsplit=2)
    cmd = parts[0]
    if cmd in ("/입장", "/join"):
        if len(parts) < 2:
            print("[사용법] /입장 <채널명> [비밀번호]")
            return
        channel = normalize(parts[1])
        key = parts[2] if len(parts) > 2 else ""
        await send_join(channel, key)
    elif cmd in ("/전환", "/switch"):
        if len(parts) < 2:
            print("[사용법] /전환 <채널명>")
            return
        channel = normalize(parts[1])
        if channel in session.channels:
            session.active_channel = channel
            print(f"[활성 채널: {channel}]")
        else:
            print(f"[오류] '{channel}' 채널에 입장하지 않았습니다.")
    elif cmd in ("/나가기", "/leave"):
        channel = normalize(parts[1]) if len(parts) > 1 else session.active_channel
        if not channel:
            print("[오류] 나갈 채널이 없습니다.")
            return
        await send_leave(channel)
    elif cmd in ("/채널목록", "/channels"):
        if not session.channels:
            print("[참여 중인 채널이 없습니다]")
        else:
            listing = ", ".join(
                f"*{c}" if c == session.active_channel else c for c in sorted(session.channels)
            )
            print(f"[참여 채널: {listing}] (*는 활성 채널)")
    else:
        print(f"[오류] 알 수 없는 명령: {cmd}")


async def listen_loop(reader, session: CustomSession):
    while True:
        try:
            msg = await recv_one(reader)
        except (ConnectionResetError, asyncio.IncompleteReadError):
            print("\n[서버 연결이 종료되었습니다]")
            return

        mtype = msg.get("type")
        if mtype == "chat":
            channel = msg.get("channel", "")
            sender = msg.get("from")
            text = msg.get("text")
            ts = msg.get("ts", time.time())
            tag = "나" if sender == session.my_id else sender
            prefix = _channel_prefix(channel, session)
            print(f"\n{prefix}[{_format_ts(ts)}] {tag}: {text}\n> ", end="", flush=True)
            history_store.append_message("custom", session.host, session.port, channel, sender, text, ts)

        elif mtype == "system":
            channel = msg.get("channel", "")
            prefix = _channel_prefix(channel, session)
            print(f"\n{prefix}* {msg.get('text')}\n> ", end="", flush=True)

        elif mtype == "userlist":
            channel = msg.get("channel", "")
            users = ", ".join(msg.get("users", []))
            prefix = _channel_prefix(channel, session)
            print(f"\n{prefix}[참여자: {users}]\n> ", end="", flush=True)

        elif mtype == "channel_result":
            channel = msg.get("channel", "")
            if msg.get("ok"):
                newly_joined = channel not in session.channels
                session.channels.add(channel)
                if newly_joined:
                    session.active_channel = channel
                    print(f"\n[{channel} 입장 완료 - 활성 채널로 전환합니다]\n> ", end="", flush=True)
                    _print_history("custom", session.host, session.port, channel)
                else:
                    print(f"\n[{msg.get('text')}]\n> ", end="", flush=True)
            else:
                print(f"\n[채널 입장 실패: {msg.get('text')}]\n> ", end="", flush=True)

        elif mtype == "leave_result":
            channel = msg.get("channel", "")
            if msg.get("ok"):
                session.channels.discard(channel)
                if session.active_channel == channel:
                    session.active_channel = next(iter(session.channels), "")
                print(f"\n[{channel} 채널에서 나갔습니다]\n> ", end="", flush=True)
            else:
                print(f"\n[나가기 실패: {msg.get('text')}]\n> ", end="", flush=True)

        elif mtype == "error":
            print(f"\n[오류] {msg.get('text')}\n> ", end="", flush=True)


async def send_loop(writer, session: CustomSession):
    async def do_join(channel, key):
        await send(writer, {"cmd": "join", "channel": channel, "key": key})

    async def do_leave(channel):
        await send(writer, {"cmd": "leave", "channel": channel})

    while True:
        text = await ainput("> ")
        if not text.strip():
            continue
        stripped = text.strip()
        if stripped in ("/종료", "/quit", "/exit"):
            writer.close()
            return
        if stripped.startswith("/"):
            await _handle_slash_command(do_join, do_leave, session, stripped)
            continue
        if not session.active_channel:
            print("[오류] 활성 채널이 없습니다. /입장으로 채널에 먼저 입장하세요.")
            continue
        await send(writer, {"cmd": "msg", "channel": session.active_channel, "text": text})


# ==================== 실제 IRC 서버 모드 ====================

@dataclass
class IrcSession:
    nick: str
    host: str = ""
    port: int = 0
    channels: set = field(default_factory=set)
    active_channel: str = ""
    members: dict = field(default_factory=dict)  # channel -> set(nick)


async def send_irc_line(writer, line: str):
    writer.write(irc_protocol.encode_line(line))
    await writer.drain()


async def recv_irc_line(reader) -> irc_protocol.IrcMessage:
    line = await reader.readline()
    if not line:
        raise ConnectionResetError("서버 연결이 끊겼습니다.")
    return irc_protocol.parse_line(line.decode("utf-8", errors="replace"))


async def irc_register(reader, writer) -> IrcSession:
    nick = (await ainput("닉네임: ")).strip()
    password = await ainput("서버/NickServ 비밀번호 (없으면 Enter): ")

    if password:
        await send_irc_line(writer, irc_protocol.format_pass(password))
    await send_irc_line(writer, irc_protocol.format_nick(nick))
    await send_irc_line(writer, irc_protocol.format_user(nick, nick))

    retries = 0
    while True:
        msg = await recv_irc_line(reader)

        if msg.command == "PING":
            await send_irc_line(writer, irc_protocol.format_pong(msg.trailing))
            continue

        if msg.command == irc_protocol.RPL_WELCOME:
            if password:
                await send_irc_line(writer, irc_protocol.format_privmsg("NickServ", f"IDENTIFY {password}"))
            print(f"[등록 완료: {nick}]")
            return IrcSession(nick=nick)

        if msg.command in irc_protocol.NICK_COLLISION_NUMERICS:
            if retries < irc_protocol.MAX_NICK_RETRIES:
                retries += 1
                nick = nick + "_"
                print(f"[알림] 닉네임이 사용 중입니다. '{nick}'(으)로 재시도합니다.")
            else:
                nick = (await ainput("[오류] 사용 가능한 닉네임이 없습니다. 새 닉네임: ")).strip()
                retries = 0
            await send_irc_line(writer, irc_protocol.format_nick(nick))
            continue

        if msg.command == "NOTICE":
            print(f"[{msg.trailing}]")
            continue

        if msg.command == "ERROR":
            raise ConnectionResetError(f"서버가 연결을 종료했습니다: {msg.trailing}")
        # 그 외 등록 과정의 잡다한 numeric 응답은 무시


async def irc_channel_flow(reader, writer, session: IrcSession):
    """최초 채널 1개 입장 (이후 추가 입장은 /입장 명령으로 irc_listen_loop 안에서 비동기 처리)"""
    while True:
        channel = irc_protocol.normalize_channel(await ainput("채널명 (예: #친구들): "))
        key = await ainput("채널 비밀번호 (없으면 Enter): ")
        await send_irc_line(writer, irc_protocol.format_join(channel, key or None))

        joined = False
        failed = False
        while not joined and not failed:
            msg = await recv_irc_line(reader)
            if msg.command == "PING":
                await send_irc_line(writer, irc_protocol.format_pong(msg.trailing))
            elif msg.command in irc_protocol.CHANNEL_JOIN_ERROR_NUMERICS:
                print(f"[오류] {msg.trailing or '채널 입장에 실패했습니다.'}")
                failed = True
            elif msg.command == irc_protocol.RPL_NAMREPLY:
                names_channel = msg.params[2] if len(msg.params) > 2 else channel
                session.members.setdefault(names_channel, set()).update(irc_protocol.parse_names_reply(msg))
            elif msg.command == "JOIN" and msg.source_nick == session.nick:
                session.channels.add(channel)
                session.active_channel = channel
                session.members.setdefault(channel, set()).add(session.nick)
                print(f"[{channel} 입장 완료]")
                joined = True
            elif msg.command == "NOTICE":
                print(f"[{msg.trailing}]")

        if joined:
            return


async def irc_listen_loop(reader, writer, session: IrcSession):
    while True:
        try:
            msg = await recv_irc_line(reader)
        except (ConnectionResetError, asyncio.IncompleteReadError):
            print("\n[서버 연결이 종료되었습니다]")
            return

        cmd = msg.command
        if cmd == "PING":
            await send_irc_line(writer, irc_protocol.format_pong(msg.trailing))

        elif cmd == "PRIVMSG":
            sender = msg.source_nick
            target = msg.params[0] if msg.params else ""
            text = msg.trailing
            ts = time.time()
            if target == session.nick:
                print(f"\n[{_format_ts(ts)}] {sender} (귓속말): {text}\n> ", end="", flush=True)
            else:
                prefix = _channel_prefix(target, session)
                print(f"\n{prefix}[{_format_ts(ts)}] {sender}: {text}\n> ", end="", flush=True)
                history_store.append_message("irc", session.host, session.port, target, sender, text, ts)

        elif cmd == "JOIN":
            nick = msg.source_nick
            channel = msg.trailing or (msg.params[0] if msg.params else "")
            if nick == session.nick:
                newly_joined = channel not in session.channels
                session.channels.add(channel)
                session.members.setdefault(channel, set()).add(nick)
                if newly_joined:
                    session.active_channel = channel
                    print(f"\n[{channel} 입장 완료 - 활성 채널로 전환합니다]\n> ", end="", flush=True)
                    _print_history("irc", session.host, session.port, channel)
                await send_irc_line(writer, irc_protocol.format_names(channel))
            else:
                session.members.setdefault(channel, set()).add(nick)
                prefix = _channel_prefix(channel, session)
                print(f"\n{prefix}* {nick}님이 입장했습니다.\n> ", end="", flush=True)

        elif cmd == "PART":
            nick = msg.source_nick
            channel = msg.params[0] if msg.params else ""
            session.members.setdefault(channel, set()).discard(nick)
            prefix = _channel_prefix(channel, session)
            print(f"\n{prefix}* {nick}님이 나갔습니다.\n> ", end="", flush=True)
            if nick == session.nick:
                session.channels.discard(channel)
                session.members.pop(channel, None)
                if session.active_channel == channel:
                    session.active_channel = next(iter(session.channels), "")

        elif cmd == "QUIT":
            # QUIT은 채널 정보가 없으므로 그 닉네임이 있던 모든 채널에 반영
            nick = msg.source_nick
            for channel, members in session.members.items():
                if nick in members:
                    members.discard(nick)
                    prefix = _channel_prefix(channel, session)
                    print(f"\n{prefix}* {nick}님이 접속을 종료했습니다.\n> ", end="", flush=True)

        elif cmd == "NICK":
            old_nick = msg.source_nick
            new_nick = msg.trailing or (msg.params[0] if msg.params else "")
            if old_nick == session.nick:
                session.nick = new_nick
            for channel, members in session.members.items():
                if old_nick in members:
                    members.discard(old_nick)
                    members.add(new_nick)
                    prefix = _channel_prefix(channel, session)
                    print(f"\n{prefix}* {old_nick}님이 {new_nick}(으)로 닉네임을 변경했습니다.\n> ", end="", flush=True)

        elif cmd == irc_protocol.RPL_NAMREPLY:
            channel = msg.params[2] if len(msg.params) > 2 else ""
            session.members.setdefault(channel, set()).update(irc_protocol.parse_names_reply(msg))

        elif cmd in irc_protocol.CHANNEL_JOIN_ERROR_NUMERICS:
            print(f"\n[채널 입장 실패: {msg.trailing or '알 수 없는 오류'}]\n> ", end="", flush=True)

        elif cmd == "NOTICE":
            print(f"\n* {msg.trailing}\n> ", end="", flush=True)

        elif cmd == "ERROR":
            print(f"\n[서버 연결이 종료되었습니다: {msg.trailing}]")
            return


async def irc_send_loop(writer, session: IrcSession):
    async def do_join(channel, key):
        await send_irc_line(writer, irc_protocol.format_join(channel, key or None))

    async def do_leave(channel):
        await send_irc_line(writer, irc_protocol.format_part(channel))

    while True:
        text = await ainput("> ")
        if not text.strip():
            continue
        stripped = text.strip()
        if stripped in ("/종료", "/quit", "/exit"):
            await send_irc_line(writer, irc_protocol.format_quit("나감"))
            writer.close()
            return
        if stripped.startswith("/"):
            await _handle_slash_command(do_join, do_leave, session, stripped, normalize=irc_protocol.normalize_channel)
            continue
        if not session.active_channel:
            print("[오류] 활성 채널이 없습니다. /입장으로 채널에 먼저 입장하세요.")
            continue
        ts = time.time()
        print(f"[{_format_ts(ts)}] 나: {text}")
        history_store.append_message(
            "irc", session.host, session.port, session.active_channel, session.nick, text, ts
        )
        await send_irc_line(writer, irc_protocol.format_privmsg(session.active_channel, text))


async def main():
    if len(sys.argv) > 1:
        host = sys.argv[1]
        use_ssl = not (len(sys.argv) > 4 and sys.argv[4].strip().lower() in ("off", "plain", "no", "0"))
        port = int(sys.argv[2]) if len(sys.argv) > 2 else (6697 if use_ssl else 6667)
        cert_path = sys.argv[3].strip().strip('"').strip("'") if len(sys.argv) > 3 else _auto_cert()
        protocol = sys.argv[5].strip().lower() if len(sys.argv) > 5 else "custom"
        if protocol not in ("custom", "irc"):
            protocol = "custom"
        if not use_ssl or protocol == "irc":
            cert_path = ""
    else:
        host, port, cert_path, use_ssl, protocol = _prompt_server_choice()

    proto_label = "IRC" if protocol == "irc" else "커스텀"
    print(f"\n=== 친구 채팅 CLI === ({host}:{port}, {'SSL' if use_ssl else '평문'}, {proto_label})")
    ssl_context = make_ssl_context(cert_path, protocol) if use_ssl else None

    print(f"[알림] 연결 시도 중... (최대 {CONNECT_TIMEOUT_SEC}초, Ctrl+C로 언제든 취소)")
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port, ssl=ssl_context), timeout=CONNECT_TIMEOUT_SEC
        )
    except asyncio.TimeoutError:
        print(f"[오류] 연결 시간이 초과되었습니다. ({CONNECT_TIMEOUT_SEC}초)")
        return
    except Exception as e:  # noqa: BLE001
        print(f"[오류] 연결 실패: {e}")
        return

    try:
        if protocol == "irc":
            session = await irc_register(reader, writer)
            session.host = host
            session.port = port
            await irc_channel_flow(reader, writer, session)
            _print_history("irc", host, port, session.active_channel)

            print("채팅을 시작합니다. 종료하려면 /종료 입력")
            print("[알림] /입장 <채널명>으로 채널 추가, /전환 <채널명>으로 전환, /나가기, /채널목록\n")

            await asyncio.gather(
                irc_listen_loop(reader, writer, session),
                irc_send_loop(writer, session),
            )
        else:
            my_id = await auth_flow(reader, writer)
            session = CustomSession(my_id=my_id, host=host, port=port)
            await channel_flow(reader, writer, session)
            _print_history("custom", host, port, session.active_channel)

            print("채팅을 시작합니다. 종료하려면 /종료 입력")
            print("[알림] /입장 <채널명>으로 채널 추가, /전환 <채널명>으로 전환, /나가기, /채널목록\n")

            await asyncio.gather(
                listen_loop(reader, session),
                send_loop(writer, session),
            )
    except Exception as e:  # noqa: BLE001
        print(f"\n[오류] 예상치 못한 문제가 발생했습니다: {e}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n종료합니다.")
