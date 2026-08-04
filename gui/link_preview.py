"""링크 미리보기 - **전부 클라이언트에서 처리한다**(서버는 관여하지 않음).

내용은 역할별로 gui/preview/ 아래로 나뉘어 있다:
- fetcher.py       주소 하나를 받아오는 일(크기 제한/타임아웃/사설망 차단)
- image_preview.py 이미지 위젯과 크기 계산(움짤 처리 규칙이 여기 모임)
- link_card.py     뉴스/게시물 카드
- area.py          한 메시지에 딸린 미리보기들을 담는 칸

새 코드는 gui.preview.* 에서 직접 가져다 쓸 것. 이 파일은 기존 import를 안 깨뜨리려고
남겨둔 재수출이다.
"""
from gui.preview.area import LinkPreviewArea
from gui.preview.fetcher import (DOWNLOAD_LIMIT_BYTES, HTML_LIMIT_BYTES,
                                 REQUEST_TIMEOUT_MS, USER_AGENT, ImageFetcher)
from gui.preview.image_preview import (CARD_THUMB_PX, IMAGE_PREVIEW_MAX_HEIGHT,
                                       IMAGE_PREVIEW_WIDTH, ImagePreview, crop_to_square,
                                       is_image_url)
from gui.preview.link_card import CARD_MAX_WIDTH, LinkCard

__all__ = ["ImageFetcher", "ImagePreview", "LinkCard", "LinkPreviewArea", "crop_to_square",
           "is_image_url", "IMAGE_PREVIEW_WIDTH", "IMAGE_PREVIEW_MAX_HEIGHT",
           "CARD_THUMB_PX", "CARD_MAX_WIDTH", "DOWNLOAD_LIMIT_BYTES", "HTML_LIMIT_BYTES",
           "REQUEST_TIMEOUT_MS", "USER_AGENT"]
