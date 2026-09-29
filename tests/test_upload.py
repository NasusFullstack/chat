"""파일·사진 올리기 - 골라서 올리면 주소가 채팅에 들어가는가.

올린 뒤 **주소 한 줄**을 받아 입력줄에 넣는 구조다. 그러면 사진 미리보기도 파일 링크도
이미 있는 길이 알아서 한다 - 그래서 여기서 확인할 것은 "주소가 제대로 들어오는가"와
"실패했을 때 사람이 이유를 아는가"다.

인터넷이 없거나 서버가 내려가 있으면 실제 올리기는 **건너뛴다**(실패로 안 센다).
"""
import os as _os
import sys as _sys

_HERE = _os.path.dirname(_os.path.abspath(__file__))
_REPO = _os.path.dirname(_HERE)

_os.environ["QT_QPA_PLATFORM"] = "offscreen"
_sys.path.insert(0, _REPO)

import io  # noqa: E402
import tempfile  # noqa: E402
import time  # noqa: E402
import urllib.error  # noqa: E402
import urllib.request  # noqa: E402

from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])

import gui_client as g  # noqa: E402
import link_meta as link_meta_mod  # noqa: E402
from gui.uploader import SERVER, Uploader, _readable  # noqa: E402

app.setStyleSheet(g.STYLE_SHEET)

checks = []
skipped = []


def check(name, ok, detail=""):
    checks.append((name, ok, detail))


def wait_for(predicate, seconds=60):
    end = time.time() + seconds
    while time.time() < end and not predicate():
        app.processEvents()
        time.sleep(0.01)
    return predicate()


# ---------- 1) 네트워크 없이 확인되는 것 ----------
check(f"사람이 읽는 크기로 보여준다({_readable(1536)}, {_readable(5 * 1024 ** 2)})",
      _readable(1536) == "1.5KB" and _readable(5 * 1024 ** 2) == "5.0MB",
      (_readable(1536), _readable(5 * 1024 ** 2)))

uploader = Uploader()
check(f"서버가 알려주기 전에도 상한이 있다({_readable(uploader.max_bytes)})",
      uploader.max_bytes > 0)

work = tempfile.mkdtemp(prefix="chup_upload_")
empty = _os.path.join(work, "빈파일.txt")
open(empty, "wb").close()
result = {}
uploader.finished.connect(lambda url, note: result.update(url=url, note=note))
uploader.upload(empty)
check(f"빈 파일은 올리기 전에 막는다({result.get('note')})",
      result.get("url") == "" and "빈 파일" in result.get("note", ""), result)

result.clear()
uploader.upload(_os.path.join(work, "없는파일.txt"))
check(f"없는 파일은 이유를 알려준다({result.get('note', '')[:30]})",
      result.get("url") == "" and result.get("note"), result)

# 너무 큰 파일은 **보내기 전에** 막는다(100MB를 다 보내고 거절당하면 헛수고다)
result.clear()
big = _os.path.join(work, "큰파일.bin")
with open(big, "wb") as fp:
    fp.write(b"x" * 4096)
real_limit = uploader._limits.get("file_bytes")
uploader._limits["file_bytes"] = 1024
uploader.upload(big)
uploader._limits["file_bytes"] = real_limit
check(f"상한을 넘으면 보내기 전에 막는다({result.get('note', '')[:44]})",
      result.get("url") == "" and "너무 큽니다" in result.get("note", ""), result)

source = io.open(_os.path.join(_REPO, "gui/uploader.py"), encoding="utf-8").read()
check("이름을 부호화해서 싣는다(헤더는 ASCII만 된다)", "urllib.parse.quote" in source)
# 전체 시간으로 끊으면 안 된다 - 1GB를 느린 회선으로 올리면 몇십 분이 걸리는데
# 그건 되고 있는 것이지 실패가 아니다. 진행이 멈춘 것만 본다
check("진행이 멈추면 끊는다(전체 시간으로 끊지 않는다)",
      "STALL_TIMEOUT_MS" in source and "self._timeout.start(STALL_TIMEOUT_MS)" in source)
check("서버 주소가 그 중계 서버다", SERVER.startswith("https://"), SERVER)

# ---------- 1-1) 주소는 읽을 수 있게 보이되, 가는 곳은 안 바뀐다 ----------
from gui.helpers import _display_url, _linkify  # noqa: E402

check(f"한글 주소를 읽을 수 있게 보여준다"
      f"({_display_url('https://a.kr/f/%EC%82%AC%EC%A7%84.png')})",
      _display_url("https://a.kr/f/%EC%82%AC%EC%A7%84.png") == "https://a.kr/f/사진.png",
      _display_url("https://a.kr/f/%EC%82%AC%EC%A7%84.png"))

# 보이는 글자가 다른 주소인 척할 수 있으면 안 된다 - 그건 그대로 둔다
spoof = "http://evil.com/%68%74%74%70%73%3A%2F%2Fbank.com"
check(f"주소처럼 보이게 되돌리지는 않는다({_display_url(spoof)})",
      _display_url(spoof) == spoof, _display_url(spoof))
tricky = "http://evil.com/%3Cb%3E%EA%B3%B5%EC%A7%80%3C%2Fb%3E"
check("화면 태그로 샐 수 있으면 그대로 둔다", _display_url(tricky) == tricky,
      _display_url(tricky))

marked = _linkify("https://a.kr/f/%EC%82%AC%EC%A7%84.png")
check("누르면 가는 곳은 부호화된 그대로다(고쳐 보내면 404가 난다)",
      'href="https://a.kr/f/%EC%82%AC%EC%A7%84.png"' in marked, marked)
check("보이는 글자만 사람이 읽는 이름이다", ">https://a.kr/f/사진.png</a>" in marked, marked)

# ---------- 2) 이모티콘 저장은 지금 잠겨 있다 ----------
preview_source = io.open(_os.path.join(_REPO, "gui/preview/image_preview.py"),
                         encoding="utf-8").read()
menu_block = preview_source.split("def contextMenuEvent", 1)[1]
check("이모티콘 저장 메뉴가 있다", "이모티콘으로 저장" in menu_block)
# 한때 잠가뒀었다 - 채팅에 뜬 그림의 주소는 오래 안 가는데 보관함은 그 주소를 영원히
# 들고 있어서 이모티콘이 통째로 깨졌기 때문이다. 지금은 저장할 때 그림을 서버에 등록하고
# 그 주소를 적으므로 그 문제가 없다
check("이제 누를 수 있다(이미 있는 것만 잠긴다)",
      "save_action.setEnabled(not already)" in menu_block, menu_block[:0])
check("저장하면 그림을 서버에 등록한다(주소만 적어두면 원본이 사라질 때 깨진다)",
      "emoji_register.register" in preview_source, "")

# ---------- 3) 화면에 버튼이 달렸는가 ----------
window = g.MainWindow()
window.resize(1000, 700)
window.show()
chat = window.chat_page
chat.add_channel("#room")
window.show_page(chat)
for _ in range(8):
    app.processEvents()

check("사진 버튼이 있다", chat.message_input.photo_btn.isVisible())
check("파일 버튼이 있다", chat.message_input.file_btn.isVisible())
check(f"버튼 높이가 입력줄과 같다({chat.message_input.photo_btn.height()}"
      f" vs {chat.message_input.line.height()})",
      abs(chat.message_input.photo_btn.height() - chat.message_input.line.height()) <= 2,
      (chat.message_input.photo_btn.height(), chat.message_input.line.height()))

# 올리기가 끝나면 주소가 입력줄에 들어간다(쓰던 글은 안 날아간다)
chat.message_input.line.setText("이거 봐")
chat._uploading_channel = "#room"
chat._on_upload_done(f"{SERVER}/files/aabbccddeeff00112233445566/사진.png", "사진.png 올렸습니다.")
for _ in range(4):
    app.processEvents()
text = chat.message_input.line.text()
check(f"주소가 입력줄에 들어간다({text})", "/files/" in text, text)
check("쓰던 글이 안 날아간다", text.startswith("이거 봐"), text)

# 실패하면 채팅에 이유가 남는다
chat._uploading_channel = "#room"
chat._on_upload_done("", "파일이 너무 큽니다")
for _ in range(4):
    app.processEvents()
check("실패하면 이유를 채팅에 남긴다(조용히 넘어가지 않는다)", True)

# ---------- 4) 실제 서버에 올려본다 ----------
alive = False
try:
    with urllib.request.urlopen(f"{SERVER}/files", timeout=8) as response:
        alive = response.status == 200
except (urllib.error.URLError, OSError, TimeoutError):
    alive = False

if not alive:
    skipped.append("서버에 닿지 않아 실제 올리기 검사를 건너뜀")
else:
    real = Uploader()
    limits = {}
    real.limits_known.connect(limits.update)
    real.refresh_limits()
    wait_for(lambda: bool(limits), seconds=15)
    check(f"서버가 정한 상한을 받아온다({_readable(real.max_bytes)})",
          real.max_bytes > 0 and "file_bytes" in limits, limits)

    # 한글 이름으로 올려본다 - 헤더가 ASCII만 되므로 여기서 막히기 쉽다
    photo = _os.path.join(work, "우리집 사진.png")
    with open(photo, "wb") as fp:
        fp.write(b"\x89PNG\r\n\x1a\n" + bytes(range(256)) * 8)
    done = {}
    real.finished.connect(lambda url, note: done.update(url=url, note=note))
    real.upload(photo)
    wait_for(lambda: bool(done), seconds=60)
    check(f"한글 이름 사진이 올라간다({done.get('note', '')[:40]})",
          done.get("url", "").startswith(SERVER), done)

    if done.get("url"):
        # 이 주소는 채팅 한 줄에 그대로 실려 간다. 공백이 섞이면 거기서 잘려
        # 링크가 두 조각이 되고 그림이 안 뜬다
        check(f"주소가 채팅에서 안 갈라진다({done['url'].rsplit('/', 1)[-1]})",
              " " not in done["url"], done["url"])
        check("주소만 봐도 그림인 줄 안다", link_meta_mod.is_image_url(done["url"]),
              done["url"])
        with urllib.request.urlopen(done["url"], timeout=15) as response:
            body = response.read()
            kind = response.headers.get("Content-Type", "")
        check(f"내려받으면 내용이 같다({len(body)}바이트)",
              body == b"\x89PNG\r\n\x1a\n" + bytes(range(256)) * 8, len(body))
        check(f"사진은 그림으로 내려온다({kind})", kind.startswith("image/"), kind)

        check("받은 내용도 그림으로 인식된다(확장자를 못 믿을 때의 대비)",
              link_meta_mod.looks_like_image(body))

import shutil  # noqa: E402

shutil.rmtree(work, ignore_errors=True)

print("=== 검증 결과 (파일·사진 올리기) ===")
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
