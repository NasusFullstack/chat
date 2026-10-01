"""파이썬이 받은 줄을 보고 **무슨 일이라고 판단하는지**를 답안지로 뜬다.

`dump_irc_cases.py`가 "한 줄을 어떻게 뜯는가"를 떴다면, 여기는 그 다음 단계다 -
"그래서 무슨 일이 일어난 것인가". 참여자 목록이 바뀌었는지, 누가 말을 한 것인지,
저 줄은 화면에 보이면 안 되는 것인지.

양쪽이 같은 서버에 붙어 있으므로 **판단이 갈리면 한쪽 사람에게만 다르게 보인다.**
예를 들어 빈 366 응답을 반영해버리면 그 사람 화면에서만 참여자가 전부 사라진다
(PC에서 실제로 났던 버그다).

쓰는 법:
    python tests/dump_session_cases.py        # mobile/test/session_cases.json 을 뜬다
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, REPO)

import irc_protocol  # noqa: E402
from chat_core import events as domain_events  # noqa: E402
from chat_core.history_adapter import NullHistoryStore  # noqa: E402
from chat_core.session import build_session  # noqa: E402

OUT = os.path.join(REPO, "mobile", "test", "session_cases.json")

ME = "몽키"

# 한 묶음 = 접속부터 시작해서 줄들을 차례로 먹인 시나리오.
# **순서가 중요하다** - 상태가 쌓이면서 판단이 달라지기 때문이다
SCENARIOS = [
    {
        "name": "접속하고 채널에 들어가 이야기한다",
        "lines": [
            f":irc.test 001 {ME} :Welcome",
            f":{ME}!~m@h JOIN #일반",
            f":irc.test 353 {ME} = #일반 :@{ME} 두리 앨리스",
            f":irc.test 366 {ME} #일반 :End of /NAMES list.",
            ":두리!d@h PRIVMSG #일반 :안녕",
            f":두리!d@h PRIVMSG #일반 :@{ME} 밥 먹었어?",
            ":앨리스!a@h JOIN #일반",
            ":앨리스!a@h PART #일반 :간다",
        ],
    },
    {
        "name": "빈 참여자 응답은 반영하지 않는다",
        # 353 없이 366만 오는 경우. 그대로 반영하면 참여자가 통째로 사라진다
        "lines": [
            f":irc.test 001 {ME} :Welcome",
            f":{ME}!~m@h JOIN #일반",
            f":irc.test 353 {ME} = #일반 :@{ME} 두리",
            f":irc.test 366 {ME} #일반 :End of /NAMES list.",
            f":irc.test 366 {ME} #일반 :End of /NAMES list.",
        ],
    },
    {
        "name": "숨김 프레임은 채팅으로 새면 안 된다",
        "lines": [
            f":irc.test 001 {ME} :Welcome",
            f":{ME}!~m@h JOIN #일반",
            ":두리!d@h PRIVMSG #일반 :\x01VERSION\x01",
            ":두리!d@h PRIVMSG #일반 :\x01FCAVATAR abc 1/3 ZZZ",
            ":두리!d@h NOTICE #일반 :\x01VERSION ChupChat\x01",
            ":두리!d@h PRIVMSG #일반 :이건 보여야 한다",
        ],
    },
    {
        "name": "나간 사람과 접속 끊은 사람",
        "lines": [
            f":irc.test 001 {ME} :Welcome",
            f":{ME}!~m@h JOIN #일반",
            f":irc.test 353 {ME} = #일반 :{ME} 두리 앨리스",
            f":irc.test 366 {ME} #일반 :End of /NAMES list.",
            ":두리!d@h QUIT :Ping timeout",
            f":{ME}!~m@h PART #일반",
        ],
    },
    {
        "name": "닉네임이 밀리면 다시 시도한다",
        "lines": [
            f":irc.test 433 * {ME} :Nickname is already in use",
            f":irc.test 001 {ME}_ :Welcome",
        ],
    },
]


def _event_to_map(event) -> dict | None:
    """Dart 쪽과 맞춰볼 수 있는 모양으로. 모바일이 아직 안 쓰는 건 None(건너뜀)."""
    if isinstance(event, domain_events.LoggedIn):
        return {"type": "LoggedIn", "user_id": event.user_id}
    if isinstance(event, domain_events.ChannelJoined):
        return {"type": "ChannelJoined", "channel": event.channel, "text": event.text}
    if isinstance(event, domain_events.ChannelLeft):
        return {"type": "ChannelLeft", "channel": event.channel}
    if isinstance(event, domain_events.MessageReceived):
        return {"type": "MessageReceived", "channel": event.channel,
                "sender": event.sender, "text": event.text, "mine": event.mine,
                "is_mention": event.is_mention, "kind": event.kind}
    if isinstance(event, domain_events.SystemNotice):
        return {"type": "SystemNotice", "channel": event.channel,
                "text": event.text, "has_time": bool(event.ts)}
    if isinstance(event, domain_events.UserlistUpdated):
        return {"type": "UserlistUpdated", "channel": event.channel,
                "users": list(event.users)}
    if isinstance(event, domain_events.NicknameRetrying):
        return {"type": "NicknameRetrying", "new_nickname": event.new_nickname}
    if isinstance(event, domain_events.ConnectionClosed):
        return {"type": "ConnectionClosed", "text": event.text}
    return None


def run(lines: list[str]) -> dict:
    """줄들을 차례로 먹이고, 나온 이벤트와 서버로 나간 줄을 기록한다."""
    sent: list[str] = []
    got: list[dict] = []

    session = build_session(
        "irc", "test.invalid", 6697,
        transport=sent.append,
        on_event=lambda event: got.append(event),
        history_store=NullHistoryStore(),
    )
    session.pending_irc_nick = ME
    for line in lines:
        session.handle_incoming(irc_protocol.parse_line(line))

    events_out = [m for m in (_event_to_map(e) for e in got) if m is not None]
    return {"events": events_out, "sent": sent}


def main() -> int:
    cases = []
    for scenario in SCENARIOS:
        result = run(scenario["lines"])
        cases.append({
            "name": scenario["name"],
            "lines": scenario["lines"],
            "events": result["events"],
            "sent": result["sent"],
        })
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fp:
        json.dump({"me": ME, "cases": cases}, fp, ensure_ascii=False, indent=1)
    print(f"답안지를 떴습니다: {OUT}")
    for case in cases:
        print(f"  {case['name']}: 이벤트 {len(case['events'])}개 / 보낸 줄 {len(case['sent'])}개")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
