import os as _os
import sys as _sys

_HERE = _os.path.dirname(_os.path.abspath(__file__))
_REPO = _os.path.dirname(_HERE)
import os
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, _REPO)

from PySide6.QtWidgets import QApplication, QMessageBox, QLabel
from PySide6.QtCore import QTimer
import gui_client as g

app = QApplication(sys.argv)
app.setStyleSheet(g.STYLE_SHEET)

events = {"add": [], "leave": [], "send": [], "avatar": []}
chat_page = g.ChatPage(
    on_send=lambda ch, text: events["send"].append((ch, text)),
    on_add_channel=lambda: events["add"].append(True),
    on_leave_channel=lambda ch: events["leave"].append(ch),
    on_set_avatar=lambda: events["avatar"].append(True),
)
chat_page.my_id = "me"
chat_page.show()
app.processEvents()

checks = []

# ---- 탭 생성/개수/활성 채널 ----
chat_page.add_channel("#a")
chat_page.add_channel("#b")
# 채널 추가는 왼쪽 채널 목록의 '+'로 옮겼고 탭바 자체는 숨겼다. 그래서 탭은
# 채널 수만큼만 있고 '+' 탭은 없다(예전에는 탭 하나를 '+'로 썼다)
checks.append(("채널 수만큼 대화 화면이 생김", chat_page.tabs.count() == 2))
checks.append(("채널 목록에도 두 줄이 생김", chat_page.channel_sidebar.list.count() == 2))
checks.append(("활성 채널이 마지막에 추가한 #b", chat_page.active_channel() == "#b"))
checks.append(("탭 라벨이 채널명과 일치", chat_page.tabs.tabText(0) == "#a" and chat_page.tabs.tabText(1) == "#b"))

# ---- 탭 닫기 요청은 콜백만 호출하고 실제로 안 지움 (서버 응답 대기 패턴) ----
orig_question = g.themed_question
g.themed_question = lambda *a, **k: True
chat_page._request_close_channel("#a")
g.themed_question = orig_question
checks.append(("탭 닫기 확인 시 on_leave_channel 콜백만 호출됨", events["leave"] == ["#a"]))
checks.append(("콜백만 오고 아직 안 지워짐(서버 응답 대기)", chat_page.tabs.count() == 2))

chat_page.remove_channel("#a")
checks.append(("remove_channel 직접 호출 시 실제로 제거됨",
               chat_page.tabs.count() == 1 and chat_page.channel_sidebar.list.count() == 1))
checks.append(("남은 활성 채널은 #b", chat_page.active_channel() == "#b"))

# ---- 안읽음 표시 ----
chat_page.add_channel("#c", activate=False)  # #b가 계속 활성 상태
checks.append(("새 채널 추가해도 activate=False면 활성 채널 안 바뀜", chat_page.active_channel() == "#b"))

chat_page.append_message("#c", "other", "hello", False, 0)
# 안읽음은 탭의 점 아이콘이 아니라 **왼쪽 채널 줄을 옅은 노랑으로 덧칠**하는 방식이다
# (노란 점은 요청으로 없앴고, 글자색은 QSS가 항상 이겨서 코드로 못 바꾼다)
sidebar = chat_page.channel_sidebar
checks.append(("비활성 채널에 메시지 오면 안읽음 깜빡임이 시작됨", sidebar.is_blinking("#c")))
checks.append(("그 채널 줄이 실제로 노랗게 칠해짐", sidebar.unread_alpha("#c") > 0))

chat_page.append_message("#b", "other", "hi active", False, 0)
checks.append(("보고 있는 채널(#b)에는 안읽음 표시가 안 생김",
               not sidebar.is_blinking("#b") and sidebar.unread_alpha("#b") == 0))

chat_page.set_active_channel("#c")
app.processEvents()
checks.append(("#c로 전환하면 깜빡임이 정리됨", not sidebar.is_blinking("#c")))
checks.append(("전환 후 노란색도 사라짐", sidebar.unread_alpha("#c") == 0))
chat_page.append_message("#c", "alice", "badge test message", False, 1700000000.0)
app.processEvents()
view = chat_page._log_views["#c"]
badges = view.findChildren(QLabel, "timestampBadge")
checks.append(("timestampBadge 라벨이 존재함", len(badges) >= 1))
if badges:
    badge = badges[-1]
    checks.append((f"배지 높이가 {g.TIMESTAMP_BADGE_HEIGHT_PX}px 고정", badge.height() == g.TIMESTAMP_BADGE_HEIGHT_PX))
    checks.append((f"배지 폰트 크기가 {g.TIMESTAMP_BADGE_FONT_PX}px 고정", badge.font().pixelSize() == g.TIMESTAMP_BADGE_FONT_PX))

# 기본 폰트를 20px로 바꾼 스타일로 다시 적용 후, 새 메시지의 배지가 여전히 7px인지 확인
bigger_style = g.STYLE_SHEET.replace("font-size: 14px;", "font-size: 20px;")
app.setStyleSheet(bigger_style)
app.processEvents()
chat_page.append_message("#c", "bob", "after font change", False, 1700000000.0)
app.processEvents()
badges_after = view.findChildren(QLabel, "timestampBadge")
badge2 = badges_after[-1]
checks.append(("앱 기본 폰트를 20px로 키워도 배지는 여전히 7px 고정", badge2.font().pixelSize() == g.TIMESTAMP_BADGE_FONT_PX))
checks.append(("배지 높이도 여전히 14px 고정", badge2.height() == g.TIMESTAMP_BADGE_HEIGHT_PX))

# ---- IRC 모드도 이제 CTCP로 아이콘을 지원하므로 버튼이 계속 보여야 함 ----
chat_page.set_protocol_mode("irc")
checks.append(("IRC 모드에서도 아이콘 버튼 계속 보임(CTCP로 지원)", chat_page.avatar_btn.isVisible() is True))
chat_page.set_protocol_mode("custom")
checks.append(("커스텀 모드에서도 아이콘 버튼 보임", chat_page.avatar_btn.isVisible() is True))

print("\n=== 검증 결과 ===")
all_ok = True
for name, ok in checks:
    print(f"[{'OK' if ok else 'FAIL'}] {name}")
    all_ok = all_ok and ok
print("\n전체 통과:", all_ok)
