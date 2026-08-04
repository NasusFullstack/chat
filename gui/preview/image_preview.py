"""이미지 미리보기 위젯과 크기 계산.

여기 담긴 규칙 두 개는 실제 사고에서 나왔다(자세한 내용은 각 함수 주석 참고):
- 크기를 다시 계산할 땐 반드시 **원본 크기**에서 한다(그려지는 크기 기준이면 겹겹이 축소됨)
- 움짤은 QMovie.setScaledSize()를 쓰지 않는다(갱신 영역이 어긋나 화면 대부분이 안 그려짐)
"""
from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QSize, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication, QMovie, QPixmap
from PySide6.QtWidgets import QLabel, QMenu, QSizePolicy

import link_meta

# 주소만 보고 "이건 그림 파일"이라고 판단하는 규칙은 link_meta에 있다(순수 함수)
is_image_url = link_meta.is_image_url

# 이미지 미리보기 최대 크기. 원본이 크면 이 안에 들어오게 비율대로 줄여서 보여줌
IMAGE_PREVIEW_WIDTH = 320
IMAGE_PREVIEW_MAX_HEIGHT = 320

# 뉴스/게시물 카드의 썸네일은 작은 정사각형 고정. 원본이 아무리 커도 여기 맞춰 잘라냄
# (안 그러면 큰 헤더 이미지가 채팅창을 통째로 차지함)
CARD_THUMB_PX = 80


def _looks_like_gif(data: bytes) -> bool:
    return data[:6] in (b"GIF87a", b"GIF89a")


def _preview_size(width: int, height: int, max_width: int = 0) -> QSize:
    """상한 안에 들어가도록 비율을 유지해 줄인 크기.

    max_width는 지금 채팅창에서 실제로 쓸 수 있는 폭. 이걸 안 지키면 채팅창이 좁을 때
    이미지가 밖으로 삐져나가 가로 스크롤이 생기고 시간 배지까지 화면 밖으로 밀린다.

    1.0을 못 넘게 막는 이유: 작은 이미지를 억지로 키우면 뭉개지므로 원본 크기 유지."""
    limit = IMAGE_PREVIEW_WIDTH if max_width <= 0 else min(IMAGE_PREVIEW_WIDTH, max_width)
    limit = max(1, limit)
    if width <= 0 or height <= 0:
        return QSize(limit, limit)
    scale = min(limit / width, IMAGE_PREVIEW_MAX_HEIGHT / height, 1.0)
    # int()로 버리면 320이 319가 되고, 거기에 KeepAspectRatio가 한 번 더 맞추면서 318까지
    # 줄어들었음. 반올림 + 아래의 IgnoreAspectRatio 조합으로 목표 크기에 정확히 맞춤
    return QSize(max(1, round(width * scale)), max(1, round(height * scale)))


def _scaled_for_preview(pixmap: QPixmap, max_width: int = 0) -> QPixmap:
    size = _preview_size(pixmap.width(), pixmap.height(), max_width)
    if size == pixmap.size():
        return pixmap
    return pixmap.scaled(size, Qt.AspectRatioMode.IgnoreAspectRatio,
                         Qt.TransformationMode.SmoothTransformation)


def crop_to_square(pixmap: QPixmap, side: int) -> QPixmap:
    """가운데를 정사각형으로 잘라 썸네일 크기에 맞춤.

    그냥 축소만 하면 가로로 긴 뉴스 헤더 이미지가 납작해져 알아보기 어렵고, 카드 높이도
    이미지마다 들쭉날쭉해짐. 가운데를 잘라내면 카드 높이가 항상 일정함.
    """
    if pixmap.isNull():
        return pixmap
    edge = min(pixmap.width(), pixmap.height())
    x = (pixmap.width() - edge) // 2
    y = (pixmap.height() - edge) // 2
    return pixmap.copy(x, y, edge, edge).scaled(
        side, side, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)


class ImagePreview(QLabel):
    """이미지 직링크 미리보기. 움직이는 GIF면 움직이게 재생함."""

    def __init__(self, url: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("linkImagePreview")
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._url = url
        self._movie = None
        self._buffer = None
        # 원본을 들고 있어야 창 크기가 바뀔 때 다시 줄일 수 있음(한 번 줄인 걸 또 줄이면
        # 화질이 계속 나빠지고, 창을 다시 넓혀도 작은 채로 남음)
        self._source = None
        # 움짤은 QMovie가 원본을 안 돌려주므로(scaledSize를 주면 그 크기로만 답함)
        # 처음 읽은 원본 프레임 크기를 따로 기억해둠
        self._source_size = None
        self._max_width = 0

    def set_max_width(self, width: int):
        """채팅창에서 쓸 수 있는 폭이 바뀌었을 때 그 안에 들어오게 다시 맞춤.

        반드시 '원본 크기'에서 다시 계산할 것. 지금 그려지는 크기(currentPixmap)를
        기준으로 줄이면 창 크기를 만질 때마다 겹겹이 축소돼서 그림이 계속 작아진다
        (실제로 "가로를 줄이면 세로가 점점 줄어든다"는 증상으로 나타났음).

        그리고 크기를 바꿨으면 라벨 자신의 크기도 같이 맞춰야 한다. 안 맞추면 라벨은
        예전 크기 그대로라 그림이 잘리거나(라벨이 작을 때) 아래가 비어 보인다(클 때).
        """
        if width <= 0 or width == self._max_width:
            return
        self._max_width = width
        self._apply_size()

    def _apply_size(self):
        """지금 폭 제한에 맞춰 그림 크기와 라벨 크기를 함께 맞춤."""
        if self._movie is not None and self._source_size is not None:
            size = _preview_size(self._source_size.width(), self._source_size.height(),
                                 self._max_width)
            # 움짤은 QMovie.setScaledSize()를 쓰면 안 된다. 애니메이션 GIF는 대부분의
            # 프레임이 '바뀐 부분'만 담고 있고, Qt는 다시 그릴 영역을 '축소 전' 좌표로
            # 알려준다. 그래서 크기를 조절해두면 갱신 영역이 어긋나 화면 대부분이 예전
            # 그림 그대로 남는다("세로가 80% 날아간다"는 증상).
            # 대신 움짤은 원래 크기로 재생시키고, 라벨이 그릴 때 통째로 줄이게 한다.
            self.setScaledContents(True)
            self.setFixedSize(size)
        elif self._source is not None:
            pixmap = _scaled_for_preview(self._source, self._max_width)
            self.setPixmap(pixmap)
            self.setFixedSize(pixmap.size())
        else:
            return
        self.updateGeometry()

    def set_image_data(self, data: bytes) -> bool:
        """받은 바이트로 이미지를 세팅. 못 읽으면 False(호출자가 미리보기를 지움)."""
        if not data:
            return False
        if _looks_like_gif(data):
            return self._set_animated(data)
        pixmap = QPixmap()
        if not pixmap.loadFromData(data) or pixmap.isNull():
            return False
        self._source = pixmap
        self._apply_size()
        return True

    def _set_animated(self, data: bytes) -> bool:
        # QMovie는 파일이나 QIODevice에서 읽으므로 메모리 버퍼를 물려줌.
        # 버퍼를 self에 붙들어두지 않으면 GC돼서 재생 중 끊김
        self._buffer = QBuffer(self)
        self._buffer.setData(QByteArray(data))
        if not self._buffer.open(QIODevice.OpenModeFlag.ReadOnly):
            return False
        movie = QMovie(self)
        movie.setDevice(self._buffer)
        if not movie.isValid():
            return False
        movie.jumpToFrame(0)
        size = movie.currentPixmap().size()
        if size.width() <= 0:
            return False
        # 원본 크기를 기억해둠 - 창 크기가 바뀔 때 항상 여기서 다시 계산해야 함
        # (그려지는 크기를 기준으로 삼으면 만질 때마다 겹겹이 축소됨)
        self._source_size = size
        self._movie = movie
        self.setMovie(movie)
        self._apply_size()
        movie.start()
        return True

    @property
    def url(self) -> str:
        return self._url

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._url:
            QDesktopServices.openUrl(QUrl(self._url))
        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event):
        """우클릭 - 남이 올린 그림도 내 이모티콘 보관함에 넣을 수 있게.

        지연 import인 이유는 파일 맨 위 docstring 참고(테스트가 themed_get_text를
        바꿔치기할 수 있어야 하므로 반드시 모듈 속성으로 조회해야 함).
        """
        import gui_client
        import emoji_store

        if not self._url:
            return
        menu = QMenu(self)
        already = emoji_store.has_emoji(self._url)
        save_action = menu.addAction("이미 보관함에 있음" if already else "내 이모티콘으로 저장")
        save_action.setEnabled(not already)
        copy_action = menu.addAction("이미지 주소 복사")
        chosen = menu.exec(event.globalPos())
        if chosen is copy_action:
            QGuiApplication.clipboard().setText(self._url)
            return
        if chosen is not save_action:
            return
        name, ok = gui_client.themed_get_text(
            self, "이모티콘 저장", "이 이모티콘의 이름을 입력하세요 (나중에 검색할 때 씀)")
        if not ok:
            return
        saved, text = emoji_store.add_emoji(self._url, name)
        if not saved:
            gui_client.themed_warning(self, "이모티콘 저장", text)
