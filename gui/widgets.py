"""예전 경로 유지용 재수출.

내용은 역할별로 나뉘어 gui/components/ 아래로 옮겼다:
- message_item.py : 메시지 한 줄(MessageWidget)
- message_log.py  : 그 줄들을 쌓는 목록(ChannelLogView)

새 코드는 gui.components.* 에서 직접 가져다 쓸 것. 이 파일은 기존 import를 안 깨뜨리려고
남겨둔 것뿐이다.
"""
from gui.components.message_item import MessageWidget, _build_system_label, _message_html
from gui.components.message_log import ChannelLogView, _ChatLogContent

__all__ = ["MessageWidget", "ChannelLogView", "_build_system_label", "_message_html",
           "_ChatLogContent"]
