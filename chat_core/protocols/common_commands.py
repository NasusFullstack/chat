"""두 프로토콜이 똑같이 처리할 수 있는 슬래시 명령들 (믹스인).

명령 "실행"은 원칙적으로 프로토콜 전략의 몫이다(프로토콜마다 할 수 있는 게 다르므로).
다만 /me나 /join처럼 이미 ProtocolPort에 있는 동작으로 그대로 환원되는 것들은 양쪽에
똑같은 코드를 복붙할 이유가 없어서 여기 모아두고 상속으로 합친다.

각 프로토콜은 COMMON_COMMANDS(명세->핸들러)에 자기 전용 명령을 더해서 최종 표를 만든다.
새 명령을 추가할 때 ChatSession은 전혀 안 건드려도 되는 게 이 구조의 요점(OCP).
"""
from chat_core import commands, events


class CommonCommands:
    def _cmd_help(self, session, channel: str, args: str) -> None:
        lines = [f"{spec.usage}  -  {spec.help}" for spec in self.command_specs()]
        session.emit(events.CommandHelp(channel, lines))

    def _cmd_me(self, session, channel: str, args: str) -> None:
        if not args:
            session.emit(events.CommandError(f"사용법: {commands.ME.usage}"))
            return
        # 일반 채팅과 같은 경로로 보내야 @호출 쿨타임 정책이 그대로 적용됨
        session.send_wire_chat(channel, commands.format_action(args), args)

    def _cmd_join(self, session, channel: str, args: str) -> None:
        if not args:
            session.emit(events.CommandError(f"사용법: {commands.JOIN.usage}"))
            return
        name, _, key = args.partition(" ")
        session.join_channel(session.normalize_channel(name), key.strip())

    def _cmd_part(self, session, channel: str, args: str) -> None:
        target = session.normalize_channel(args) if args else channel
        if not target:
            session.emit(events.CommandError("나갈 채널이 없습니다."))
            return
        session.leave_channel(target)

    def _cmd_nick(self, session, channel: str, args: str) -> None:
        if not args:
            session.emit(events.CommandError(f"사용법: {commands.NICK.usage}"))
            return
        session.set_nickname(args.split()[0])

    COMMON_COMMANDS = {
        commands.HELP: _cmd_help,
        commands.ME: _cmd_me,
        commands.JOIN: _cmd_join,
        commands.PART: _cmd_part,
        commands.NICK: _cmd_nick,
    }
