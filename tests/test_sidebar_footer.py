"""만든이 표시(참여자 열 아래) + 채널 목록 접기/펴기 + 화살표로 밀어 보기."""
import os as _os
import sys as _sys

_HERE = _os.path.dirname(_os.path.abspath(__file__))
_REPO = _os.path.dirname(_HERE)

_os.environ["QT_QPA_PLATFORM"] = "offscreen"
_sys.path.insert(0, _REPO)
_sys.path.insert(0, _HERE)

from PySide6.QtCore import Qt
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

footer = page.footer
texts = " ".join(label.text() for label in footer.findChildren(QLabel))
checks.append(("프로그램 이름이 있음", "춥채팅" in texts))
checks.append((f"버전이 있음(v{APP_VERSION})", APP_VERSION in texts))
checks.append(("만든이 메일이 있음", DEVELOPER_EMAIL in texts))
checks.append((f"카피라이트가 있음({COPYRIGHT_YEAR})", str(COPYRIGHT_YEAR) in texts and "©" in texts))
logos = [lb for lb in footer.findChildren(QLabel) if lb.objectName() == "footerLogo"]
checks.append(("로고가 있음", bool(logos) and logos[0].pixmap() is not None
               and not logos[0].pixmap().isNull()))
# 채널 사이드바는 접을 수 있으므로 만든이 표시는 항상 보이는 참여자 열로 옮겼다.
# 사이드바에 남아 있으면 접었을 때 통째로 사라진다
checks.append(("만든이 표시가 채널 사이드바에 있지 않음",
               footer.parentWidget() is not page.channel_sidebar))
checks.append(("참여자 열(프로필 버튼과 같은 열) 안에 있음",
               footer.parentWidget() is page.avatar_btn.parentWidget()))
checks.append(("프로필 변경 버튼이 참여자 목록 바로 아래에 있음",
               page.avatar_btn.y() >= page.member_panel.y() + page.member_panel.height()))
checks.append(("만든이 표시는 프로필 버튼보다 아래에 있음",
               footer.y() >= page.avatar_btn.y() + page.avatar_btn.height()))

# --- 참여자 목록: 여섯 줄만 보이고 나머지는 스크롤 ---
from gui.theme import MEMBER_ROW_HEIGHT, MEMBER_VISIBLE_ROWS   # noqa: E402

panel = page.member_panel
panel.set_members("#a", [f"user{i}" for i in range(4)])
panel.show_channel("#a")
for _ in range(4):
    app.processEvents()
checks.append((f"인원수가 머리글에 나옴({panel.header.text()})", "4명" in panel.header.text()))
few_max = panel.list.verticalScrollBar().maximum()
checks.append(("네 명일 때는 스크롤이 필요 없음", few_max == 0))

panel.set_members("#a", [f"user{i}" for i in range(9)])
for _ in range(4):
    app.processEvents()
checks.append((f"인원수가 갱신됨({panel.header.text()})", "9명" in panel.header.text()))
checks.append((f"목록 높이가 {MEMBER_VISIBLE_ROWS}줄로 고정됨({panel.list.height()}px)",
               panel.list.height() == MEMBER_ROW_HEIGHT * MEMBER_VISIBLE_ROWS + 2))
checks.append(("아홉 명이면 스크롤로 내려서 봄",
               panel.list.verticalScrollBar().maximum() > 0))
checks.append(("스크롤바가 얇음(6px)", panel.list.verticalScrollBar().width() == 6))
checks.append(("사람이 늘어도 만든이 표시가 밀려나지 않음",
               footer.y() + footer.height() <= page.height() + 2))

# --- 채널 목록 접기/펴기 ---
sidebar = page.channel_sidebar
open_width = sidebar.width()
from PySide6.QtCore import QPoint       # noqa: E402
from PySide6.QtTest import QTest        # noqa: E402

# 실제로 손잡이를 눌러서 접힌다(핸들러 직접 호출이 아니라 진짜 클릭 경로로)
QTest.mouseClick(page.sidebar_handle, Qt.MouseButton.LeftButton,
                 pos=QPoint(page.sidebar_handle.width() // 2,
                            page.sidebar_handle.height() // 2))
for _ in range(4):
    app.processEvents()
checks.append((f"접으면 폭을 통째로 내줌({open_width} -> {sidebar.width()})",
               sidebar.width() == 0))
checks.append(("접으면 채널 목록이 숨음", not sidebar.list.isVisible()))
checks.append(("접어도 손잡이는 남아 있음(다시 펼 수 있어야 함)",
               page.sidebar_handle.isVisible()))
checks.append(("손잡이 화살표가 '펴는 쪽'을 가리킴", page.sidebar_handle._collapsed is True))
checks.append(("접어도 만든이 표시는 그대로 보임", footer.isVisible()))
sidebar.toggle_collapsed()
for _ in range(4):
    app.processEvents()
checks.append((f"다시 펴면 원래 폭으로 돌아옴({sidebar.width()})", sidebar.width() == open_width))
checks.append(("다시 펴면 채널 목록이 보임", sidebar.list.isVisible()))
checks.append(("손잡이 화살표가 '접는 쪽'으로 돌아옴", page.sidebar_handle._collapsed is False))
handle_x = page.sidebar_handle.mapTo(page, QPoint(0, 0)).x()   # 부모 기준 x는 의미가 없음
checks.append((f"손잡이는 사이드바와 대화창 사이에 있음(사이드바 끝 {sidebar.x() + sidebar.width()} <= 손잡이 {handle_x})",
               sidebar.x() + sidebar.width() <= handle_x))
checks.append(("손잡이가 창 세로 가운데쯤에 있음",
               abs((page.sidebar_handle.mapTo(page, QPoint(0, 0)).y()
                    + page.sidebar_handle.height() / 2) - page.height() / 2) <= 2))

# 채널이 적을 때는 화살표가 없어야 함
for i in range(2):
    page.add_channel(f"#ch{i}")
for _ in range(6):
    app.processEvents()
checks.append(("채널이 적으면 화살표가 안 보임",
               not page.channel_sidebar.scroll_down.isVisible()
               and not page.channel_sidebar.scroll_up.isVisible()))

# 채널을 잔뜩 넣으면 목록이 잘리고 아래 화살표가 생겨야 함
for i in range(2, 30):
    page.add_channel(f"#ch{i}")
for _ in range(8):
    app.processEvents()
page.channel_sidebar.sync_height()
for _ in range(4):
    app.processEvents()

bar = page.channel_sidebar.list.verticalScrollBar()
checks.append((f"목록이 잘려 스크롤 여지가 생김(최대 {bar.maximum()})", bar.maximum() > 0))

# 채널을 추가하면 그 채널이 선택되면서 목록이 맨 아래로 내려가 있음 - 위로 올려두고 확인
checks.append(("방금 들어간 채널이 보이도록 아래로 내려가 있음", bar.value() == bar.maximum()))
checks.append(("맨 아래에서는 위 화살표가 보임", page.channel_sidebar.scroll_up.isVisible()))

bar.setValue(0)
page.channel_sidebar._sync_arrows()
for _ in range(4):
    app.processEvents()
checks.append(("맨 위에서는 아래 화살표가 나타남", page.channel_sidebar.scroll_down.isVisible()))
checks.append(("맨 위에서는 위 화살표가 없음", not page.channel_sidebar.scroll_up.isVisible()))

before = bar.value()
page.channel_sidebar.scroll_by(1)
for _ in range(4):
    app.processEvents()
checks.append((f"아래 화살표로 밀림({before} -> {bar.value()})", bar.value() > before))
checks.append(("밀고 나면 위 화살표가 생김", page.channel_sidebar.scroll_up.isVisible()))

bar.setValue(bar.maximum())
page.channel_sidebar._sync_arrows()
checks.append(("맨 아래에서는 아래 화살표가 사라짐", not page.channel_sidebar.scroll_down.isVisible()))

page.channel_sidebar.scroll_by(-1)
for _ in range(4):
    app.processEvents()
checks.append(("위 화살표로 되돌아감", bar.value() < bar.maximum()))

# 채널이 아무리 많아도 만든이 표시는 다른 열에 있으므로 밀려나지 않음
checks.append(("채널이 많아도 만든이 표시가 화면 안에 있음",
               footer.isVisible() and footer.y() + footer.height() <= page.height() + 2))

# 접힘 상태를 기억해야 함(다음에 켤 때 접힌 채로 열림)
import app_prefs   # noqa: E402

sidebar.set_collapsed(True)
for _ in range(3):
    app.processEvents()
checks.append(("접으면 설정에 남음", app_prefs.get("channel_sidebar_collapsed") is True))
sidebar.set_collapsed(False)
for _ in range(3):
    app.processEvents()
checks.append(("펴면 설정도 돌아옴", app_prefs.get("channel_sidebar_collapsed") is False))

# 항목이 반쯤 걸쳐 보이면 안 됨(칸 단위로 잘라야 함).
# 칸 높이는 실측한 줄 높이 그대로 - QSS의 margin-bottom은 줄 안쪽에 그려지므로 더하면 안 됨
row_rect = page.channel_sidebar.list.visualItemRect(page.channel_sidebar.list.item(0))
step = row_rect.height()
checks.append((f"목록 높이가 칸 단위({step}px)로 떨어짐",
               page.channel_sidebar.list.height() % step == 0))

# 창을 높이면 다 들어가서 화살표가 사라지고, 낮추면 다시 생겨야 함
page.resize(900, 1400)
for _ in range(8):
    app.processEvents()
tall_max = page.channel_sidebar.list.verticalScrollBar().maximum()
tall_arrow = page.channel_sidebar.scroll_down.isVisible() or page.channel_sidebar.scroll_up.isVisible()

page.resize(900, 500)
for _ in range(8):
    app.processEvents()
page.channel_sidebar.list.verticalScrollBar().setValue(0)
page.channel_sidebar._sync_arrows()
short_max = page.channel_sidebar.list.verticalScrollBar().maximum()
checks.append((f"창을 높이면 스크롤 여지가 줄어듦(1400에서 {tall_max} / 500에서 {short_max})",
               tall_max < short_max))
checks.append(("창을 낮추면 아래 화살표가 다시 생김", page.channel_sidebar.scroll_down.isVisible()))
if tall_max == 0:
    checks.append(("창이 충분히 크면 화살표가 사라짐", not tall_arrow))

print("=== 검증 결과 (만든이 표시/참여자 목록/채널 접기) ===")
all_ok = True
for name, ok in checks:
    print(f"[{'OK' if ok else 'FAIL'}] {name}")
    all_ok = all_ok and ok
print("\n전체 통과:", all_ok)
_sys.exit(0 if all_ok else 1)
