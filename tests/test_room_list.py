"""서버에 **어떤 방이 있는지 보고 고를 수 있는가.**

예전에는 방 이름을 글자로 쳐야 했다. 이름을 모르면 들어갈 방법이 없다 - 서버 채팅은
서버가 방을 들고 있으므로 물어볼 수 있다.

여기서 지키는 것:
- 목록을 **줄 수 있는 쪽에서만** 보여준다. IRC 에서는 칸 자체가 안 보인다
  (빈 목록을 보여주면 "방이 하나도 없나" 하고 헷갈린다)
- 화면은 "지금 서버 채팅인가"를 모른다. **"목록을 줄 수 있나"**만 묻는다
- 보이는 글자에는 사람 수와 자물쇠가 섞인다 - **이름은 따로 들고 간다**
  (안 그러면 "🔒 일반 (2명)" 이라는 이름으로 들어가려 한다)
- **비밀번호는 서버가 안 보낸다.** 걸렸다는 사실만 온다
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, REPO)
sys.path.insert(0, HERE)

from chat_core import events  # noqa: E402
from chat_core.history_adapter import NullHistoryStore  # noqa: E402
from chat_core.session import build_session  # noqa: E402

checks = []


def check(name, passed, detail=""):
    checks.append((name, passed, detail))
    print(f"[{'OK' if passed else 'FAIL'}] {name}" +
          (f"  <- {detail}" if detail and not passed else ""), flush=True)


def make(protocol):
    sent, got = [], []
    session = build_session(protocol, "host", 1, transport=sent.append,
                            on_event=got.append, history_store=NullHistoryStore())
    return session, sent, got


# ---------- 1) 누가 목록을 줄 수 있나 ----------
server, sent, got = make("server")
check("서버 채팅은 방 목록을 줄 수 있다", server.can_list_rooms is True)

irc, irc_sent, _ = make("irc")
check("IRC 는 안 준다(큰 서버는 방이 수만 개다)", irc.can_list_rooms is False)
irc.request_room_list()
check("IRC 에서는 줄 하나도 안 나간다", irc_sent == [], irc_sent)

custom, custom_sent, _ = make("custom")
check("옛 커스텀 서버도 안 준다", custom.can_list_rooms is False)
custom.request_room_list()
check("거기서도 줄이 안 나간다", custom_sent == [], custom_sent)

# ---------- 2) 묻고 받기 ----------
server.request_room_list()
check("물어보는 줄은 channels 하나", sent == [{"cmd": "channels"}], sent)

server.handle_incoming({"type": "channel_list", "channels": [
    {"name": "일반", "users": 3, "locked": False},
    {"name": "비밀방", "users": 0, "locked": True},
    {"users": 9},                      # 이름이 없다 - 버려야 한다
    "방이 아니다",                      # 모양이 다르다 - 버려야 한다
]})
listed = [e for e in got if isinstance(e, events.RoomListReceived)]
check("방 목록을 받는다", len(listed) == 1, got)
rooms = listed[0].rooms
check("쓸 수 없는 줄은 버린다", [r.name for r in rooms] == ["일반", "비밀방"],
      [r.name for r in rooms])
check("몇 명 있는지 같이 온다", rooms[0].users == 3, rooms[0])
check("비밀번호가 걸렸는지 알려준다", rooms[1].locked is True, rooms[1])
check("**비밀번호 자체는 안 들고 있다**", not hasattr(rooms[1], "key"), dir(rooms[1]))

# ---------- 3) 화면 ----------
# 앱 객체를 먼저 만든다. 없이 위젯을 만들면 Qt 가 프로세스를 그냥 죽인다(CLAUDE.md 11-3)
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])

from gui.pages.channel_page import ChannelPage  # noqa: E402

page = ChannelPage(lambda mode: None)
page.show()

page.set_room_list_shown(False)
check("목록을 못 주는 서버에서는 칸을 숨긴다", not page.room_list.isVisibleTo(page))
check("새로고침 버튼도 숨긴다", not page.refresh_btn.isVisibleTo(page))

page.set_room_list_shown(True)
check("줄 수 있는 서버에서는 보인다", page.room_list.isVisibleTo(page))

page.show_rooms(rooms)
check("방이 다 보인다", page.room_list.count() == 2, page.room_list.count())
first = page.room_list.item(0)
check("사람 수를 같이 보여준다", "3명" in first.text(), first.text())
check("잠긴 방에는 자물쇠", "🔒" in page.room_list.item(1).text(),
      page.room_list.item(1).text())
check("**이름은 따로 들고 간다**",
      first.data(Qt.ItemDataRole.UserRole) == "일반",
      first.data(Qt.ItemDataRole.UserRole))

# 고르면 입력칸이 채워진다 - 핸들러를 직접 부르지 않고 **실제 경로**로 고른다
page.room_list.setCurrentRow(1)
check("고르면 이름이 칸에 들어간다", page.get_values()["channel"] == "비밀방",
      page.get_values())

# 방이 없을 때 - 빈 칸만 덩그러니 두면 "고장났나" 싶다
page.show_rooms([])
check("방이 없으면 그렇다고 적는다", page.room_list.count() == 1,
      page.room_list.count())
empty = page.room_list.item(0)
check("그 줄은 고를 수 없다(이름이 아니다)",
      empty.flags() == Qt.ItemFlag.NoItemFlags, empty.flags())

# ---------- 4) 화면이 프로토콜 이름을 알면 안 된다 ----------
with open(os.path.join(REPO, "gui", "pages", "channel_page.py"), encoding="utf-8") as fp:
    source = fp.read()
check("채널 화면이 'server' 를 이름으로 비교하지 않는다",
      '"server"' not in source and "'server'" not in source,
      "목록을 줄 수 있는가로 묻는다(능력), 무슨 프로토콜인가로 묻지 않는다")

print(f"\n검사 {len(checks)}개")
all_ok = all(passed for _, passed, *_ in checks)
print("전체 통과:", all_ok)
sys.exit(0 if all_ok else 1)
