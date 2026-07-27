"""
IRC 스타일 채팅 서버
- 순수 RFC 1459 IRC 프로토콜 대신, 같은 개념(계정, 채널, 채널 키)을
  JSON 한 줄짜리 메시지로 단순화해서 구현 (파싱이 쉽고 안정적)
- 실행: python server.py [포트]
"""
import asyncio
import json
import sys
import time
from store import Store

HOST = "0.0.0.0"
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 6667

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
    current_channel = None

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
                ok, text = store.create_channel(
                    msg.get("channel", ""), msg.get("key", ""), user_id
                )
                await send(writer, {"type": "channel_result", "ok": ok, "text": text})

            elif cmd == "join":
                if not user_id:
                    await send(writer, {"type": "error", "text": "먼저 로그인하세요."})
                    continue
                channel = msg.get("channel", "")
                ok, text = store.verify_channel(channel, msg.get("key", ""))
                if ok:
                    # 이전 채널에서 나가기
                    if current_channel and user_id in channels.get(current_channel, {}):
                        del channels[current_channel][user_id]
                        await send_userlist(current_channel)
                    current_channel = channel
                    channels.setdefault(channel, {})[user_id] = writer
                    await send(writer, {"type": "channel_result", "ok": True, "text": text})
                    await broadcast(
                        channel,
                        {"type": "system", "text": f"{user_id}님이 입장했습니다."},
                        exclude=user_id,
                    )
                    await send_userlist(channel)
                else:
                    await send(writer, {"type": "channel_result", "ok": False, "text": text})

            elif cmd == "msg":
                if not user_id or not current_channel:
                    await send(writer, {"type": "error", "text": "채널에 먼저 입장하세요."})
                    continue
                text = msg.get("text", "")
                await broadcast(
                    current_channel,
                    {
                        "type": "chat",
                        "channel": current_channel,
                        "from": user_id,
                        "text": text,
                        "ts": time.time(),
                    },
                )

            elif cmd == "leave":
                if current_channel and user_id in channels.get(current_channel, {}):
                    del channels[current_channel][user_id]
                    await broadcast(
                        current_channel,
                        {"type": "system", "text": f"{user_id}님이 나갔습니다."},
                    )
                    await send_userlist(current_channel)
                current_channel = None

            else:
                await send(writer, {"type": "error", "text": f"알 수 없는 명령: {cmd}"})

    except (ConnectionResetError, asyncio.IncompleteReadError):
        pass
    finally:
        if current_channel and user_id and user_id in channels.get(current_channel, {}):
            del channels[current_channel][user_id]
            await broadcast(
                current_channel, {"type": "system", "text": f"{user_id}님이 접속을 종료했습니다."}
            )
            await send_userlist(current_channel)
        print(f"[연결 종료] {addr} (user={user_id})")
        writer.close()


async def main():
    server = await asyncio.start_server(handle_client, HOST, PORT)
    print(f"채팅 서버 시작: {HOST}:{PORT}")
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
