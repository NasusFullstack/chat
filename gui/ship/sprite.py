"""배틀크루저 스프라이트 읽기 - 파일 찾기, 배경 지우기, 팀 컬러 바꾸기, 방향별로 자르기.

원본 게임 이미지는 저장소에 올리지 않는다(각자 자기 폴더에 넣어서 씀). 파일이 없으면
gui/ship/painter.py가 직접 그린 그림으로 대체되므로 없어도 정상 동작한다.

픽셀을 훑는 일이라 느려지기 쉽다 - 예전에 pixelColor()로 30만 픽셀을 돌다가 첫 소환 때
화면이 멈췄다. 지금은 QImage.bits()로 원시 버퍼를 한 번에 다룬다.
"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage, QPixmap

from gui.helpers import _find_image_in_app_dirs

# 회색 팀 컬러 (원본의 연보라 자리)
_TEAM = QColor("#b9bdc7")
_TEAM_DARK = QColor("#6e727c")
_HULL_LIGHT = QColor("#9aa0ab")
_HULL_MID = QColor("#6b7079")
_HULL_DARK = QColor("#3e424b")
_OUTLINE = QColor("#22252b")
_ENGINE = QColor("#cfe8ff")


SPRITE_FILENAME = "battlecruiser.png"
SPRITE_MAX_PX = 256
# 가로가 세로보다 이 배 이상 길면 "방향별 프레임을 가로로 이어붙인 스트립"으로 봄.
# 배 한 대짜리 그림과 스트립을 파일명 하나로 같이 받기 위한 구분 규칙
STRIP_MIN_ASPECT = 8
FRAME_MAX_PX = 128  # 스트립 한 칸의 최대 크기(그릴 때 96px 안팎이라 이 이상은 낭비)
_sprite_cache: list = []  # [_Sprite] 또는 [None] - 파일 탐색/변환을 한 번만 하려고 캐시


WHITE_BG_THRESHOLD = 246  # 이 값 이상인 흰색만 배경으로 봄
TEAM_GRAY_MAX = 185  # 팀 컬러를 회색으로 옮길 때의 최대 밝기(255면 순백이 되어 얼룩짐)


def _convert_pixels(image: QImage) -> QImage:
    """흰 배경 -> 투명, 팀 컬러(분홍) -> 회색. 두 변환을 한 번에 훑음.

    - 스프라이트 시트는 보통 흰 배경 위에 유닛이 올라가 있어서, 그대로 쓰면 채팅창 위에
      흰 네모가 깔림. 함선의 가장 밝은 부분도 순백까지는 안 가므로 임계값을 아주 높게
      잡으면 배경만 안전하게 날아감(이미 투명 배경인 이미지에는 아무 영향 없음).
    - 스타 유닛 스프라이트는 팀 컬러를 분홍으로 칠해두고 플레이어 색으로 치환하는 구조라,
      분홍 계열(R·B는 높고 G는 낮음)만 골라 회색으로 옮기면 회색 팀이 됨. 이때 밝기를
      그대로 쓰면 안 됨 - 가장 밝은 분홍(#ff00ff)이 순백이 되어 함선에 흰 얼룩처럼 남음.
      TEAM_GRAY_MAX까지로 눌러서 중간 회색 범위에 들어오게 함.

    픽셀마다 QColor 객체를 만드는 pixelColor()를 쓰면 32칸짜리 방향 스트립(30만 픽셀
    이상)에서 수 초씩 걸려 첫 소환 때 화면이 멈춤. 원시 버퍼를 직접 훑어서 피함.
    """
    image = image.convertToFormat(QImage.Format.Format_ARGB32)
    buf = image.bits()  # ARGB32는 리틀엔디안에서 B,G,R,A 순으로 저장됨
    stride = image.bytesPerLine()
    width, height = image.width(), image.height()
    for y in range(height):
        row = y * stride
        for x in range(width):
            i = row + x * 4
            if buf[i + 3] == 0:
                continue
            b, g, r = buf[i], buf[i + 1], buf[i + 2]
            if r >= WHITE_BG_THRESHOLD and g >= WHITE_BG_THRESHOLD and b >= WHITE_BG_THRESHOLD:
                buf[i + 3] = 0
            elif r > 90 and b > 90 and g + 60 < min(r, b):
                level = max(r, b) * TEAM_GRAY_MAX // 255
                buf[i] = buf[i + 1] = buf[i + 2] = level
    return image


def _trim_transparent(image: QImage) -> QImage:
    """투명한 바깥 여백을 잘라냄.

    스프라이트 시트에서 배 한 대를 오려낼 때 여백이 넉넉히 남기 마련인데, 그대로 두면
    회전 중심이 배가 아니라 여백 한가운데가 돼서 제자리에서 도는 게 아니라 원을 그리며
    돌아버림. 실제 그림이 차지하는 영역만 남겨서 중심을 맞춤.
    """
    image = image.convertToFormat(QImage.Format.Format_ARGB32)
    left, top = image.width(), image.height()
    right = bottom = -1
    for y in range(image.height()):
        for x in range(image.width()):
            if image.pixelColor(x, y).alpha() > 8:
                left = min(left, x)
                right = max(right, x)
                top = min(top, y)
                bottom = max(bottom, y)
    if right < 0:  # 전부 투명하면 그대로 둠
        return image
    return image.copy(left, top, right - left + 1, bottom - top + 1)


class _Sprite:
    """불러온 함선 그림. 방향별 프레임이 있으면 골라 쓰고, 없으면 한 장을 회전시킴.

    실제 게임은 방향별 그림을 미리 그려두고 고르는 방식이다. 아이소메트릭 그림을
    회전시키면 각도가 어긋나 보이므로, 프레임이 있으면 회전을 아예 하지 않는다.
    """

    def __init__(self, frames: list[QPixmap]):
        self.frames = frames

    @property
    def directional(self) -> bool:
        return len(self.frames) > 1

    def pick(self, facing_deg: float) -> QPixmap:
        """진행 방향(위=0, 시계방향)에 가장 가까운 프레임.

        0번 프레임이 정북이고 번호가 늘수록 시계방향이라는 전제 - 시트에서 프레임을
        뽑을 때 실제로 측정해 확인한 규칙이다(측정: 0=북, 8=동, 16=남, 24=서).
        """
        count = len(self.frames)
        if count == 1:
            return self.frames[0]
        step = 360.0 / count
        return self.frames[int(round(facing_deg / step)) % count]


def _slice_strip(image: QImage) -> list[QImage]:
    """가로로 이어붙인 방향 프레임 스트립을 한 칸씩 나눔. 스트립이 아니면 통째로 한 장."""
    width, height = image.width(), image.height()
    if height <= 0 or width < height * STRIP_MIN_ASPECT:
        return [image]
    count = int(round(width / height))
    if count < 2:
        return [image]
    cell = width / count
    return [image.copy(int(round(i * cell)), 0, int(round(cell)), height) for i in range(count)]


def _load_sprite() -> "_Sprite | None":
    """battlecruiser.png가 있으면 그 이미지를, 없으면 아래 _draw_ship()으로 직접 그림.

    파일은 두 가지 형태를 다 받는다:
    - 배 한 대짜리 그림 -> 진행 방향으로 회전시켜 씀
    - 방향별 프레임을 가로로 이어붙인 스트립 -> 회전 없이 프레임을 골라 씀(자연스러움)
    구분은 가로세로 비로 함(STRIP_MIN_ASPECT).

    찾는 곳은 로고(icon.png)와 완전히 같은 경로 규칙 - 설치 폴더와 PyInstaller 번들
    양쪽을 봄. 파일이 없으면 그냥 직접 그린 함선이 나옴(둘 다 정상 동작).
    """
    if _sprite_cache:
        return _sprite_cache[0]
    path = _find_image_in_app_dirs((SPRITE_FILENAME,))
    sprite = None
    if path:
        image = QImage(path)
        if not image.isNull():
            image = _downscale(image)
            # 순서 주의: 흰 배경을 먼저 투명하게 만들어야 여백 잘라내기가 제대로 먹음
            image = _convert_pixels(image)
            frames = _slice_strip(image)
            if len(frames) > 1:
                # 스트립은 칸마다 따로 여백을 자르면 방향이 바뀔 때 배 위치가 튀므로
                # 칸 크기를 그대로 유지함(원본 격자의 상대 위치가 곧 정렬 기준)
                pixmaps = [QPixmap.fromImage(f) for f in frames]
            else:
                pixmaps = [QPixmap.fromImage(_trim_transparent(frames[0]))]
            sprite = _Sprite(pixmaps)
    _sprite_cache.append(sprite)
    return sprite


def _downscale(image: QImage) -> QImage:
    """픽셀 변환이 파이썬 루프라 큰 원본을 그대로 돌리면 첫 소환 때 화면이 멈춤.
    스트립은 '칸 하나'가, 낱장은 '이미지 전체'가 기준이라 각각 다르게 줄임."""
    width, height = image.width(), image.height()
    if height > 0 and width >= height * STRIP_MIN_ASPECT:
        if height <= FRAME_MAX_PX:
            return image
        ratio = FRAME_MAX_PX / height
        return image.scaled(int(width * ratio), FRAME_MAX_PX,
                            Qt.AspectRatioMode.IgnoreAspectRatio,
                            Qt.TransformationMode.SmoothTransformation)
    if max(width, height) <= SPRITE_MAX_PX:
        return image
    return image.scaled(SPRITE_MAX_PX, SPRITE_MAX_PX,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation)
