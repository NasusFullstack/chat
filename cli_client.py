"""
친구 채팅 - 단순 CLI 클라이언트 (TUI 없이 순수 텍스트)
실행: python cli_client.py [서버주소] [포트] [cert.pem 경로(선택)] [ssl여부: on/off, 기본 on]
인자 없이 실행하면 등록된 공용서버 목록에서 골라 접속하거나, 새 서버를 등록할 수 있습니다.
SSL을 켜면 기본 포트 6697(암호화), 끄면 기본 포트 6667(평문)을 사용합니다.
cert.pem 경로를 안 주면, 실행 파일과 같은 폴더의 cert.pem을 자동으로 찾습니다.
"""
import asyncio
import json
import os
import ssl
import sys

import server_registry

CONNECT_TIMEOUT_SEC = 10


def _app_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _auto_cert() -> str:
    candidate = os.path.join(_app_dir(), "cert.pem")
    return candidate if os.path.exists(candidate) else ""


def _prompt_yes_no(prompt: str, default: bool) -> bool:
    ans = input(prompt).strip().lower()
    if not ans:
        return default
    return ans in ("y", "yes")


def _prompt_server_choice() -> tuple[str, int, str, bool]:
    """저장된 공용서버 목록에서 고르거나, 직접 입력/새로 등록"""
    servers = server_registry.load_servers()
    print("\n=== 서버 선택 ===")
    for i, s in enumerate(servers, start=1):
        mode = "SSL" if s.get("ssl", True) else "평문"
        print(f"  {i}) {s['name']} ({s['host']}:{s['port']}, {mode})")
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
            return s["host"], int(s["port"]), s.get("cert_path", ""), s.get("ssl", True)

        if choice == manual_no:
            return _prompt_server_details()

        if choice == register_no:
            name = input("서버 이름: ").strip()
            host, port, cert_path, use_ssl = _prompt_server_details()
            if name:
                server_registry.add_server(name, host, port, cert_path, ssl=use_ssl)
                print(f"[알림] '{name}' 서버가 등록되었습니다. 다음부터 목록에서 바로 고를 수 있어요.")
            return host, port, cert_path, use_ssl

        print("[오류] 올바른 번호를 선택하세요.")


def _prompt_server_details() -> tuple[str, int, str, bool]:
    host = input("서버 주소: ").strip()
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
    if use_ssl:
        cert_path = input("cert.pem 경로 (없으면 Enter): ").strip().strip('"').strip("'")
        if not cert_path:
            cert_path = _auto_cert()
    return host, port, cert_path, use_ssl


def make_ssl_context(cert_path: str):
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    if cert_path:
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
    else:
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


async def channel_flow(reader, writer):
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
            return channel


async def listen_loop(reader, my_id):
    while True:
        try:
            msg = await recv_one(reader)
        except (ConnectionResetError, asyncio.IncompleteReadError):
            print("\n[서버 연결이 종료되었습니다]")
            return

        mtype = msg.get("type")
        if mtype == "chat":
            sender = msg.get("from")
            tag = "나" if sender == my_id else sender
            print(f"\n{tag}: {msg.get('text')}\n> ", end="", flush=True)
        elif mtype == "system":
            print(f"\n* {msg.get('text')}\n> ", end="", flush=True)
        elif mtype == "userlist":
            users = ", ".join(msg.get("users", []))
            print(f"\n[참여자: {users}]\n> ", end="", flush=True)


async def send_loop(writer):
    while True:
        text = await ainput("> ")
        if not text.strip():
            continue
        if text.strip() in ("/종료", "/quit", "/exit"):
            writer.close()
            return
        await send(writer, {"cmd": "msg", "text": text})


async def main():
    if len(sys.argv) > 1:
        host = sys.argv[1]
        use_ssl = not (len(sys.argv) > 4 and sys.argv[4].strip().lower() in ("off", "plain", "no", "0"))
        port = int(sys.argv[2]) if len(sys.argv) > 2 else (6697 if use_ssl else 6667)
        cert_path = sys.argv[3].strip().strip('"').strip("'") if len(sys.argv) > 3 else _auto_cert()
        if not use_ssl:
            cert_path = ""
    else:
        host, port, cert_path, use_ssl = _prompt_server_choice()

    print(f"\n=== 친구 채팅 CLI === ({host}:{port}, {'SSL' if use_ssl else '평문'})")
    ssl_context = make_ssl_context(cert_path) if use_ssl else None

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
        my_id = await auth_flow(reader, writer)
        await channel_flow(reader, writer)

        print("채팅을 시작합니다. 종료하려면 /종료 입력\n")

        await asyncio.gather(
            listen_loop(reader, my_id),
            send_loop(writer),
        )
    except Exception as e:  # noqa: BLE001
        print(f"\n[오류] 예상치 못한 문제가 발생했습니다: {e}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n종료합니다.")
