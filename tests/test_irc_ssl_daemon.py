"""테스트 전용: TLS로 감싼 미니 IRC 데몬 (자체 서명 인증서 사용).
실제 소규모/개인 IRC 서버가 자체 서명 인증서를 쓰는 상황을 재현해서
SSL 로그인 실패 원인을 검증하기 위한 용도.
"""
import os as _os
import sys as _sys

_HERE = _os.path.dirname(_os.path.abspath(__file__))
_REPO = _os.path.dirname(_HERE)

import asyncio
import ssl
import sys

sys.path.insert(0, _REPO)
from certs import ensure_certificate

HOST = "127.0.0.1"
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 16701

clients: dict[str, asyncio.StreamWriter] = {}


async def send(writer, line: str):
    try:
        writer.write((line + "\r\n").encode("utf-8"))
        await writer.drain()
    except (ConnectionResetError, BrokenPipeError):
        pass


async def handle_client(reader, writer):
    nick = None
    user_sent = False
    welcomed = False

    async def maybe_welcome():
        nonlocal welcomed
        if welcomed or not nick or not user_sent:
            return
        welcomed = True
        await send(writer, f":testd 001 {nick} :Welcome {nick}")

    try:
        while True:
            line = await reader.readline()
            if not line:
                break
            text = line.decode("utf-8", errors="replace").strip()
            if not text:
                continue
            if text.startswith("NICK "):
                nick = text[5:].strip()
                clients[nick] = writer
                await maybe_welcome()
                continue
            if text.startswith("USER "):
                user_sent = True
                await maybe_welcome()
                continue
    except (ConnectionResetError, asyncio.IncompleteReadError, ssl.SSLError):
        pass
    finally:
        if nick:
            clients.pop(nick, None)
        writer.close()


async def main():
    cert_path, key_path = ensure_certificate()
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(certfile=cert_path, keyfile=key_path)
    server = await asyncio.start_server(handle_client, HOST, PORT, ssl=ctx)
    print(f"[test ssl irc daemon] listening on {HOST}:{PORT} (self-signed cert: {cert_path})")
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
