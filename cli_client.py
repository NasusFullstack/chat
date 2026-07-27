"""
친구 채팅 - 단순 CLI 클라이언트 (TUI 없이 순수 텍스트)
실행: python cli_client.py [서버주소] [포트] [cert.pem 경로(선택)]
cert.pem 경로를 안 주면, 실행 파일과 같은 폴더의 cert.pem을 자동으로 찾습니다.
"""
import asyncio
import json
import os
import ssl
import sys


def _app_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


HOST = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 6667
if len(sys.argv) > 3:
    CERT_PATH = sys.argv[3].strip().strip('"').strip("'")
else:
    _auto = os.path.join(_app_dir(), "cert.pem")
    CERT_PATH = _auto if os.path.exists(_auto) else ""


def make_ssl_context():
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    if CERT_PATH:
        try:
            ctx.load_verify_locations(cafile=CERT_PATH)
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_REQUIRED
            print(f"[알림] 인증서로 서버 신원 확인 중... ({CERT_PATH})")
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
    print(f"=== 친구 채팅 CLI === ({HOST}:{PORT})")
    ssl_context = make_ssl_context()

    try:
        reader, writer = await asyncio.open_connection(HOST, PORT, ssl=ssl_context)
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
