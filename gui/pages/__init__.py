"""화면(페이지)들.

한 파일에 세 화면이 다 들어 있어서 하나를 고치려면 다른 둘까지 스크롤해야 했다.
지금은 화면당 한 파일이고, 이 __init__이 예전처럼 `from gui.pages import ChatPage`로
가져다 쓸 수 있게 모아준다.
"""
from gui.pages.channel_page import ChannelPage
from gui.pages.chat_page import MEMBER_HEADER_HEIGHT, ChatPage
from gui.pages.login_page import LoginPage

__all__ = ["LoginPage", "ChannelPage", "ChatPage", "MEMBER_HEADER_HEIGHT"]
