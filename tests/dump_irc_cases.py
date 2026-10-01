"""파이썬이 IRC 한 줄을 어떻게 해석하는지를 **답안지로 떠서** 모바일에 넘긴다.

## 왜 이렇게 하나
PC 앱과 모바일 앱은 같은 서버에 붙어 같은 사람들과 이야기한다. 한쪽만 다르게 해석하면
그 사람에게만 글자가 깨지거나 명령이 안 먹는데, 양쪽을 따로 시험하면 그걸 못 잡는다.
"둘 다 통과"가 아니라 **"둘의 답이 같다"**를 봐야 한다.

그래서 파이썬 쪽 결과를 JSON으로 떠놓고, Dart 검사가 그 파일을 읽어 자기 답과 맞춰본다.
파이썬을 고치면 답안지가 바뀌고, 그러면 Dart 검사가 깨지면서 "모바일도 고쳐야 한다"고
알려준다. 이게 두 앱이 갈라지지 않게 하는 장치다.

나중에 전투 계산(`battle_sim.py`)을 옮길 때도 같은 방식을 쓴다 - 그쪽은 한 틱만 어긋나도
"한 놈은 죽었다는데 다른 쪽은 안 죽었다"가 되므로 더 중요하다.

쓰는 법:
    python tests/dump_irc_cases.py        # mobile/test/irc_cases.json 을 새로 뜬다
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, REPO)

import irc_protocol  # noqa: E402

OUT = os.path.join(REPO, "mobile", "test", "irc_cases.json")

# 실제로 서버가 보내는 모양들. 까다로운 것 위주로 모았다
LINES = [
    ":irc.example.com 001 몽키 :Welcome to the Internet Relay Network",
    ":몽키!~mong@1.2.3.4 PRIVMSG #일반 :안녕 다들 뭐해",
    ":몽키!~mong@1.2.3.4 PRIVMSG #일반 :공백   여러   개",
    ":두리!d@host PRIVMSG 몽키 :귓속말이야",
    "PING :1234567890",
    ":irc.example.com 353 몽키 = #일반 :@몽키 +두리 앨리스 ~밥",
    ":irc.example.com 366 몽키 #일반 :End of /NAMES list.",
    ":몽키!~m@h JOIN #개발",
    ":몽키!~m@h PART #개발 :나간다",
    ":몽키!~m@h QUIT :Client Quit",
    ":irc.example.com 433 * 몽키 :Nickname is already in use",
    "@time=2026-09-30T00:00:00Z :몽키!~m@h PRIVMSG #일반 :태그 달린 줄",
    ":서버 NOTICE * :*** Looking up your hostname...",
    # 마지막 칸 안에 ' :' 가 또 들어 있는 경우 - 한 번만 갈라야 한다
    ":몽키!~m@h PRIVMSG #일반 :시간 10 :30 에 보자",
    # 프리픽스도 마지막 칸도 없는 줄
    "ERROR",
    # 숨김 프레임(우리끼리 쓰는 것) - 채팅으로 새면 안 된다
    ":몽키!~m@h PRIVMSG #일반 :\x01VERSION\x01",
    ":몽키!~m@h PRIVMSG #일반 :\x01ACTION 춤춘다\x01",
    # 잘린 숨김 프레임 - 닫는 문자가 없어도 프레임으로 봐야 한다
    ":몽키!~m@h PRIVMSG #일반 :\x01FCAVATAR abc 1/3 ZZZ",
    ":irc.example.com 475 몽키 #비밀방 :Cannot join channel (+k)",
]

TEXTS_TO_SPLIT = [
    "",
    "짧은 글",
    "가" * 200,                       # 한글 600바이트 - 글자 중간이 잘리면 안 된다
    "띄어쓰기가 " * 80,               # 띄어쓰기에서 잘려야 한다
    "a" * 1000,                       # 띄어쓰기 없는 영문
    "짧은앞부분 " + "나" * 300,       # 앞에만 띄어쓰기
    "영문 and 한글 섞인 글 " * 40,
]

CHANNEL_NAMES = ["일반", "#일반", "  개발  ", "&로컬", "+모드", "!느낌표", "", "   "]

FRAME_TEXTS = ["\x01VERSION\x01", "\x01잘린것", "보통 글", "", " \x01앞에공백"]


def dump() -> dict:
    cases = {
        "parse": [],
        "split": [],
        "normalize_channel": [],
        "is_ctcp_frame": [],
        "names_reply": [],
        "constants": {
            "MAX_MESSAGE_BYTES": irc_protocol.MAX_MESSAGE_BYTES,
            "MAX_NICK_RETRIES": irc_protocol.MAX_NICK_RETRIES,
            "NICK_COLLISION_NUMERICS": sorted(irc_protocol.NICK_COLLISION_NUMERICS),
            "CHANNEL_JOIN_ERROR_NUMERICS": sorted(
                irc_protocol.CHANNEL_JOIN_ERROR_NUMERICS),
        },
        "format": {
            "pass": irc_protocol.format_pass("비밀"),
            "nick": irc_protocol.format_nick("몽키"),
            "user": irc_protocol.format_user("mong", "몽키 님"),
            "join": irc_protocol.format_join("#일반"),
            "join_key": irc_protocol.format_join("#비밀", "열쇠"),
            "privmsg": irc_protocol.format_privmsg("#일반", "안녕"),
            "notice": irc_protocol.format_notice("몽키", "알림"),
            "part": irc_protocol.format_part("#일반"),
            "part_reason": irc_protocol.format_part("#일반", "간다"),
            "quit": irc_protocol.format_quit(),
            "quit_reason": irc_protocol.format_quit("종료"),
            "pong": irc_protocol.format_pong("1234"),
            "ping": irc_protocol.format_ping("1234"),
            "names": irc_protocol.format_names("#일반"),
        },
    }

    for line in LINES:
        msg = irc_protocol.parse_line(line)
        cases["parse"].append({
            "line": line,
            "prefix": msg.prefix,
            "command": msg.command,
            "params": msg.params,
            "source_nick": msg.source_nick,
            "trailing": msg.trailing,
        })

    for text in TEXTS_TO_SPLIT:
        cases["split"].append({"text": text,
                               "pieces": irc_protocol.split_message(text)})

    for name in CHANNEL_NAMES:
        cases["normalize_channel"].append(
            {"name": name, "out": irc_protocol.normalize_channel(name)})

    for text in FRAME_TEXTS:
        cases["is_ctcp_frame"].append(
            {"text": text, "out": irc_protocol.is_ctcp_frame(text)})

    for line in LINES:
        msg = irc_protocol.parse_line(line)
        if msg.command == irc_protocol.RPL_NAMREPLY:
            cases["names_reply"].append(
                {"line": line, "names": irc_protocol.parse_names_reply(msg)})

    return cases


def main() -> int:
    cases = dump()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fp:
        json.dump(cases, fp, ensure_ascii=False, indent=1)
    total = sum(len(v) for v in cases.values() if isinstance(v, list))
    print(f"답안지를 떴습니다: {OUT}")
    print(f"  줄 해석 {len(cases['parse'])}개 / 줄 나누기 {len(cases['split'])}개 "
          f"/ 그 밖 {total - len(cases['parse']) - len(cases['split'])}개")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
