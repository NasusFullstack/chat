"""테스트 전용 미니 IRC 데몬 - 실제 프로젝트에는 포함되지 않음.
gui_client.py / cli_client.py의 IRC 모드 구현을 검증하기 위한 용도로만 사용.
"""
import os as _os
import sys as _sys

_HERE = _os.path.dirname(_os.path.abspath(__file__))
_REPO = _os.path.dirname(_HERE)

import asyncio
import sys

HOST = "127.0.0.1"
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 16700

# nick -> writer
clients: dict[str, asyncio.StreamWriter] = {}
# channel -> set(nick)
channels: dict[str, set] = {}


async def send(writer, line: str):
    try:
        writer.write((line + "\r\n").encode("utf-8"))
        await writer.drain()
    except (ConnectionResetError, BrokenPipeError):
        pass


async def broadcast(channel: str, line: str, exclude: str = None):
    for nick in list(channels.get(channel, set())):
        if nick == exclude:
            continue
        w = clients.get(nick)
        if w:
            await send(w, line)


async def ping_loop(nick: str, writer):
    try:
        while True:
            await asyncio.sleep(2)
            if nick not in clients:
                return
            await send(writer, "PING :testtoken")
    except asyncio.CancelledError:
        return


async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    nick = None
    my_channels: set = set()
    pinger = None
    pass_given = None
    user_sent = False
    welcomed = False

    async def maybe_welcome():
        nonlocal pinger, welcomed, nick
        if welcomed or not nick or not user_sent:
            return
        welcomed = True
        # 서버가 요청한 닉네임을 그대로 안 주고 다른 걸로 바꿔서 확정하는 상황을
        # 재현하기 위한 테스트 전용 트리거 (실제 서버가 규칙 위반/미인증 시 Guest로
        # 바꾸는 것과 같은 시나리오)
        if nick == "wantguest":
            clients.pop(nick, None)
            nick = "Guest1234"
            clients[nick] = writer
        await send(writer, f":testd 001 {nick} :Welcome to the test IRC network {nick}")
        pinger = asyncio.create_task(ping_loop(nick, writer))

    try:
        while True:
            line = await reader.readline()
            if not line:
                break
            text = line.decode("utf-8", errors="replace").strip()
            if not text:
                continue
            print(f"[recv{' ' + nick if nick else ''}] {text}")

            if text.startswith("PASS "):
                pass_given = text[5:].strip()
                continue

            if text.startswith("NICK "):
                # 표준 클라이언트는 NICK/USER를 응답을 기다리지 않고 연달아 보내므로,
                # 닉네임이 이미 등록됐는지와 무관하게 등록(USER) 상태와 합쳐서 001을 판단해야 함
                requested = text[5:].strip()
                if requested in clients:
                    await send(writer, f":testd 433 * {requested} :Nickname is already in use.")
                    continue
                old_nick = nick
                nick = requested
                clients[nick] = writer
                if old_nick:
                    clients.pop(old_nick, None)
                if welcomed and old_nick:
                    # 등록 이후(접속 중) 닉네임 변경 - 실제 IRC 서버처럼 본인 및 같은 채널
                    # 멤버 전원에게 NICK 라인을 브로드캐스트하고, 채널 멤버십 집합도 옛 닉에서
                    # 새 닉으로 갱신함 (안 하면 이후 브로드캐스트가 옛 닉을 찾다가 유실됨)
                    recipients = {writer}
                    for channel in my_channels:
                        members = channels.get(channel, set())
                        if old_nick in members:
                            members.discard(old_nick)
                            members.add(nick)
                            for m in members:
                                w = clients.get(m)
                                if w:
                                    recipients.add(w)
                    for w in recipients:
                        await send(w, f":{old_nick}!u@h NICK :{nick}")
                await maybe_welcome()
                continue

            if text.startswith("USER "):
                user_sent = True
                await maybe_welcome()
                continue

            if text.startswith("JOIN "):
                if not nick:
                    continue
                parts = text[5:].split()
                channel = parts[0]
                my_channels.add(channel)
                channels.setdefault(channel, set())
                channels[channel].add(nick)
                await broadcast(channel, f":{nick}!u@h JOIN :{channel}")
                members = " ".join(channels[channel])
                await send(writer, f":testd 353 {nick} = {channel} :{members}")
                await send(writer, f":testd 366 {nick} {channel} :End of /NAMES list.")
                continue

            if text.startswith("PART "):
                if not nick:
                    continue
                channel = text[5:].split()[0]
                if channel in my_channels:
                    my_channels.discard(channel)
                    channels.get(channel, set()).discard(nick)
                    await broadcast(channel, f":{nick}!u@h PART {channel}", exclude=nick)
                    await send(writer, f":{nick}!u@h PART {channel}")
                continue

            if text.startswith("PRIVMSG "):
                if not nick:
                    continue
                rest = text[len("PRIVMSG "):]
                target, _, msg_text = rest.partition(" :")
                if target == "NickServ":
                    identified = msg_text.strip() == f"IDENTIFY {pass_given}" and pass_given is not None
                    if identified:
                        await send(writer, ":NickServ!services@testd NOTICE * :You are now identified.")
                    else:
                        await send(writer, ":NickServ!services@testd NOTICE * :Invalid password.")
                    continue
                if msg_text.strip() == "!disconnect":
                    await send(writer, "ERROR :Closing Link: (test requested)")
                    break
                if target in clients:
                    # 닉네임 대상 1:1 메시지 (채널이 아니라 특정 유저에게 직접) - 실제 IRC 서버처럼 그 사람에게만 전달
                    await send(clients[target], f":{nick}!u@h PRIVMSG {target} :{msg_text}")
                else:
                    await broadcast(target, f":{nick}!u@h PRIVMSG {target} :{msg_text}", exclude=nick)
                continue

            if text.startswith("PONG"):
                continue

            if text.startswith("QUIT"):
                break

    except (ConnectionResetError, asyncio.IncompleteReadError):
        pass
    finally:
        if pinger:
            pinger.cancel()
        if nick:
            clients.pop(nick, None)
            for channel in list(my_channels):
                channels.get(channel, set()).discard(nick)
                await broadcast(channel, f":{nick}!u@h QUIT :bye", exclude=nick)
        writer.close()


async def main():
    server = await asyncio.start_server(handle_client, HOST, PORT)
    print(f"[test irc daemon] listening on {HOST}:{PORT}")
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
