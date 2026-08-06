"""README에 넣을 스크린샷을 찍는다 - docs/screenshot.png.

실행: python docs/make_screenshot.py (저장소 루트에서)

**오프스크린(QT_QPA_PLATFORM=offscreen)으로 찍으면 안 된다** - 한글이 전부 네모로 나온다.
실제 창을 띄워야 하므로 화면에 창이 잠깐 떴다 사라진다.

내용은 진짜 대화가 아니라 여기서 만들어 넣는다(개인 대화 기록이 새어나가면 안 되고,
화면에 무엇이 보일지도 매번 같아야 하므로). 안읽음 노란색은 깜빡이는 중이면 찍는 순간에
따라 색이 없을 수 있어서, 다 깜빡인 뒤 유지되는 상태로 고정해두고 찍는다.
"""
import os
import sys
import time

from PySide6.QtWidgets import QApplication

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

app = QApplication([])
import gui_client as g

app.setStyleSheet(g.STYLE_SHEET)
win = g.MainWindow()
page = win.chat_page
win.stack.setCurrentWidget(page)   # 크기 정책이 화면 전환 때 적용되므로 크기는 그 뒤에 정함
win.show()
win.resize(1060, 720)

page.my_id = "몽키"
for ch in ("#일반", "#개발", "#잡담"):
    page.add_channel(ch)
page.member_panel.set_members("#일반", ["몽키", "hjsong", "앨리스", "Bob", "다람쥐", "고양이", "너구리"])
page.member_panel.set_nickname("hjsong", "준성")
page.member_panel.show_channel("#일반")

now = time.time()
talk = [
    ("앨리스", "다들 주말에 뭐 했어?", False, 1400),
    ("Bob", "나는 이 채팅 프로그램 붙잡고 있었지", False, 1330),
    ("hjsong", "IRC 서버에 그대로 붙는 거라 아무 서버나 다 되더라", False, 1250),
    ("몽키", "Libera.Chat 들어가봤는데 진짜 되더라 ㅋㅋ", True, 1180),
    ("다람쥐", "그러면 다른 IRC 클라이언트 쓰는 사람이랑도 같이 대화되는 거야?", False, 1090),
    ("hjsong", "응. 아이콘이랑 닉네임은 우리끼리만 보이고, 저쪽에는 안 깨져서 나가", False, 1010),
    ("앨리스", "오 그거 어떻게 한 거야", False, 950),
    ("hjsong", "CTCP라고 IRC에 원래 있는 틀에 실어 보내. 모르는 클라이언트는 그냥 무시함", False, 880),
    ("Bob", "@몽키 너도 아이콘 좀 바꿔봐. 오른쪽 아래 프로필 변경 눌러", False, 700),
    ("몽키", "지금 바꿨는데 어때", True, 640),
    ("앨리스", "괜찮은데? 근데 창 닫으면 알림 안 오는 거 아니야?", False, 520),
    ("다람쥐", "닫아도 안 꺼져. 작업표시줄 아이콘에 남아 있어서 알림 계속 옴", False, 430),
    ("hjsong", "알림에 뭘 보여줄지도 환경설정에서 고를 수 있어. 내용 숨기기도 됨", False, 330),
    ("몽키", "회사에서 쓰기 좋겠네 ㅋㅋㅋ", True, 240),
    ("다람쥐", "채널 목록은 가운데 화살표로 접었다 폈다 하면 대화창이 넓어져", False, 120),
]
for sender, text, mine, ago in talk:
    page.append_message("#일반", sender, text, mine, now - ago)
page.append_system("#일반", "다람쥐님이 입장했습니다.")
page.channel_sidebar.set_active("#일반")
# 안읽음 노란색 - 깜빡이는 중이면 찍는 순간에 따라 색이 없을 수 있어서,
# 다 깜빡인 뒤 유지되는 상태(실제로 가장 오래 보이는 모습)로 고정한다
page.channel_sidebar.mark_unread("#개발")
page.channel_sidebar._kill_timer("#개발")
from gui.theme import UNREAD_TINT_ALPHA_IDLE
page.channel_sidebar._tint.set_alpha("#개발", UNREAD_TINT_ALPHA_IDLE)

for _ in range(30):
    app.processEvents()
    time.sleep(0.02)
win.grab().save(os.path.join(os.path.dirname(os.path.abspath(__file__)), "screenshot.png"))
print("docs/screenshot.png 갱신 완료")
