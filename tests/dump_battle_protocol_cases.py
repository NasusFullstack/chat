"""전투 규약의 답안지를 뜬다 - **무엇을 받아주고 무엇을 버리는가**.

## 왜 이것까지 대조하나
받은 줄은 전부 남이 정한 값이다. 서버가 보낸 것이라도 마찬가지다(그 서버에 남이
붙어 있다). 한쪽이 더 헐겁게 받아주면 거기서만 이상한 값이 들어와 배가 엉뚱한 자리로
가거나, 체력이 음수가 되거나, 남의 배를 대신 신고하는 길이 열린다.

그래서 **같은 줄에 같은 답**이 나오는지 본다 - 받아줄 것은 모양까지 같게, 버릴 것은
양쪽 다 버리게.

쓰는 법:
    python tests/dump_battle_protocol_cases.py
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, REPO)

import battle_protocol as bp  # noqa: E402

OUT = os.path.join(REPO, "mobile", "test", "battle_protocol_cases.json")

ROOM = "a1b2c3d4e5f6"

# 받은 줄(글자 그대로)과 그때 나와야 하는 답. 답이 None 이면 버려야 한다는 뜻
LINES = [
    # ---- 제대로 된 것들 ----
    '{"t":"welcome","slot":0,"tick":0,"cap":6,"color":3,"players":[],"bots":0}',
    '{"t":"welcome","slot":2,"tick":120,"cap":4,"color":0,'
    '"players":[{"slot":0,"nick":"몽키","color":1},{"slot":1,"nick":"두리","color":2}],'
    '"bots":2,"started":true}',
    '{"t":"joined","slot":3,"nick":"새사람","color":5}',
    '{"t":"left","slot":3}',
    '{"t":"started"}',
    '{"t":"deny","why":"정원이 찼습니다"}',
    '{"t":"peer","slot":1,"tick":55,"keys":19}',
    '{"t":"peerhit","slot":1,"by":0,"hp":240}',
    '{"t":"peerdead","slot":1,"by":0,"hp":0}',
    '{"t":"bye"}',

    # ---- 버려야 하는 것들 ----
    '',                                        # 빈 줄
    'not json',                                # JSON 이 아님
    '[1,2,3]',                                 # 사전이 아님
    '{"t":"모르는것","slot":0}',                # 표에 없는 종류
    '{"t":"peer","slot":99,"tick":5,"keys":1}',       # 자리 번호가 범위 밖
    '{"t":"peer","slot":-1,"tick":5,"keys":1}',       # 음수 자리
    '{"t":"peer","slot":1,"tick":5,"keys":999}',      # 키 비트가 범위 밖
    '{"t":"peer","slot":1,"tick":-5,"keys":1}',       # 틱이 음수
    '{"t":"peer","slot":1,"tick":5}',                 # 키가 없음
    '{"t":"peer","slot":"1","tick":5,"keys":1}',      # 자리가 글자
    '{"t":"peer","slot":true,"tick":5,"keys":1}',     # 참/거짓은 정수가 아니다
    '{"t":"peerhit","slot":1,"by":0}',                # 남은 체력이 없음
    '{"t":"peerhit","slot":1,"by":0,"hp":-1}',        # 체력이 음수
    '{"t":"peerhit","slot":1,"by":0,"hp":99999}',     # 체력이 너무 큼
    '{"t":"welcome","slot":0,"tick":0,"cap":6,"color":3}',          # 참가자 목록 없음
    '{"t":"welcome","slot":0,"tick":0,"cap":1,"color":0,"players":[]}',   # 정원이 너무 작음
    '{"t":"welcome","slot":0,"tick":0,"cap":6,"color":3,"players":[{"nick":"자리없음"}]}',
    '{"t":"left","slot":"셋"}',
    '{"t":"joined","slot":40,"nick":"범위밖","color":0}',
]

# 보내는 쪽 - 우리가 만든 줄이 양쪽에서 같은 글자여야 한다
TO_SEND = [
    {"t": bp.JOIN, "room": ROOM, "nick": "몽키", "color": 3, "cap": 4, "bots": 2},
    {"t": bp.START},
    {"t": bp.INPUT, "tick": 42, "keys": 19},
    {"t": bp.HIT, "by": 1, "hp": 240},
    {"t": bp.DEAD, "by": 1, "hp": 0},
    {"t": bp.BYE},
]

# 닉네임 다듬기 - 제어문자와 길이. 남의 이름이 화면을 망가뜨리지 않게
NICKS = [
    "몽키",
    "  앞뒤 공백  ",
    "제어\x01문자\x1f섞임",
    "가" * 40,
    "",
]


def main():
    data = {
        "limits": {
            "MAX_LINE_BYTES": bp.MAX_LINE_BYTES,
            "MAX_HUMANS": bp.MAX_HUMANS,
            "MAX_BOTS": bp.MAX_BOTS,
            "MAX_PLAYERS": bp.MAX_PLAYERS,
            "MIN_PLAYERS": bp.MIN_PLAYERS,
            "MAX_NICK_LEN": bp.MAX_NICK_LEN,
            "COLOR_COUNT": bp.COLOR_COUNT,
            "RAINBOW_COLOR": bp.RAINBOW_COLOR,
            "MAX_TICK": bp.MAX_TICK,
            "MAX_HP": bp.MAX_HP,
            "KEY_MASK": bp.KEY_MASK,
        },
        "decode": [
            {"line": line, "want": bp.decode(line.encode("utf-8"))}
            for line in LINES
        ],
        "encode": [
            {"message": message,
             "line": bp.encode(message).decode("utf-8").rstrip("\n")}
            for message in TO_SEND
        ],
        "nicks": [{"raw": nick, "safe": bp.safe_nick(nick)} for nick in NICKS],
        "rooms": [
            {"value": ROOM, "ok": bp.is_room_id(ROOM)},
            {"value": "A1B2C3D4", "ok": bp.is_room_id("A1B2C3D4")},
            {"value": "짧음", "ok": bp.is_room_id("짧음")},
            {"value": "zzzzzzzz", "ok": bp.is_room_id("zzzzzzzz")},
            {"value": "a1b2", "ok": bp.is_room_id("a1b2")},
        ],
        # 채팅으로 오가는 '방 번호 알림' - 이걸 못 알아보면 전투에 못 들어간다
        "notices": [
            {"text": bp.format_room_notice(ROOM), "room": ROOM},
            {"text": "\x01CHUPBATTLE ROOM " + ROOM + "\x01", "room": ROOM},
            {"text": "그냥 채팅입니다", "room": ""},
            {"text": "\x01CHUPBATTLE ROOM 짧음\x01", "room": ""},
        ],
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fp:
        json.dump(data, fp, ensure_ascii=False)
    kept = sum(1 for one in data["decode"] if one["want"] is not None)
    print(f"{OUT} 에 적었습니다")
    print(f"  받은 줄 {len(LINES)}개 - 받아줄 것 {kept}개, 버릴 것 {len(LINES) - kept}개")
    print(f"  보낼 줄 {len(TO_SEND)}개, 닉네임 {len(NICKS)}개")


if __name__ == "__main__":
    main()
