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
import unfurl
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

                    # 새로 입장하는 사람에게 기존 멤버들의 아이콘/닉네임을 알려줌 (설정한 사람만)
                    for other_uid in channels[channel]:
                        if other_uid == user_id:
                            continue
                        other_avatar = store.get_avatar(other_uid)
                        if other_avatar:
                            await send(writer, {
                                "type": "member_avatar", "channel": channel,
                                "user_id": other_uid, "avatar": other_avatar,
                            })
                        other_nickname = store.get_nickname(other_uid)
                        if other_nickname:
                            await send(writer, {
                                "type": "member_nickname", "channel": channel,
                                "user_id": other_uid, "nickname": other_nickname,
                            })

                    await broadcast(
                        channel,
                        {"type": "system", "channel": channel, "text": f"{user_id}님이 입장했습니다."},
                        exclude=user_id,
                    )

                    # 기존 멤버들에게 새로 입장한 사람의 아이콘/닉네임을 알려줌 (내가 설정했을 때만)
                    my_avatar = store.get_avatar(user_id)
                    if my_avatar:
                        await broadcast(
                            channel,
                            {"type": "member_avatar", "channel": channel, "user_id": user_id, "avatar": my_avatar},
                            exclude=user_id,
                        )
                    my_nickname = store.get_nickname(user_id)
                    if my_nickname:
                        await broadcast(
                            channel,
                            {"type": "member_nickname", "channel": channel, "user_id": user_id, "nickname": my_nickname},
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

            elif cmd == "set_avatar":
                if not user_id:
                    await send(writer, {"type": "error", "text": "먼저 로그인하세요."})
                    continue
                avatar = msg.get("avatar", "")
                ok, text = store.set_avatar(user_id, avatar)
                if not ok:
                    await send(writer, {"type": "error", "text": text})
                    continue
                for channel in current_channels:
                    await broadcast(
                        channel,
                        {"type": "member_avatar", "channel": channel, "user_id": user_id, "avatar": avatar},
                        exclude=user_id,
                    )

            elif cmd == "set_nickname":
                if not user_id:
                    await send(writer, {"type": "error", "text": "먼저 로그인하세요."})
                    continue
                nickname = msg.get("nickname", "")
                ok, text = store.set_nickname(user_id, nickname)
                if not ok:
                    await send(writer, {"type": "error", "text": text})
                    continue
                for channel in current_channels:
                    await broadcast(
                        channel,
                        {"type": "member_nickname", "channel": channel, "user_id": user_id, "nickname": nickname},
                        exclude=user_id,
                    )

            elif cmd == "unfurl":
                # 링크 미리보기를 서버가 대신 가져옴. 클라이언트가 각자 접속하면 채널
                # 인원수만큼 요청이 나가고 참여자 IP가 링크 주인에게 전부 노출되므로,
                # 서버가 한 번만 받아 캐시해두고 결과만 나눠줌(unfurl.py 설명 참고).
                if not user_id:
                    await send(writer, {"type": "error", "text": "먼저 로그인하세요."})
                    continue
                url = msg.get("url", "")
                if not url or not unfurl.check_rate_limit(user_id):
                    # 도배로 서버 자원을 소모하지 못하게 막음. 조용히 무시하면 되고
                    # (미리보기는 덤이라) 오류를 채팅에 남길 필요는 없음
                    continue
                # 네트워크 요청이라 오래 걸릴 수 있음 - 별도 스레드로 돌려서 다른
                # 사용자들의 채팅이 그 사이 멈추지 않게 함
                info = await asyncio.to_thread(unfurl.unfurl, url)
                await send(writer, {"type": "unfurl_result", "url": url, **info})

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
