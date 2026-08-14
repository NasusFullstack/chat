"""창 크기/위치 계산(화면도 위젯도 모르는 순수 계산).

채널 목록을 접고 펴면 그만큼 **창 왼쪽 변만** 움직여야 한다.
- 오른쪽 변을 움직이면 대화창과 참여자 목록이 통째로 끌려간다("왜 오른쪽이 딸려오지?")
- 왼쪽 변이 움직이면 접히고 펴지는 자리(채널 목록)만 늘었다 줄었다 하는 것처럼 보인다

화면 밖으로 나가면 안 되므로 두 가지를 지킨다.
- 왼쪽 변이 화면 왼쪽보다 왼쪽으로 가지 않는다
- 그래도 안 들어가면 폭을 화면만큼으로 줄인다(그때는 대화창이 조금 좁아질 수밖에 없다)
"""


def widen_to_left(x: int, width: int, delta: int, screen_left: int, screen_right: int,
                  min_width: int = 0) -> tuple:
    """오른쪽 변을 고정한 채 폭을 delta만큼 바꾼다. (새 x, 새 폭)을 돌려준다.

    delta > 0 이면 왼쪽으로 넓어지고, < 0 이면 왼쪽에서 줄어든다.
    """
    right_edge = x + width
    target = max(min_width, width + delta)
    screen_width = screen_right - screen_left + 1
    if screen_width > 0:
        target = min(target, screen_width)

    new_x = right_edge - target
    if new_x < screen_left:
        new_x = screen_left
    if new_x + target - 1 > screen_right:
        new_x = max(screen_left, screen_right - target + 1)
    return new_x, target
