"""사이드바 아래 만든이 표시 + 채널이 많을 때 화살표로 밀어 보기."""
import os as _os
import sys as _sys

_HERE = _os.path.dirname(_os.path.abspath(__file__))
_REPO = _os.path.dirname(_HERE)

_os.environ["QT_QPA_PLATFORM"] = "offscreen"
_sys.path.insert(0, _REPO)
_sys.path.insert(0, _HERE)

from PySide6.QtWidgets import QApplication, QLabel

app = QApplication.instance() or QApplication([])
import gui_client as g
from gui.theme import COPYRIGHT_YEAR, DEVELOPER_EMAIL
from version import APP_VERSION

app.setStyleSheet(g.STYLE_SHEET)
checks = []

page = g.ChatPage(on_send=lambda c, t: None, on_add_channel=lambda: None,
                  on_leave_channel=lambda c: None, on_set_avatar=lambda: None)
page.resize(900, 620)
page.show()
page.my_id = "Mong"
for _ in range(5):
    app.processEvents()

footer = page._sidebar_footer
texts = " ".join(label.text() for label in footer.findChildren(QLabel))
checks.append(("프로그램 이름이 있음", "춥채팅" in texts))
checks.append((f"버전이 있음(v{APP_VERSION})", APP_VERSION in texts))
checks.append(("만든이 메일이 있음", DEVELOPER_EMAIL in texts))
checks.append((f"카피라이트가 있음({COPYRIGHT_YEAR})", str(COPYRIGHT_YEAR) in texts and "©" in texts))
logos = [lb for lb in footer.findChildren(QLabel) if lb.objectName() == "footerLogo"]
checks.append(("로고가 있음", bool(logos) and logos[0].pixmap() is not None
               and not logos[0].pixmap().isNull()))
checks.append(("사이드바 안에 들어 있음",
               footer.parentWidget() is page._channel_sidebar))

# 채널이 적을 때는 화살표가 없어야 함
for i in range(2):
    page.add_channel(f"#ch{i}")
for _ in range(6):
    app.processEvents()
checks.append(("채널이 적으면 화살표가 안 보임",
               not page.channel_scroll_down.isVisible()
               and not page.channel_scroll_up.isVisible()))

# 채널을 잔뜩 넣으면 목록이 잘리고 아래 화살표가 생겨야 함
for i in range(2, 30):
    page.add_channel(f"#ch{i}")
for _ in range(8):
    app.processEvents()
page._sync_channel_list_height()
for _ in range(4):
    app.processEvents()

bar = page.channel_list.verticalScrollBar()
checks.append((f"목록이 잘려 스크롤 여지가 생김(최대 {bar.maximum()})", bar.maximum() > 0))

# 채널을 추가하면 그 채널이 선택되면서 목록이 맨 아래로 내려가 있음 - 위로 올려두고 확인
checks.append(("방금 들어간 채널이 보이도록 아래로 내려가 있음", bar.value() == bar.maximum()))
checks.append(("맨 아래에서는 위 화살표가 보임", page.channel_scroll_up.isVisible()))

bar.setValue(0)
page._sync_channel_scroll_buttons()
for _ in range(4):
    app.processEvents()
checks.append(("맨 위에서는 아래 화살표가 나타남", page.channel_scroll_down.isVisible()))
checks.append(("맨 위에서는 위 화살표가 없음", not page.channel_scroll_up.isVisible()))

before = bar.value()
page._scroll_channels(1)
for _ in range(4):
    app.processEvents()
checks.append((f"아래 화살표로 밀림({before} -> {bar.value()})", bar.value() > before))
checks.append(("밀고 나면 위 화살표가 생김", page.channel_scroll_up.isVisible()))

bar.setValue(bar.maximum())
page._sync_channel_scroll_buttons()
checks.append(("맨 아래에서는 아래 화살표가 사라짐", not page.channel_scroll_down.isVisible()))

page._scroll_channels(-1)
for _ in range(4):
    app.processEvents()
checks.append(("위 화살표로 되돌아감", bar.value() < bar.maximum()))

# 목록이 만든이 표시를 밀어내면 안 됨
checks.append(("채널이 많아도 만든이 표시가 화면 안에 있음",
               footer.isVisible() and footer.y() + footer.height() <= page.height() + 2))

# 항목이 반쯤 걸쳐 보이면 안 됨(칸 단위로 잘라야 함)
row_rect = page.channel_list.visualItemRect(page.channel_list.item(0))
step = row_rect.height() + 6
checks.append((f"목록 높이가 칸 단위({step}px)로 떨어짐",
               page.channel_list.height() % step == 0))

# 창을 높이면 다 들어가서 화살표가 사라지고, 낮추면 다시 생겨야 함
page.resize(900, 1400)
for _ in range(8):
    app.processEvents()
tall_max = page.channel_list.verticalScrollBar().maximum()
tall_arrow = page.channel_scroll_down.isVisible() or page.channel_scroll_up.isVisible()

page.resize(900, 500)
for _ in range(8):
    app.processEvents()
page.channel_list.verticalScrollBar().setValue(0)
page._sync_channel_scroll_buttons()
short_max = page.channel_list.verticalScrollBar().maximum()
checks.append((f"창을 높이면 스크롤 여지가 줄어듦(1400에서 {tall_max} / 500에서 {short_max})",
               tall_max < short_max))
checks.append(("창을 낮추면 아래 화살표가 다시 생김", page.channel_scroll_down.isVisible()))
if tall_max == 0:
    checks.append(("창이 충분히 크면 화살표가 사라짐", not tall_arrow))

print("=== 검증 결과 (사이드바 하단/채널 스크롤) ===")
all_ok = True
for name, ok in checks:
    print(f"[{'OK' if ok else 'FAIL'}] {name}")
    all_ok = all_ok and ok
print("\n전체 통과:", all_ok)
_sys.exit(0 if all_ok else 1)
