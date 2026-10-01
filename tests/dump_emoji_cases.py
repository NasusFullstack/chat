"""메시지 안의 이모티콘을 어떻게 가르는지 답안지로 뜬다.

짝이 안 맞는 표시를 한쪽만 다르게 다루면 그 사람 화면에서만 대화가 사라지거나
이상한 글자가 뜬다. 그래서 까다로운 경우 위주로 모았다.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, REPO)

from chat_core import commands  # noqa: E402

OUT = os.path.join(REPO, "mobile", "test", "emoji_cases.json")
OPEN, CLOSE = commands.EMOJI_OPEN, commands.EMOJI_CLOSE
URL = "https://jsserv.pdlab.kr/files/aabbccddeeff00112233445c/%EC%A7%A4.png"

TEXTS = [
    "그냥 글",
    "",
    commands.format_emoji(URL),
    "이거 봐 " + commands.format_emoji(URL) + " 귀엽지",
    commands.format_emoji(URL) + commands.format_emoji(URL),
    # 짝이 안 맞는 것들 - 대화가 사라지면 안 된다
    "닫는 표시가 없음 " + OPEN + URL,
    "여는 표시가 없음 " + URL + CLOSE,
    OPEN + CLOSE,
    OPEN + OPEN + URL + CLOSE,
    "앞" + OPEN + URL + CLOSE + "뒤",
]


def main() -> int:
    cases = {
        "open": OPEN,
        "close": CLOSE,
        "format": commands.format_emoji(URL),
        "split": [
            {"text": text,
             "parts": [{"kind": kind, "value": value}
                       for kind, value in commands.split_emoji_parts(text)]}
            for text in TEXTS
        ],
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fp:
        json.dump(cases, fp, ensure_ascii=False, indent=1)
    print(f"답안지를 떴습니다: {OUT} ({len(cases['split'])}개)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
