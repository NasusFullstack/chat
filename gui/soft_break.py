"""공백 없이 길게 이어진 글이 화면 밖으로 나가지 않게 접을 자리를 만들어 준다.

실제 사고(2026-08-13): 장문을 보냈더니 **줄바꿈이 안 되고 글이 안 보였다.**
재보니 Qt는 공백이 없는 덩어리를 아예 접지 않는다 - 접을 자리가 없다고 보기 때문이다.
실측(폭 400에 1400자, 공백 없음):

| 방법 | 높이 |
|---|---|
| 일반 글자(PlainText) | 12 (한 줄, 안 접힘) |
| 서식 글자(RichText, 우리 방식) | 14 (안 접힘) |
| CSS `word-wrap:break-word` | 14 (Qt가 이 속성을 모른다) |
| **글자 사이에 폭 0인 공백 넣기** | **392 (제대로 접힘)** |

그래서 화면에 그릴 때만 `U+200B`(눈에 안 보이고 폭도 0인 공백)를 끼워 넣는다.
보내는 글자는 건드리지 않는다 - 상대에게는 원래 글이 그대로 간다.

한글/중국어처럼 띄어쓰기 없이 길게 쓰는 경우가 흔해서, 이게 없으면 그런 메시지는
통째로 안 보인다.
"""

ZERO_WIDTH_SPACE = "​"
# 이만큼 공백 없이 이어지면 그 자리에 접을 기회를 준다. 너무 작으면 평범한 글에도
# 자꾸 끼어들고(복사할 때 따라붙는다), 너무 크면 좁은 창에서 여전히 삐져나간다
MAX_RUN = 25


def add_break_hints(html: str, max_run: int = MAX_RUN) -> str:
    """HTML 안의 **보이는 글자**에만 접을 자리를 넣는다.

    태그(`<a href=...>`)와 실체 참조(`&lt;`)는 건드리지 않는다 - 그 안에 끼워 넣으면
    주소가 깨지거나 글자가 이상해진다.
    """
    if not html:
        return html
    out = []
    run = 0
    index = 0
    length = len(html)
    while index < length:
        char = html[index]
        if char == "<":                      # 태그는 통째로 넘긴다
            end = html.find(">", index)
            if end < 0:
                out.append(html[index:])
                break
            out.append(html[index:end + 1])
            index = end + 1
            continue
        if char == "&":                      # &lt; 같은 것은 한 글자로 친다
            end = html.find(";", index)
            if 0 <= end <= index + 10:
                out.append(html[index:end + 1])
                index = end + 1
                run += 1
                if run >= max_run:
                    out.append(ZERO_WIDTH_SPACE)
                    run = 0
                continue
        if char.isspace() or char == ZERO_WIDTH_SPACE:
            run = 0
        else:
            run += 1
            if run >= max_run:
                out.append(char)
                out.append(ZERO_WIDTH_SPACE)
                run = 0
                index += 1
                continue
        out.append(char)
        index += 1
    return "".join(out)
