"""
친구 채팅 - 단순 CLI 클라이언트 (TUI 없이 순수 텍스트)
실행: python cli_client.py [서버주소] [포트] [cert.pem 경로(선택)] [ssl여부: on/off, 기본 on] [프로토콜: custom/irc, 기본 custom]
인자 없이 실행하면 등록된 공용서버 목록에서 골라 접속하거나, 새 서버를 등록할 수 있습니다.
SSL을 켜면 기본 포트 6697(암호화), 끄면 기본 포트 6667(평문)을 사용합니다.
cert.pem 경로를 안 주면, 실행 파일과 같은 폴더의 cert.pem을 자동으로 찾습니다.
프로토콜을 irc로 지정하면 이 프로젝트의 커스텀 서버(server.py)가 아니라 실제 IRC 서버에 접속합니다.

구조: 로그인/채널/멤버리스트/메시지 해석 같은 "상태 로직"은 전부 chat_core.ChatSession이
담당하고(GUI와 같은 코어를 공유함), 이 파일은 얇은 어댑터로서 (1) asyncio 소켓 I/O,
(2) input() 프롬프트를 세션 메서드 호출로 변환, (3) 세션이 내보내는 이벤트를 터미널에
print 하는 것만 담당함.
"""
import asyncio
import datetime
import json
import os
import ssl
import sys

import irc_protocol
import server_registry
from chat_core import commands, events
from chat_core.session import build_session

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


class CliAdapter:
    """ChatSession(도메인 코어)을 터미널에 연결하는 어댑터.

    코어가 내보내는 이벤트를 print로 렌더링하고, 로그인/채널입장처럼 "응답을 기다려야
    하는" 흐름은 asyncio.Event로 완료 신호를 받아서 기존 CLI의 순차적 프롬프트 UX를
    그대로 유지함(코어 자체는 비동기 이벤트 방식이라 이 대기는 어댑터 쪽 책임).
    """

    def __init__(self, protocol: str, host: str, port: int, writer):
        self.protocol = protocol
        self.writer = writer
        # 프로토콜에 따라 전송 방식이 다르므로(dict를 JSON 라인으로 / 문자열을 IRC 라인으로)
        # 세션을 만들 때 알맞은 전송 포트를 꽂아줌 - 코어는 이 차이를 모름
        transport = self._send_irc if protocol == "irc" else self._send_json
        self.session = build_session(
            protocol, host, port,
            transport=transport,
            on_event=self._on_event,
        )
        self.running = True
        # 순차 흐름(로그인/채널입장)에서 응답을 기다리기 위한 신호
        self.auth_done = asyncio.Event()
        self.auth_ok = False
        self.register_done = asyncio.Event()
        self.channel_done = asyncio.Event()
        self.channel_ok = False
        # 프롬프트가 뜬 상태에서 메시지가 오면 줄이 섞이므로, 기존처럼 개행 후 "> "를 다시 그림
        self.interactive = False

    # ---------- 코어가 쓰는 전송 포트 ----------
    def _send_json(self, payload: dict):
        self.writer.write((json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8"))

    def _send_irc(self, line: str):
        self.writer.write(irc_protocol.encode_line(line))

    # ---------- 코어 이벤트를 터미널에 렌더링 ----------
    def _out(self, text: str):
        """채팅 중(대화형)일 때는 입력 프롬프트와 안 섞이도록 앞뒤로 개행/프롬프트를 붙임"""
        if self.interactive:
            print(f"\n{text}\n> ", end="", flush=True)
        else:
            print(text)

    def _channel_prefix(self, channel: str) -> str:
        """참여 채널이 하나뿐이거나 현재 활성 채널이면 접두사 없음(기존 단일 채널 동작 그대로)"""
        s = self.session
        if channel == s.active_channel or len(s.joined_channels) <= 1:
            return ""
        return f"[{channel}] "

    def _on_event(self, event):
        s = self.session

        if isinstance(event, events.LoggedIn):
            if not self.auth_done.is_set():
                self.auth_ok = True
                # IRC는 "등록 완료", 커스텀 서버는 로그인 성공 - 기존 CLI 출력 문구를 유지
                print(f"[등록 완료: {event.user_id}]" if self.protocol == "irc" else "[로그인 성공]")
                self.auth_done.set()

        elif isinstance(event, events.RegisterSucceeded):
            print("[회원가입 완료]")
            self.register_done.set()

        elif isinstance(event, events.AuthFailed):
            print(f"[{event.text}]")
            self.auth_ok = False
            self.auth_done.set()
            self.register_done.set()

        elif isinstance(event, events.ChannelCreated):
            print(f"[{event.text}]")
            self.channel_ok = True
            self.channel_done.set()

        elif isinstance(event, events.ChannelJoined):
            if self.interactive:
                self._out(f"[{event.channel} 입장 완료 - 활성 채널로 전환합니다]")
            else:
                # 최초 입장 때는 서버가 준 문구를 그대로 보여줌(커스텀 서버는 "입장 성공")
                print(f"[{event.text}]")
            self._print_history(event.history)
            self.channel_ok = True
            self.channel_done.set()

        elif isinstance(event, events.ChannelJoinFailed):
            text = event.text or "채널 입장에 실패했습니다."
            if self.interactive:
                self._out(f"[채널 입장 실패: {text}]")
            else:
                print(f"[오류] {text}")
            self.channel_ok = False
            self.channel_done.set()

        elif isinstance(event, events.ChannelLeft):
            self._out(f"[{event.channel} 채널에서 나갔습니다]")

        elif isinstance(event, events.ChannelLeaveFailed):
            self._out(f"[나가기 실패: {event.text}]")

        elif isinstance(event, events.MessageReceived):
            tag = "나" if event.mine else event.sender
            display = s.nicknames.get(event.sender, event.sender) if not event.mine else tag
            prefix = self._channel_prefix(event.channel)
            # /me(행동)와 /notice(공지)는 "닉: 내용" 형식이 아니라 IRC 관행대로 따로 그림
            if event.kind == commands.KIND_ACTION:
                line = f"{prefix}[{_format_ts(event.ts)}] * {display} {event.text}"
            elif event.kind == commands.KIND_NOTICE:
                line = f"{prefix}[{_format_ts(event.ts)}] -{display}- {event.text}"
            else:
                line = f"{prefix}[{_format_ts(event.ts)}] {display}: {event.text}"
            if event.mine and not self.interactive:
                print(line)
            elif event.mine:
                # 내가 방금 보낸 건 프롬프트를 새로 그릴 필요 없이 그냥 한 줄 출력
                print(line)
            else:
                self._out(line)

        elif isinstance(event, events.SystemNotice):
            prefix = self._channel_prefix(event.channel) if event.channel else ""
            self._out(f"{prefix}* {event.text}")

        elif isinstance(event, events.UserlistUpdated):
            prefix = self._channel_prefix(event.channel)
            users = ", ".join(event.users)
            self._out(f"{prefix}[참여자: {users}]")

        elif isinstance(event, events.MentionBlocked):
            self._out(f"[@{event.target_display} 호출은 {event.remaining_sec}초 후에 다시 가능합니다]")

        elif isinstance(event, events.CommandHelp):
            self._out("[사용 가능한 명령]")
            for line in event.lines:
                self._out("  " + line)

        elif isinstance(event, events.CommandError):
            self._out(f"[{event.text}]")

        elif isinstance(event, events.NicknameRetrying):
            print(f"[알림] 닉네임이 사용 중입니다. '{event.new_nickname}'(으)로 재시도합니다.")

        elif isinstance(event, events.NicknameChangeFailed):
            self._out(f"[닉네임 변경 실패: {event.text}]")

        elif isinstance(event, events.ConnectionClosed):
            print(f"\n[서버 연결이 종료되었습니다: {event.text}]")
            self.running = False

        elif isinstance(event, events.GenericError):
            self._out(f"[오류] {event.text}")

        # AvatarUpdated / NicknameUpdated / ClientVersionUpdated는 터미널에 그릴 게
        # 없어서 조용히 무시. 다만 CTCP VERSION에 답하는 일은 코어가 하므로, CLI로
        # 접속해도 남들 눈에는 '춥채팅'으로 제대로 보인다
        # (코어가 캐시는 갱신해두므로 닉네임은 메시지 표시에 자동 반영됨)

    def _print_history(self, history: list[dict]):
        if not history:
            return
        print("── 이전 대화 기록 ──")
        for entry in history:
            print(f"[{_format_ts(entry['ts'])}] {entry['from']}: {entry['text']}")
        print("── 여기까지 이전 기록 ──")


async def _drain(writer):
    try:
        await writer.drain()
    except (ConnectionResetError, BrokenPipeError):
        pass


async def auth_flow(adapter: CliAdapter, reader, writer):
    """커스텀 프로토콜 로그인 - 로그인 성공할 때까지 반복"""
    while True:
        mode = await ainput("회원가입(r) / 로그인(l)? [r/l]: ")
        user_id = await ainput("아이디: ")
        password = await ainput("비밀번호: ")

        is_register = mode.strip().lower() == "r"
        if is_register:
            adapter.register_done.clear()
            adapter.session.register(user_id, password)
            await _drain(writer)
            await adapter.register_done.wait()
            # 회원가입 성공/실패 무관하게 다시 루프 돌아서 로그인 유도(기존 동작 그대로)
            continue

        adapter.auth_done.clear()
        adapter.session.login(user_id, password)
        await _drain(writer)
        await adapter.auth_done.wait()
        if adapter.auth_ok:
            return


async def channel_flow(adapter: CliAdapter, writer):
    """최초 채널 1개 입장 (이후 추가 입장은 /입장 명령으로 처리)"""
    while True:
        channel = await ainput("채널명 (예: #친구들): ")
        if adapter.protocol == "irc":
            channel = irc_protocol.normalize_channel(channel)
        key = await ainput("채널 비밀번호 (없으면 Enter): ")

        if adapter.protocol == "custom":
            create = await ainput("새로 만드는 채널인가요? [y/N]: ")
            if create.strip().lower() == "y":
                adapter.channel_done.clear()
                adapter.session.create_channel(channel, key)
                await _drain(writer)
                await adapter.channel_done.wait()
                if not adapter.channel_ok:
                    continue

        adapter.channel_done.clear()
        adapter.session.join_channel(channel, key)
        await _drain(writer)
        await adapter.channel_done.wait()
        if adapter.channel_ok:
            return


# CLI 화면 조작 전용 명령 - 서버로 나가지 않고 터미널 쪽에서만 의미가 있음
_CLI_LOCAL_HELP = [
    "/입장(/join) <채널> [비밀번호]  -  채널에 입장합니다",
    "/전환(/switch) <채널>  -  활성 채널을 바꿉니다",
    "/나가기(/leave) [채널]  -  채널에서 나갑니다",
    "/채널목록(/channels)  -  참여 중인 채널을 봅니다",
    "/종료(/quit)  -  프로그램을 끝냅니다",
]


async def _handle_slash_command(adapter: CliAdapter, writer, command: str):
    s = adapter.session
    normalize = irc_protocol.normalize_channel if adapter.protocol == "irc" else (lambda c: c)
    parts = command.split(maxsplit=2)
    cmd = parts[0]

    if cmd == "/help":
        # CLI 전용 명령을 먼저 보여주고, 프로토콜이 지원하는 명령은 코어가 이어서 알려줌
        print("[CLI 전용 명령]")
        for line in _CLI_LOCAL_HELP:
            print("  " + line)
        s.send_message(s.active_channel, command)
        await _drain(writer)
    elif cmd in ("/입장", "/join"):
        if len(parts) < 2:
            print("[사용법] /입장 <채널명> [비밀번호]")
            return
        channel = normalize(parts[1])
        key = parts[2] if len(parts) > 2 else ""
        s.join_channel(channel, key)
        await _drain(writer)
    elif cmd in ("/전환", "/switch"):
        if len(parts) < 2:
            print("[사용법] /전환 <채널명>")
            return
        channel = normalize(parts[1])
        if channel in s.joined_channels:
            s.active_channel = channel
            print(f"[활성 채널: {channel}]")
        else:
            print(f"[오류] '{channel}' 채널에 입장하지 않았습니다.")
    elif cmd in ("/나가기", "/leave"):
        channel = normalize(parts[1]) if len(parts) > 1 else s.active_channel
        if not channel:
            print("[오류] 나갈 채널이 없습니다.")
            return
        s.leave_channel(channel)
        await _drain(writer)
    elif cmd in ("/채널목록", "/channels"):
        if not s.joined_channels:
            print("[참여 중인 채널이 없습니다]")
        else:
            listing = ", ".join(
                f"*{c}" if c == s.active_channel else c for c in sorted(s.joined_channels)
            )
            print(f"[참여 채널: {listing}] (*는 활성 채널)")
    else:
        # CLI 전용 명령이 아니면 코어에 넘김 - /me, /notice, /whois 같은 프로토콜 명령은
        # GUI와 완전히 같은 구현(chat_core)을 타므로 여기서 다시 만들 필요가 없음.
        # 코어도 모르는 명령이면 CommandError 이벤트로 안내가 나감
        if not s.active_channel:
            print("[오류] 채널에 먼저 입장하세요.")
            return
        s.send_message(s.active_channel, command)
        await _drain(writer)


async def listen_loop(adapter: CliAdapter, reader):
    """소켓에서 원시 라인을 읽어 코어에 넘기기만 함 - 해석은 전부 ChatSession이 담당.

    종료 조건을 adapter.running이 아니라 "연결이 실제로 끊길 때(EOF)"로 둠: /종료 직후에도
    서버가 이미 보낸 메시지(내가 방금 보낸 채팅의 에코 등)가 소켓 버퍼에 남아있을 수 있는데,
    running 플래그로 즉시 중단하면 그게 화면에 못 찍히고 사라짐.
    """
    while True:
        try:
            line = await reader.readline()
        except (ConnectionResetError, asyncio.IncompleteReadError):
            break
        if not line:
            break

        if adapter.protocol == "irc":
            msg = irc_protocol.parse_line(line.decode("utf-8", errors="replace"))
        else:
            try:
                msg = json.loads(line.decode("utf-8").strip())
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
        adapter.session.handle_incoming(msg)
        await _drain(adapter.writer)  # 코어가 응답(PONG 등)을 보냈을 수 있음

    if adapter.running:
        print("\n[서버 연결이 종료되었습니다]")
        adapter.running = False


async def send_loop(adapter: CliAdapter, writer):
    s = adapter.session
    while adapter.running:
        text = await ainput("> ")
        if not adapter.running:
            return
        if not text.strip():
            continue
        stripped = text.strip()

        if stripped in ("/종료", "/quit", "/exit"):
            if adapter.protocol == "irc":
                adapter.session.transport(irc_protocol.format_quit("나감"))
                await _drain(writer)
            adapter.running = False
            writer.close()
            return

        if stripped.startswith("/"):
            await _handle_slash_command(adapter, writer, stripped)
            continue

        if not s.active_channel:
            print("[오류] 활성 채널이 없습니다. /입장으로 채널에 먼저 입장하세요.")
            continue

        s.send_message(s.active_channel, text)
        await _drain(writer)


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

    adapter = CliAdapter(protocol, host, port, writer)
    listener = asyncio.create_task(listen_loop(adapter, reader))

    try:
        if protocol == "irc":
            nick = (await ainput("닉네임: ")).strip()
            password = await ainput("서버/NickServ 비밀번호 (없으면 Enter): ")
            adapter.auth_done.clear()
            # IRC는 회원가입 개념이 없어서 login()이 곧 등록 핸드셰이크임(프로토콜 전략이 처리)
            adapter.session.login(nick, password)
            await _drain(writer)
            await adapter.auth_done.wait()
            if not adapter.auth_ok:
                return
        else:
            await auth_flow(adapter, reader, writer)

        await channel_flow(adapter, writer)

        print("채팅을 시작합니다. 종료하려면 /종료 입력")
        print("[알림] /입장 <채널명>으로 채널 추가, /전환 <채널명>으로 전환, /나가기, /채널목록\n")
        adapter.interactive = True

        await send_loop(adapter, writer)
        # /종료로 writer를 닫으면 서버도 연결을 닫아 listen_loop이 EOF로 스스로 끝남 -
        # 그때까지 잠깐 기다려서 아직 도착 안 한 메시지(내 마지막 채팅의 에코 등)를 마저 출력함
        try:
            await asyncio.wait_for(listener, timeout=2.0)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            pass
    except Exception as e:  # noqa: BLE001
        print(f"\n[오류] 예상치 못한 문제가 발생했습니다: {e}")
    finally:
        adapter.running = False
        listener.cancel()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n종료합니다.")
