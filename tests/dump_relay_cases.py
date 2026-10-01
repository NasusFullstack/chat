"""중계 서버 자리 이름(id)을 답안지로 뜬다.

**여기가 틀리면 조용히 갈라진다.** PC와 모바일이 같은 채널에 있는데 기록은 서로 다른
칸에 쌓이고, 같은 사람인데 얼굴이 안 보이고, 이모티콘 목록이 따로 논다. 오류가 안 나고
그냥 "안 보인다"로만 나타나서 원인을 찾기도 어렵다.

대소문자를 낮추는 방식이 파이썬(casefold)과 Dart(toLowerCase)에서 다를 수 있어서,
실제로 쓰는 글자들로 양쪽 답을 맞춰본다.

쓰는 법:
    python tests/dump_relay_cases.py        # mobile/test/relay_cases.json 을 뜬다
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, REPO)

import relay  # noqa: E402

OUT = os.path.join(REPO, "mobile", "test", "relay_cases.json")

# (프로토콜, 호스트, 포트) 묶음 - 실제로 쓰는 것과 헷갈리기 쉬운 것들
PLACES = [
    ("irc", "home.pdlab.kr", 6697),
    ("irc", "HOME.PDLAB.KR", 6697),      # 대문자여도 같은 자리여야 한다
    ("irc", "home.pdlab.kr", 6667),      # 포트가 다르면 다른 자리
    ("irc", "other.example.com", 6697),  # 서버가 다르면 다른 자리
    ("custom", "home.pdlab.kr", 6697),   # 프로토콜이 다르면 다른 자리
]

CHANNELS = ["#일반", "#General", "#general", "#개발", "#잡담", "일반", ""]
NICKS = ["몽키", "MongKey", "mongkey", "두리", "Ångström", ""]

FILE_URLS = [
    f"{relay.SERVER}/files/aabbccddeeff00112233445c/문서.pdf",
    f"{relay.SERVER}/files/aabbccddeeff00112233445c/a.png?x=1",
    f"{relay.SERVER}/files/emoji?group=aaaaaaaaaaaaaaaaaaaaaaaa",
    f"{relay.SERVER}/files/TOOSHORT/a.png",
    f"{relay.SERVER}/files/zzbbccddeeff00112233445c/a.png",   # 16진수가 아님
    "https://example.com/files/aabbccddeeff00112233445c/a.png",
    "",
]


def main() -> int:
    cases = {
        "urls": {
            "server": relay.SERVER,
            "battle": relay.BATTLE_URL,
            "files": relay.FILES_URL,
            "logs": relay.LOGS_URL,
            "profiles": relay.PROFILES_URL,
        },
        "id_chars": relay.ID_CHARS,
        "room": [],
        "who": [],
        "group": [],
        "file_id": [],
        "meta_url": relay.meta_url("aabbccddeeff00112233445c"),
    }

    for protocol, host, port in PLACES:
        cases["group"].append({
            "protocol": protocol, "host": host, "port": port,
            "id": relay.group_id(protocol, host, port),
        })
        for channel in CHANNELS:
            cases["room"].append({
                "protocol": protocol, "host": host, "port": port,
                "channel": channel,
                "id": relay.room_id(protocol, host, port, channel),
            })
        for nick in NICKS:
            cases["who"].append({
                "protocol": protocol, "host": host, "port": port, "nick": nick,
                "id": relay.who_id(protocol, host, port, nick),
            })

    for url in FILE_URLS:
        cases["file_id"].append({"url": url, "id": relay.file_id_from(url)})

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fp:
        json.dump(cases, fp, ensure_ascii=False, indent=1)

    print(f"답안지를 떴습니다: {OUT}")
    print(f"  방 {len(cases['room'])}개 / 사람 {len(cases['who'])}개 "
          f"/ 무리 {len(cases['group'])}개 / 파일 주소 {len(cases['file_id'])}개")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
