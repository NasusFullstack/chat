"""채팅 기록·프로필을 중계 서버로 주고받기 - 놓친 이야기를 따라잡고 얼굴이 보이는가.

이 기능들의 값은 각각 하나씩이다:
  기록   앱을 꺼둔 사이에 오간 말을 다시 켰을 때 볼 수 있는가
  프로필 그 사람이 지금 접속해 있지 않아도 얼굴이 보이는가
  이모티콘 원본이 사라져도 안 깨지는가

인터넷이 없거나 서버가 내려가 있으면 실제 왕복 검사는 **건너뛴다**(실패로 안 센다).
"""
import os as _os
import sys as _sys

_HERE = _os.path.dirname(_os.path.abspath(__file__))
_REPO = _os.path.dirname(_HERE)

_os.environ["QT_QPA_PLATFORM"] = "offscreen"
_sys.path.insert(0, _REPO)

import io  # noqa: E402
import json  # noqa: E402
import time  # noqa: E402
import urllib.error  # noqa: E402
import urllib.request  # noqa: E402

from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])

import emoji_store  # noqa: E402
import relay  # noqa: E402
from gui.chat_log_sync import ChatLogSync  # noqa: E402
from gui.emoji_backup import needs_backup  # noqa: E402
from gui.profile_sync import ProfileSync, load_tokens  # noqa: E402

checks = []
skipped = []


def check(name, ok, detail=""):
    checks.append((name, ok, detail))


def wait_for(predicate, seconds=30):
    end = time.time() + seconds
    while time.time() < end and not predicate():
        app.processEvents()
        time.sleep(0.01)
    return predicate()


# ---------- 1) 자리 이름 (네트워크 없이) ----------
a = relay.room_id("irc", "home.pdlab.kr", 6697, "#general")
b = relay.room_id("irc", "other.example.com", 6697, "#general")
check(f"자리 이름은 24자다({len(a)}자)", len(a) == 24 and a.isalnum(), a)
check("서버가 다르면 같은 채널이라도 다른 자리다(#general이 뒤섞이면 안 된다)", a != b)
check("IRC는 대소문자를 안 가리므로 #General과 #general은 같은 자리다",
      a == relay.room_id("irc", "HOME.pdlab.kr", 6697, "#General"))
check("채널 이름이 그대로 서버에 나가지 않는다(남의 서버에 우리 방 이름을 안 적는다)",
      "general" not in a.lower())
check("사람 자리와 방 자리는 안 겹친다",
      relay.who_id("irc", "h", 1, "x") != relay.room_id("irc", "h", 1, "x"))

# ---------- 2) 이모티콘 백업 대상 고르기 ----------
check("우리 서버에 이미 있는 것은 다시 안 옮긴다",
      not needs_backup({"url": f"{relay.SERVER}/files/aa/b.png"}))
check("남의 사이트에 있는 것은 옮긴다",
      needs_backup({"url": "https://example.com/a.png"}))
check("사설망 주소는 건드리지 않는다(각자 자기 공유기를 두드리게 된다)",
      not needs_backup({"url": "http://192.168.0.1/a.png"}))

# 보관함이 원래 주소를 기억하는가 - 같은 그림을 또 저장하려 할 때 알아보려면 필요하다
real_file = emoji_store.EMOJI_STORE_FILE
emoji_store.EMOJI_STORE_FILE = _os.path.join(
    _os.environ.get("TEMP", "."), "test_emojis.json")
try:
    if _os.path.exists(emoji_store.EMOJI_STORE_FILE):
        _os.remove(emoji_store.EMOJI_STORE_FILE)
    emoji_store.add_emoji(f"{relay.SERVER}/files/aa/웃음.png", "웃음",
                          source="https://example.com/원본.png")
    check("등록한 주소로 찾을 수 있다",
          emoji_store.has_emoji(f"{relay.SERVER}/files/aa/웃음.png"))
    check("**원래 주소로도 찾을 수 있다**(같은 그림을 두 번 저장하지 않게)",
          emoji_store.has_emoji("https://example.com/원본.png"))
    again, text = emoji_store.add_emoji(f"{relay.SERVER}/files/bb/다른.png", "또",
                                        source="https://example.com/원본.png")
    check(f"같은 원본을 또 저장하려 하면 막는다({text})", not again, text)

    emoji_store.add_emoji("https://example.com/옛날.png", "옛날")
    moved = emoji_store.replace_url("https://example.com/옛날.png",
                                    f"{relay.SERVER}/files/cc/옛날.png")
    saved = [e for e in emoji_store.load_emojis() if e["name"] == "옛날"][0]
    check(f"서버로 옮기면 주소가 바뀐다({saved['url'][-12:]})",
          moved and saved["url"].startswith(relay.SERVER), saved)
    check("옮겨도 원래 주소를 잃지 않는다", saved["from"] == "https://example.com/옛날.png", saved)
finally:
    if _os.path.exists(emoji_store.EMOJI_STORE_FILE):
        _os.remove(emoji_store.EMOJI_STORE_FILE)
    emoji_store.EMOJI_STORE_FILE = real_file

# ---------- 3) 연달아 한 같은 말에 번호 매기기 ----------
sync = ChatLogSync("irc", "test.invalid", 6697)
now = time.time()
seqs = [sync._seq_for("#a", "몽키", "ㅋㅋ", now),
        sync._seq_for("#a", "몽키", "ㅋㅋ", now + 1.0),
        sync._seq_for("#a", "몽키", "다른말", now + 1.1),
        sync._seq_for("#a", "몽키", "ㅋㅋ", now + 99)]
check(f"연달아 한 같은 말에 번호를 매긴다({seqs})", seqs == [0, 1, 0, 0], seqs)
check("한참 뒤에 한 같은 말은 다시 0부터(창이 지나면 겹칠 일이 없다)", seqs[3] == 0)

sync2 = ChatLogSync("irc", "test.invalid", 6697)
# 같은 대화를 본 사람은 같은 번호를 매겨야 한다 - 받은 시각이 조금 달라도
other = [sync2._seq_for("#a", "몽키", "ㅋㅋ", now + 0.3),
         sync2._seq_for("#a", "몽키", "ㅋㅋ", now + 1.2)]
check(f"같은 대화를 본 사람끼리 같은 번호를 매긴다({other})", other == seqs[:2], other)

# ---------- 4) 실제 서버와 주고받기 ----------
alive = False
try:
    with urllib.request.urlopen(f"{relay.SERVER}/logs", timeout=8) as response:
        alive = response.status == 200
except (urllib.error.URLError, OSError, TimeoutError):
    alive = False

if not alive:
    skipped.append("서버에 닿지 않아 실제 왕복 검사를 건너뜀")
else:
    stamp = f"{time.time():.3f}"
    host = f"test-{stamp}.invalid"
    live = ChatLogSync("irc", host, 6697)
    got = {}
    live.missed.connect(lambda channel, lines: got.update(channel=channel, lines=lines))

    live.record("#방", "몽키", "아무도 없을 때 한 말", now)
    live.record("#방", "두리", "이것도", now + 1)
    live.flush()
    wait_for(lambda: False, seconds=3)      # 올라갈 시간을 준다

    live.fetch("#방", now - 60)
    ok = wait_for(lambda: bool(got), seconds=20)
    texts = [line["text"] for line in got.get("lines", [])]
    check(f"올린 대화를 도로 받아온다({texts})",
          ok and "아무도 없을 때 한 말" in texts and "이것도" in texts, got)
    check("내가 보낸 것도 기록에 남는다(빠지면 남의 기록에 구멍이 생긴다)",
          "이것도" in texts, texts)

    got.clear()
    live.fetch("#방", now + 30)
    wait_for(lambda: bool(got), seconds=6)
    check("이미 다 본 뒤라면 아무것도 안 준다", not got.get("lines"), got)

    # 여럿이 같은 대화를 올려도 한 번만 남는가
    twin = ChatLogSync("irc", host, 6697)
    twin.record("#방", "몽키", "아무도 없을 때 한 말", now + 0.4)
    twin.record("#방", "두리", "이것도", now + 1.3)
    twin.flush()
    wait_for(lambda: False, seconds=3)
    got.clear()
    live.fetch("#방", now - 60)
    wait_for(lambda: bool(got), seconds=20)
    all_texts = [line["text"] for line in got.get("lines", [])]
    check(f"남이 같은 대화를 올려도 겹쳐 보이지 않는다({len(all_texts)}줄)",
          len(all_texts) == 2, all_texts)

    # ----- 프로필 -----
    face = ("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8"
            "BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
    profiles = ProfileSync("irc", host, 6697)
    profiles.publish("몽키", face)
    wait_for(lambda: bool(load_tokens().get(relay.who_id("irc", host, 6697, "몽키"))),
             seconds=20)
    token = load_tokens().get(relay.who_id("irc", host, 6697, "몽키"), "")
    check(f"프로필을 올리면 표를 받아 적어둔다({token[:8]}...)", bool(token), token)

    # 접속해 있지 않은 사람의 얼굴을 본다 - 이 기능의 목적 그대로
    seen = {}
    watcher = ProfileSync("irc", host, 6697)
    watcher.profile_known.connect(lambda nick, avatar, display: seen.update(
        nick=nick, avatar=avatar))
    watcher.want(["몽키", "없는사람"])
    wait_for(lambda: bool(seen), seconds=20)
    check(f"그 사람이 없어도 얼굴을 받아온다({seen.get('nick')})",
          seen.get("nick") == "몽키" and seen.get("avatar") == face, seen)

    seen.clear()
    watcher.want(["몽키"])
    wait_for(lambda: False, seconds=3)
    check("한 번 받아온 사람은 다시 묻지 않는다(CTCP를 아껴 묻는 것과 같은 이유)",
          not seen, seen)

    # 남이 내 얼굴을 못 바꾼다
    stolen = urllib.request.Request(
        f"{relay.PROFILES_URL}/{relay.who_id('irc', host, 6697, '몽키')}",
        method="PUT",
        data=json.dumps({"nick": "가짜", "avatar": "AAAA"}).encode("utf-8"))
    try:
        urllib.request.urlopen(stolen, timeout=10)
        blocked = False
    except urllib.error.HTTPError as error:
        blocked = error.code == 403
    check("표 없이는 남의 얼굴을 못 바꾼다", blocked)

print("=== 검증 결과 (기록·프로필 중계) ===")
all_ok = True
for name, ok, *detail in checks:
    extra = f"  <- {detail[0]}" if detail and detail[0] and not ok else ""
    print(f"[{'OK' if ok else 'FAIL'}] {name}{extra}")
    all_ok = all_ok and ok
for note in skipped:
    print(f"[건너뜀] {note}")
print(f"\n검사 {len(checks)}개")
print("전체 통과:", all_ok)
_sys.exit(0 if all_ok else 1)
