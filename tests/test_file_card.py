"""올린 파일이 채팅에서 카드로 보이는가, 올리는 중에 멈출 수 있는가.

이 기능들의 값:
  카드     주소 한 줄만 보고는 무슨 파일인지도 아직 살아 있는지도 알 수 없다
  내리기   잘못 올린 것을 되돌릴 수 있어야 한다(서버에서도 지워져야 한다)
  진행률   1GB까지 올릴 수 있으니 몇 분씩 걸린다 - 표시가 없으면 멈춘 줄 안다
  끌어놓기 고르는 창을 거치지 않고 바로 올릴 수 있어야 한다
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

from PySide6.QtCore import QMimeData, QPoint, QUrl, Qt  # noqa: E402
from PySide6.QtGui import QDropEvent, QPixmap  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])

import file_tokens  # noqa: E402
import gui_client as g  # noqa: E402
import relay  # noqa: E402
from gui.components.message_item import MessageWidget  # noqa: E402
from gui.preview.file_card import (FileCard, parse_meta, readable_size,  # noqa: E402
                                   remaining_text)

app.setStyleSheet(g.STYLE_SHEET)

checks = []


def check(name, ok, detail=""):
    checks.append((name, ok, detail))


FILE_ID = "a1b2c3d4e5f60718293a4b5c"
URL = f"{relay.SERVER}/files/{FILE_ID}/%EB%AC%B8%EC%84%9C.pdf"


# ---------- 1) 주소를 보고 우리 파일인 줄 아는가 ----------
check(f"우리 서버 파일 주소를 알아본다({relay.file_id_from(URL)})",
      relay.file_id_from(URL) == FILE_ID, relay.file_id_from(URL))
check("남의 사이트 주소는 아니다",
      relay.file_id_from("https://example.com/files/aaa/b.png") == "")
# /files/emoji 같은 다른 경로를 파일 id로 오인하면 엉뚱한 곳에 묻게 된다
check("파일 id 모양이 아니면 아니다",
      relay.file_id_from(f"{relay.SERVER}/files/emoji?group=x") == "")

# ---------- 2) 사람이 읽는 말로 ----------
check(f"크기를 읽기 쉽게({readable_size(878900)})", readable_size(878900) == "858.3KB")
now = time.time()
check(f"몇 시간 남았는지({remaining_text(now + 3 * 3600, now)})",
      remaining_text(now + 3 * 3600, now) == "3시간 뒤 사라짐")
check(f"한 시간 안이면 분으로({remaining_text(now + 300, now)})",
      remaining_text(now + 300, now) == "5분 뒤 사라짐")
check("이미 지났으면 그렇다고 알려준다",
      "사라졌" in remaining_text(now - 10, now), remaining_text(now - 10, now))
check("기한이 없으면 아무 말도 안 한다(이모티콘)", remaining_text(0) == "")

# ---------- 3) 서버 답을 읽는가 ----------
good = json.dumps({"id": FILE_ID, "name": "문서.pdf", "size": 4000,
                   "expires": now + 7200, "image": False}).encode("utf-8")
check("서버 답을 읽는다", parse_meta(good) is not None)
check("없는 파일이면 카드를 안 만든다",
      parse_meta(json.dumps({"error": "없습니다"}).encode("utf-8")) is None)
check("깨진 답이면 카드를 안 만든다", parse_meta(b"\xff\xfe not json") is None)

# ---------- 4) 카드가 무엇을 보여주는가 ----------
info = json.loads(good.decode("utf-8"))
file_tokens.forget(FILE_ID)
card = FileCard(URL, info)
check(f"이름을 보여준다({card.name_label.text()})", card.name_label.text() == "문서.pdf")
check(f"크기와 남은 기간을 함께({card.info_label.text()})",
      "3.9KB" in card.info_label.text() and "사라짐" in card.info_label.text(),
      card.info_label.text())
check("남의 파일에는 '내리기'가 없다", card.drop_btn.isHidden())

# 내가 올린 것이면(표가 있으면) 내릴 수 있다
file_tokens.remember(FILE_ID, "f" * 32)
mine = FileCard(URL, info)
check("내가 올린 것에는 '내리기'가 보인다", not mine.drop_btn.isHidden())
check("표를 적어두면 내 것으로 안다", file_tokens.is_mine(FILE_ID))
file_tokens.forget(FILE_ID)
check("표를 지우면 남의 것이 된다", not file_tokens.is_mine(FILE_ID))

source = io.open(_os.path.join(_REPO, "gui/preview/file_card.py"), encoding="utf-8").read()
check("받기는 브라우저에 맡긴다(이어받기·검사를 브라우저가 한다)",
      "QDesktopServices.openUrl" in source)

# ---------- 5) 카드가 뜨면 주소 글자는 사라진다 ----------
avatar = QPixmap(24, 24)
avatar.fill()
item = MessageWidget("몽키", f"자료 올렸어 {URL}", False, 0, avatar, preview=True)
before = item._text_label.text()
item._drop_url_text(URL)
after = item._text_label.text()
check(f"카드가 뜨면 주소 글자가 빠진다({after})",
      URL not in after and "/files/" not in after, after)
check("사람이 쓴 말은 남는다", "자료 올렸어" in after, after)
check("빼기 전에는 주소가 있었다(검사가 헛돌지 않게)", "/files/" in before)

only_url = MessageWidget("몽키", URL, False, 0, avatar, preview=True)
only_url._drop_url_text(URL)
check(f"주소만 보냈으면 이름만 남는다({only_url._text_label.text()})",
      only_url._text_label.text().strip() == "몽키", only_url._text_label.text())

# ---------- 6) 올리는 중 표시와 취소 ----------
window = g.MainWindow()
window.resize(1000, 700)
chat = window.chat_page
chat.add_channel("#room")
window.show_page(chat)
window.show()
for _ in range(6):
    app.processEvents()

check("평소에는 올리는 줄이 안 보인다", chat.upload_bar.isHidden())
chat.upload_bar.start("큰영상.mp4")
check("올리기 시작하면 나타난다", not chat.upload_bar.isHidden())
check(f"무엇을 올리는지 보여준다({chat.upload_bar.name_label.text()})",
      chat.upload_bar.name_label.text() == "큰영상.mp4")
chat.upload_bar.set_progress(37, 100)
check(f"진행률을 보여준다({chat.upload_bar.percent_label.text()})",
      chat.upload_bar.percent_label.text() == "37%", chat.upload_bar.percent_label.text())
chat.upload_bar.stop()
check("끝나면 사라진다", chat.upload_bar.isHidden())

# 취소하면 줄 서 있던 것도 같이 비운다 - 하나만 멈추고 나머지가 계속 올라가면 당황한다
chat._upload_queue = ["a.bin", "b.bin"]
chat._uploading_channel = "#room"
chat._cancel_upload()
check(f"취소하면 기다리던 것도 비운다({len(chat._upload_queue)}개 남음)",
      not chat._upload_queue, chat._upload_queue)
chat._uploading_channel = ""

# ---------- 7) 끌어다 놓기 ----------
check("창이 끌어다 놓기를 받는다", chat.acceptDrops())

work = _os.path.join(_os.environ.get("TEMP", "."), "chup_drop_test")
_os.makedirs(work, exist_ok=True)
dropped = _os.path.join(work, "끌어놓은파일.txt")
with open(dropped, "wb") as fp:
    fp.write(b"hello")
folder = _os.path.join(work, "폴더")
_os.makedirs(folder, exist_ok=True)

mime = QMimeData()
mime.setUrls([QUrl.fromLocalFile(dropped), QUrl.fromLocalFile(folder)])
event = QDropEvent(QPoint(10, 10), Qt.DropAction.CopyAction, mime,
                   Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
started = {}
chat._begin_upload = lambda path: started.setdefault("path", path)
chat.dropEvent(event)
# Qt는 경로를 '/'로 돌려주므로 글자 그대로 비교하면 안 된다
check(f"끌어다 놓으면 올리기가 시작된다({_os.path.basename(started.get('path', ''))})",
      _os.path.normcase(_os.path.normpath(started.get("path", "")))
      == _os.path.normcase(_os.path.normpath(dropped)), started)
check("폴더는 건너뛴다(안에 뭐가 얼마나 있을지 모른다)",
      folder not in chat._upload_queue and started.get("path") != folder)

import shutil  # noqa: E402

shutil.rmtree(work, ignore_errors=True)

print("=== 검증 결과 (파일 카드·올리기) ===")
all_ok = True
for name, ok, *detail in checks:
    extra = f"  <- {detail[0]}" if detail and detail[0] and not ok else ""
    print(f"[{'OK' if ok else 'FAIL'}] {name}{extra}")
    all_ok = all_ok and ok
print(f"\n검사 {len(checks)}개")
print("전체 통과:", all_ok)
_sys.exit(0 if all_ok else 1)
