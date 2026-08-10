"""늦게 도착한 이미지 미리보기가 메시지 줄 높이를 제대로 키우는가.

실제 사고(2026-08-06): 채팅에 이미지 주소를 올리면 **어떤 이미지는 되고 어떤 이미지는
그 자리가 통째로 빈칸**이 됐다. 그림 자체는 320x320으로 멀쩡히 받아져 있는데 메시지 줄
높이는 34에서 굳어 있었다.

원인: Qt는 부모 레이아웃이 자식 위젯의 높이를 물을 때, 그 위젯에 자체 레이아웃이 있으면
위젯의 heightForWidth()가 아니라 **안쪽 레이아웃**에 묻는다. 미리보기 칸의 안쪽 레이아웃은
평범한 QVBoxLayout이었고, 담긴 것이 고정 크기 그림 라벨이라 -1(→0)을 돌려줬다.
그림이 레이아웃 계산보다 먼저 도착하면 sizeHint 경로를 타서 정상으로 보였기 때문에
"되는 이미지와 안 되는 이미지"가 갈렸다.

여기서는 네트워크 없이 그 순서를 그대로 만든다: 메시지를 먼저 배치해 높이를 굳힌 뒤,
나중에 그림 데이터를 밀어 넣는다.
"""
import os as _os
import sys as _sys

_HERE = _os.path.dirname(_os.path.abspath(__file__))
_REPO = _os.path.dirname(_HERE)

_os.environ["QT_QPA_PLATFORM"] = "offscreen"
_sys.path.insert(0, _REPO)
_sys.path.insert(0, _HERE)

from PySide6.QtCore import QBuffer, Qt
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])
import gui_client as g  # noqa: E402
from gui.preview.area import LinkPreviewArea  # noqa: E402

app.setStyleSheet(g.STYLE_SHEET)
checks = []


def check(name, ok, detail=""):
    checks.append((name, ok, detail))


def png_bytes(width: int, height: int) -> bytes:
    """시험용 그림 한 장. 네트워크 없이 '늦게 도착한 데이터'를 만들기 위함."""
    pixmap = QPixmap(width, height)
    pixmap.fill(QColor("#7c6cf0"))
    buffer = QBuffer()   # QBuffer(QByteArray())처럼 임시를 넘기면 접근 위반으로 죽는다
    buffer.open(QBuffer.OpenModeFlag.WriteOnly)
    pixmap.save(buffer, "PNG")
    return bytes(buffer.data())


URL = "https://example.com/사진.jpg"
page = g.ChatPage(on_send=lambda c, t: None, on_add_channel=lambda: None,
                  on_leave_channel=lambda c: None, on_set_avatar=lambda: None)
page.resize(900, 700)
page.show()
page.add_channel("#t")

# fetcher가 None이면 아무것도 받아오지 않는다 - '아직 안 온 상태'를 그대로 만들 수 있다
page._image_fetcher = None
page.append_message("#t", "몽키", URL, True, 1.0)
for _ in range(6):
    app.processEvents()

view = page._log_views["#t"]
widget = view._messages[0]
before = widget.height()
check(f"그림이 오기 전에는 글자 줄 높이({before}px)", 0 < before < 100, before)

areas = widget.findChildren(LinkPreviewArea)
check("미리보기 칸이 만들어져 있다", len(areas) == 1, len(areas))

# 이제서야 그림이 도착 - 실제 앱에서 네트워크 응답이 오는 시점과 같다
areas[0]._on_direct_image(URL, png_bytes(600, 600))
for _ in range(8):
    app.processEvents()

after = widget.height()
check(f"그림이 도착하면 줄 높이가 커진다({before} -> {after})", after > before + 200,
      (before, after))
check(f"원하는 높이도 같이 커진다({widget.sizeHint().height()})",
      widget.sizeHint().height() > before + 200, widget.sizeHint().height())

# 부모 레이아웃이 실제로 물어보는 경로(안쪽 레이아웃)로도 답이 나와야 한다.
# 이 검사가 이번 버그의 핵심이다 - 위젯의 heightForWidth만 고치면 통과하지 못한다
row = widget.layout()
check(f"줄 레이아웃이 폭을 받아 제대로 답한다(hfw={row.heightForWidth(widget.width())})",
      row.heightForWidth(widget.width()) > 200, row.heightForWidth(widget.width()))
inner = areas[0].layout()
check(f"미리보기 칸의 안쪽 레이아웃이 0을 답하지 않는다(hfw={inner.heightForWidth(400)})",
      inner.heightForWidth(400) > 200, inner.heightForWidth(400))

# 대화 목록 전체 높이에도 반영돼야 빈 공간이 안 남는다
content = view.widget()
check(f"대화 목록이 그림 높이를 포함해서 잰다({content.measured_height()}px)",
      content.measured_height() > after, content.measured_height())

print("=== 검증 결과 (늦게 도착한 이미지 미리보기) ===")
all_ok = True
for name, ok, *detail in checks:
    extra = f"  <- {detail[0]}" if detail and detail[0] and not ok else ""
    print(f"[{'OK' if ok else 'FAIL'}] {name}{extra}")
    all_ok = all_ok and ok
print("\n전체 통과:", all_ok)
_sys.exit(0 if all_ok else 1)
