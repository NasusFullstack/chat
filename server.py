"""
IRC 스타일 채팅 서버
- 순수 RFC 1459 IRC 프로토콜 대신, 같은 개념(계정, 채널, 채널 키)을
  JSON 한 줄짜리 메시지로 단순화해서 구현 (파싱이 쉽고 안정적)
- 실행: python server.py [평문 포트] [TLS 포트]
- 평문(암호화 없음)과 TLS(SSL 암호화) 두 포트를 동시에 열어서, 클라이언트가
  접속 방식을 선택할 수 있게 함 (IRC 관례대로 기본 6667=평문, 6697=SSL)
"""
import asyncio
import json
import ssl
import sys
import time
from store import Store
from certs import ensure_certificate

HOST = "0.0.0.0"
PLAIN_PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 6667
SSL_PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 6697

store = Store()

# channel -> {user_id: writer}
channels: dict[str, dict[str, asyncio.StreamWriter]] = {}


async def send(writer: asyncio.StreamWriter, payload: dict):
    try:
        writer.write((json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8"))
        await writer.drain()
    except (ConnectionResetError, BrokenPipeError):
        pass


async def broadcast(channel: str, payload: dict, exclude: str = None):
    for uid, w in list(channels.get(channel, {}).items()):
        if uid == exclude:
            continue
        await send(w, payload)


async def send_userlist(channel: str):
    users = list(channels.get(channel, {}).keys())
    await broadcast(channel, {"type": "userlist", "channel": channel, "users": users})


async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    addr = writer.get_extra_info("peername")
    user_id = None
    current_channels: set[str] = set()

    print(f"[연결] {addr}")

    try:
        while True:
            line = await reader.readline()
            if not line:
                break
            try:
                msg = json.loads(line.decode("utf-8").strip())
            except json.JSONDecodeError:
                await send(writer, {"type": "error", "text": "잘못된 메시지 형식"})
                continue

            cmd = msg.get("cmd")

            if cmd == "register":
                ok, text = store.register_user(msg.get("id", ""), msg.get("pw", ""))
                await send(writer, {"type": "auth_result", "ok": ok, "text": text})

            elif cmd == "login":
                ok, text = store.verify_user(msg.get("id", ""), msg.get("pw", ""))
                if ok:
                    user_id = msg.get("id")
                await send(writer, {"type": "auth_result", "ok": ok, "text": text})

            elif cmd == "create_channel":
                if not user_id:
                    await send(writer, {"type": "error", "text": "먼저 로그인하세요."})
                    continue
                channel = msg.get("channel", "")
                ok, text = store.create_channel(channel, msg.get("key", ""), user_id)
                await send(writer, {"type": "channel_result", "ok": ok, "text": text, "channel": channel})

            elif cmd == "join":
                if not user_id:
                    await send(writer, {"type": "error", "text": "먼저 로그인하세요."})
                    continue
                channel = msg.get("channel", "")
                if channel in current_channels:
                    await send(writer, {
                        "type": "channel_result", "ok": True,
                        "text": "이미 입장한 채널입니다.", "channel": channel,
                    })
                    continue
                ok, text = store.verify_channel(channel, msg.get("key", ""))
                if ok:
                    current_channels.add(channel)
                    channels.setdefault(channel, {})[user_id] = writer
                    await send(writer, {"type": "channel_result", "ok": True, "text": text, "channel": channel})
                    await broadcast(
                        channel,
                        {"type": "system", "channel": channel, "text": f"{user_id}님이 입장했습니다."},
                        exclude=user_id,
                    )
                    await send_userlist(channel)
                else:
                    await send(writer, {"type": "channel_result", "ok": False, "text": text, "channel": channel})

            elif cmd == "msg":
                channel = msg.get("channel", "")
                if not user_id:
                    await send(writer, {"type": "error", "text": "먼저 로그인하세요."})
                    continue
                if channel not in current_channels:
                    await send(writer, {"type": "error", "text": "채널에 먼저 입장하세요.", "channel": channel})
                    continue
                text = msg.get("text", "")
                await broadcast(
                    channel,
                    {"type": "chat", "channel": channel, "from": user_id, "text": text, "ts": time.time()},
                )

            elif cmd == "leave":
                channel = msg.get("channel", "")
                if channel and user_id in channels.get(channel, {}):
                    del channels[channel][user_id]
                    current_channels.discard(channel)
                    await broadcast(
                        channel, {"type": "system", "channel": channel, "text": f"{user_id}님이 나갔습니다."}
                    )
                    await send_userlist(channel)
                    await send(writer, {"type": "leave_result", "ok": True, "text": "채널에서 나갔습니다.", "channel": channel})
                else:
                    await send(writer, {"type": "leave_result", "ok": False, "text": "입장하지 않은 채널입니다.", "channel": channel})

            else:
                await send(writer, {"type": "error", "text": f"알 수 없는 명령: {cmd}"})

    except (ConnectionResetError, asyncio.IncompleteReadError):
        pass
    finally:
        for channel in list(current_channels):
            if user_id and user_id in channels.get(channel, {}):
                del channels[channel][user_id]
                await broadcast(
                    channel, {"type": "system", "channel": channel, "text": f"{user_id}님이 접속을 종료했습니다."}
                )
                await send_userlist(channel)
        print(f"[연결 종료] {addr} (user={user_id})")
        writer.close()


async def main():
    cert_path, key_path = ensure_certificate()
    ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ssl_context.load_cert_chain(certfile=cert_path, keyfile=key_path)

    plain_server = await asyncio.start_server(handle_client, HOST, PLAIN_PORT)
    ssl_server = await asyncio.start_server(handle_client, HOST, SSL_PORT, ssl=ssl_context)

    print("채팅 서버 시작")
    print(f"  - 평문 (암호화 없음): {HOST}:{PLAIN_PORT}")
    print(f"  - TLS (SSL 암호화):   {HOST}:{SSL_PORT}")
    print(f"인증서 파일(cert.pem)을 친구들에게 함께 전달하세요: {cert_path}")

    async with plain_server, ssl_server:
        await asyncio.gather(plain_server.serve_forever(), ssl_server.serve_forever())


if __name__ == "__main__":
    asyncio.run(main())
