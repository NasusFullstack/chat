import os as _os
import sys as _sys

_HERE = _os.path.dirname(_os.path.abspath(__file__))
_REPO = _os.path.dirname(_HERE)
import os
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, _REPO)

from PySide6.QtWidgets import QApplication, QLabel, QListWidgetItem
import gui_client as g

app = QApplication(sys.argv)
app.setStyleSheet(g.STYLE_SHEET)

checks = []

# ---- 버튼 라벨이 "프로필 변경"으로 바뀜 ----
chat_page = g.ChatPage(
    on_send=lambda ch, text: None,
    on_add_channel=lambda: None,
    on_leave_channel=lambda ch: None,
    on_set_avatar=lambda: None,
)
chat_page.my_id = "me"
chat_page.show()
app.processEvents()
checks.append(("아바타 버튼 라벨이 '프로필 변경'", chat_page.avatar_btn.text() == "프로필 변경"))

# ---- ProfileDialog: 닉네임 입력 필드 + 초기값 + 저장 시 result_nickname ----
dlg = g.ProfileDialog(initial_base64=None, initial_nickname="기존닉", is_irc=False)
checks.append(("ProfileDialog에 닉네임 입력란이 있고 초기값 반영", dlg._nickname_input.text() == "기존닉"))
dlg._nickname_input.setText("새닉네임")
dlg._on_save()
checks.append(("저장 시 result_nickname에 새 값 반영", dlg.result_nickname == "새닉네임"))
checks.append(("저장 시 result_base64도 함께 생성됨(빈 그림이라도 문자열)", isinstance(dlg.result_base64, str)))

# IRC 모드 힌트 문구가 뜨는지 (플레이스홀더 다르게)
dlg_irc = g.ProfileDialog(initial_base64=None, initial_nickname="ircnick", is_irc=True)
checks.append(("IRC 모드에서는 플레이스홀더가 IRC용 문구", "IRC" in dlg_irc._nickname_input.placeholderText()))

# ---- chat_page.set_nickname: 참여자 목록에 닉네임이 표시되고 툴팁으로 원래 ID 확인 가능 ----
chat_page.add_channel("#p")
chat_page.update_userlist("#p", ["alice", "bob"])
app.processEvents()
chat_page.set_nickname("alice", "앨리스별명")
app.processEvents()

items_text = [chat_page.member_panel.list.item(i).text() for i in range(chat_page.member_panel.list.count())]
checks.append(("닉네임 설정한 사용자는 참여자 목록에 닉네임으로 표시됨", "앨리스별명" in items_text))
checks.append(("닉네임 없는 사용자는 여전히 원래 아이디로 표시됨", "bob" in items_text))

alice_item = next(chat_page.member_panel.list.item(i) for i in range(chat_page.member_panel.list.count())
                   if chat_page.member_panel.list.item(i).text() == "앨리스별명")
checks.append(("닉네임 표시 항목의 툴팁에 원래 아이디가 남아있음", alice_item.toolTip() == "alice"))

# ---- 채팅 메시지도 닉네임으로 표시됨 ----
chat_page.append_message("#p", "alice", "안녕하세요", False, 1700000000.0)
app.processEvents()
view = chat_page._log_views["#p"]
# 메시지 본문은 텍스트 엔진 위젯이 그린다(시스템 안내만 라벨)
from gui.components.message_text import MessageText  # noqa: E402

all_text = "\n".join([l.text() for l in view.findChildren(QLabel)]
                     + [b.text() for b in view.findChildren(MessageText)])
checks.append(("채팅 메시지 발신자도 닉네임으로 표시됨", "앨리스별명" in all_text))
checks.append(("원래 아이디(alice)는 발신자 표시에 노출되지 않음", "<b>alice</b>" not in all_text))

# ---- 닉네임 초기화(빈 문자열) 시 다시 원래 아이디로 표시 ----
chat_page.set_nickname("alice", "")
app.processEvents()
items_text2 = [chat_page.member_panel.list.item(i).text() for i in range(chat_page.member_panel.list.count())]
checks.append(("닉네임 초기화하면 다시 원래 아이디로 표시", "alice" in items_text2 and "앨리스별명" not in items_text2))

print("\n=== 검증 결과 (프로필/닉네임 GUI) ===")
all_ok = True
for name, ok in checks:
    print(f"[{'OK' if ok else 'FAIL'}] {name}")
    all_ok = all_ok and ok
print("전체 통과:", all_ok)
