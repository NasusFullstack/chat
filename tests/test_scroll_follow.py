"""위쪽 지난 대화를 보고 있을 때 새 메시지가 화면을 끌어내리지 않아야 한다.

단, 맨 아래(또는 그 근처)를 보고 있었다면 새 메시지를 계속 따라가야 한다.
"""
import os as _os
import sys as _sys

_HERE = _os.path.dirname(_os.path.abspath(__file__))
_REPO = _os.path.dirname(_HERE)

_os.environ["QT_QPA_PLATFORM"] = "offscreen"
_sys.path.insert(0, _REPO)
_sys.path.insert(0, _HERE)

from PySide6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])
import gui_client as g
from fixtures import sample_history

app.setStyleSheet(g.STYLE_SHEET)
checks = []

page = g.ChatPage(on_send=lambda c, t: None, on_add_channel=lambda: None,
                  on_leave_channel=lambda c: None, on_set_avatar=lambda: None)
page.resize(900, 620)
page.show()
page.my_id = "Mong"
page.add_channel("#a")
page.set_active_channel("#a")
for _ in range(6):
    app.processEvents()
page.load_history("#a", sample_history(40))
for _ in range(8):
    app.processEvents()

view = page._log_views["#a"]
bar = view.verticalScrollBar()


def settle():
    for _ in range(8):
        app.processEvents()


settle()
checks.append((f"기록을 불러오면 맨 아래를 보고 있음({bar.value()}/{bar.maximum()})",
               bar.value() >= bar.maximum() - 40))

# 맨 아래에 있을 때 새 메시지 -> 따라 내려가야 함
page.append_message("#a", "hjsong", "맨 아래에서 받은 메시지", False, 1.0)
settle()
checks.append(("맨 아래를 보고 있으면 새 메시지를 따라간다",
               bar.value() >= bar.maximum() - 40))

# 위쪽으로 올려서 지난 대화를 보는 중
bar.setValue(int(bar.maximum() * 0.3))
settle()
reading_at = bar.value()
checks.append(("위로 올려서 지난 대화를 보는 중", bar.value() < bar.maximum() - 40))

page.append_message("#a", "hjsong", "지난 대화 보는 중에 온 메시지", False, 2.0)
settle()
checks.append((f"위쪽을 보는 중엔 끌려 내려가지 않는다({reading_at} -> {bar.value()})",
               bar.value() == reading_at))
checks.append(("그래도 메시지는 목록에 쌓인다",
               any("지난 대화 보는 중" in m._text_label.text() for m in view._messages)))

# 다시 맨 아래로 내리면 따라가기가 켜져야 함
view.scroll_to_bottom()
settle()
checks.append(("맨 아래로 내려옴", bar.value() >= bar.maximum() - 40))
page.append_message("#a", "hjsong", "다시 따라가는지 확인", False, 3.0)
settle()
checks.append(("따라가기가 켜지면 새 메시지로 내려간다",
               bar.value() >= bar.maximum() - 40))

# 살짝 위(한 줄 정도)여도 따라가야 함
bar.setValue(bar.maximum() - 20)
settle()
checks.append(("맨 아래 근처로 이동", bar.value() >= bar.maximum() - 40))

# 내가 친 메시지는 위쪽을 보고 있어도 맨 아래로 내려와야 함
bar.setValue(int(bar.maximum() * 0.2))
settle()
up_there = bar.value()
page.append_message("#a", "Mong", "내가 친 메시지", True, 4.0)
settle()
checks.append((f"내가 치면 위를 보고 있어도 맨 아래로 내려온다({up_there} -> {bar.value()})",
               bar.value() >= bar.maximum() - 40))

# 남이 친 메시지는 여전히 안 끌어내림(위 동작이 남의 메시지까지 바꾸면 안 됨)
bar.setValue(int(bar.maximum() * 0.2))
settle()
up_again = bar.value()
page.append_message("#a", "hjsong", "남이 친 메시지", False, 5.0)
settle()
checks.append((f"남이 치면 여전히 안 끌려간다({up_again} -> {bar.value()})",
               bar.value() == up_again))

# 입력창으로 실제 전송했을 때도 곧바로 내려가야 함
bar.setValue(int(bar.maximum() * 0.2))
settle()
page.message_input.line.setText("입력창에서 보냄")
page.message_input.submit()
settle()
checks.append(("입력창으로 보내면 곧바로 맨 아래로 내려온다",
               bar.value() >= bar.maximum() - 40))

print("=== 검증 결과 (새 메시지 따라가기) ===")
all_ok = True
for name, ok in checks:
    print(f"[{'OK' if ok else 'FAIL'}] {name}")
    all_ok = all_ok and ok
print("\n전체 통과:", all_ok)
_sys.exit(0 if all_ok else 1)
