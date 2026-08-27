"""늦게 도착한 내용 때문에 크기가 바뀌었다고 위쪽에 알리는 **한 곳**.

그림·카드·이모티콘은 전부 네트워크로 뒤늦게 도착한다. 도착하면 그 자리의 크기가
바뀌는데, 그걸 위쪽 레이아웃에 제대로 알리지 않으면 예전 크기가 그대로 남아 채팅
맨 아래에 빈 공간이 생긴다(CLAUDE.md 9번과 같은 뿌리).

**왜 파일을 따로 뒀는가**: 이 알림을 각자 손으로 짜다가 실제로 사고가 났다.
2026-08-26 실측 - 이모티콘을 한 메시지에 여러 개 넣으면 맨 아래에 최대 1184px의
빈 공간이 남았다. 링크 미리보기는 멀쩡했는데, 두 경로가 하는 일이 미묘하게 달랐다:

| 알린 방법 | 조상 레이아웃 invalidate | 결과 |
|---|---|---|
| 링크 미리보기 | 함 | 공백 0px |
| 이모티콘 | **안 함** | 공백 1184px |

`updateGeometry()`만 부르면 **바로 위 부모의 레이아웃까지만** 무효가 된다(Qt는
`QLayout::update()`에서 그 레이아웃을 가진 위젯에 LayoutRequest를 보내고 멈춘다).
대화 목록의 레이아웃은 그대로 '도착 전 높이'를 캐시하고 있으므로, 곧바로 높이를
다시 재봐야 옛 값이 나온다. 그래서 **조상 레이아웃을 전부 무효로 만든 다음**에
알려야 한다.

지금은 부르는 쪽이 대화 목록을 알 필요가 없다 - 무효로 만들면 LayoutRequest가
대화 목록 안쪽 위젯까지 올라가고, 그쪽이 알아서 높이를 다시 잰다
(`_ChatLogContent.event`). 새 미리보기 종류를 추가할 때도 이 함수 한 줄만 부르면 된다.
"""
from PySide6.QtWidgets import QWidget


def size_changed(widget: QWidget) -> None:
    """이 위젯의 크기가 바뀌었다 - 위쪽 배치를 전부 다시 계산하게 한다."""
    widget.updateGeometry()
    parent = widget.parentWidget()
    while parent is not None:
        layout = parent.layout()
        if layout is not None:
            # 캐시된 옛 크기를 버리게 한다. 이걸 빼면 바로 위 부모까지만 갱신되고
            # 대화 목록은 도착 전 높이를 그대로 쓴다(위 표의 1184px 사고)
            layout.invalidate()
        parent.updateGeometry()
        parent = parent.parentWidget()
