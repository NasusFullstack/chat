"""남이 그냥 이미지 주소로 보낸 것을 우클릭해서 내 이모티콘으로 저장하는 경로.

메뉴를 눈으로 여는 대신 실제 저장 경로(themed_get_text로 이름 입력 -> emoji_store)를
그대로 태운다. 이름 입력 창은 테스트가 바꿔치기한다(기존 테스트들과 같은 방식).
"""
import os as _os
import sys as _sys

_HERE = _os.path.dirname(_os.path.abspath(__file__))
_REPO = _os.path.dirname(_HERE)

_os.environ["QT_QPA_PLATFORM"] = "offscreen"
_sys.path.insert(0, _REPO)
_sys.path.insert(0, _HERE)

import tempfile

from PySide6.QtWidgets import QApplication

import emoji_store

emoji_store.EMOJI_STORE_FILE = _os.path.join(tempfile.gettempdir(), "test_emojis_menu.json")
if _os.path.exists(emoji_store.EMOJI_STORE_FILE):
    _os.remove(emoji_store.EMOJI_STORE_FILE)

app = QApplication.instance() or QApplication([])
import gui_client as g
from gui.link_preview import ImagePreview

checks = []
SHARED = "https://example.com/friend/funny.gif"

# 남이 올린 이미지 미리보기 위젯(채팅에 뜬 그 그림)
preview = ImagePreview(SHARED)
checks.append(("미리보기에서 주소를 꺼낼 수 있음", preview.url == SHARED))

# 이름 입력 창을 가짜로 바꿔치기 - 반드시 gui_client 속성으로 조회돼야 먹힘
asked = {}


def fake_get_text(parent, title, label, *args, **kwargs):
    asked["title"] = title
    asked["label"] = label
    return "친구 짤", True


warned = []
g.themed_get_text = fake_get_text
g.themed_warning = lambda parent, title, text: warned.append(text)


def save_via_menu(target):
    """contextMenuEvent 본문과 같은 순서로 저장 경로를 실행"""
    import gui_client
    name, ok = gui_client.themed_get_text(target, "이모티콘 저장", "이름을 입력하세요")
    if not ok:
        return False
    saved, text = emoji_store.add_emoji(target.url, name)
    if not saved:
        gui_client.themed_warning(target, "이모티콘 저장", text)
    return saved


ok = save_via_menu(preview)
checks.append(("우클릭 저장이 보관함에 들어감", ok and emoji_store.has_emoji(SHARED)))
checks.append(("이름 입력 창이 떴음", bool(asked.get("title"))))
checks.append(("입력한 이름으로 저장됨",
               emoji_store.load_emojis()[0]["name"] == "친구 짤"))
checks.append(("주소만 저장(그림 파일 없음)",
               set(emoji_store.load_emojis()[0]) == {"url", "name"}))

# 두 번째 저장 시도는 막히고 안내가 떠야 함
again = save_via_menu(preview)
checks.append(("이미 있는 건 다시 저장 안 됨", not again))
checks.append(("이미 있다고 알려줌", any("이미" in w for w in warned)))

# 사설망 주소는 저장되면 안 됨
bad = ImagePreview("http://192.168.0.5/cam.png")
saved_bad = save_via_menu(bad)
checks.append(("사설망 이미지 주소는 저장 거부", not saved_bad))

# 취소하면 아무 일도 없어야 함
g.themed_get_text = lambda *a, **k: ("", False)
count_before = len(emoji_store.load_emojis())
save_via_menu(ImagePreview("https://example.com/other.png"))
checks.append(("이름 입력을 취소하면 저장 안 함",
               len(emoji_store.load_emojis()) == count_before))

print("=== 검증 결과 (우클릭 이모티콘 저장) ===")
all_ok = True
for name, ok in checks:
    print(f"[{'OK' if ok else 'FAIL'}] {name}")
    all_ok = all_ok and ok
print("\n전체 통과:", all_ok)
_sys.exit(0 if all_ok else 1)
