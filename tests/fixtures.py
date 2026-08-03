"""테스트가 쓰는 가짜 대화 기록.

예전에는 개발자 PC에 설치된 앱의 history.json을 직접 읽어서 재현했는데, 그러면 그
사람 PC에서만 도는 테스트가 된다. 실제 대화와 같은 성격(짧은 한글 줄이 대부분,
가끔 긴 줄과 링크)만 갖추면 레이아웃 문제는 그대로 재현되므로 여기서 만들어 쓴다.
"""

SENDERS = ("Mong", "Ming", "hjsong", "hjsong_mobile", "MangMang2")

_SHORT = (
    "ㄷㄷ", "ㅋㅋㅋㅋㅋ", "머지", "그러네", "아 진짜?", "굿굿", "ㅇㅇ",
    "밥먹자", "지금감", "왜 안돼", "다시 해봐", "확인했어", "깔깔",
    "그건 아닌듯", "오케이", "잠깐만", "된다", "안된다",
)
_LONG = (
    "이거 서버쪽 문제인지 클라 문제인지 모르겠는데 일단 로그부터 봐야 할 것 같아",
    "아까 그 화면에서 스크롤 내리면 아무것도 안 보이고 빈 공간만 계속 나오더라고",
    "모듈화가 안 되어 있으면 이런 거 고칠 때 눈이 팽팽 돌아서 못 고쳐",
)


def sample_history(count: int = 200) -> list[dict]:
    """history.json에서 읽어오던 것과 같은 모양의 기록 목록."""
    out = []
    for i in range(count):
        if i % 17 == 0:
            text = _LONG[i % len(_LONG)]
        elif i % 29 == 0:
            text = "https://example.com/some/page?id=" + str(i)
        else:
            text = _SHORT[i % len(_SHORT)]
        out.append({
            "from": SENDERS[i % len(SENDERS)],
            "text": text,
            "ts": 1_700_000_000 + i * 7,
        })
    return out
