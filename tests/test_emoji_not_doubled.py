"""이모티콘 하나를 보냈는데 **두 번 그려지던** 것을 잡는다.

## 무슨 일이었나
"이모티콘을 보내면 두 개로 보인다"는 제보.

메시지 한 줄은 두 가지를 따로 그린다:
  - 이모티콘(`emoji_area`) - 글자 옆에 붙는 작은 그림
  - 링크 미리보기(`preview_area`) - 주소를 보고 받아오는 320px 그림

그런데 미리보기 대상을 고를 때 **이모티콘을 떼어내기 전의 원문**에서 주소를 찾고
있었다. 이모티콘은 `\\ue000주소\\ue001` 모양이라 그 안의 주소가 그대로 걸린다.
그래서 같은 그림이 이모티콘으로 한 번, 미리보기로 또 한 번 그려졌다.

고치는 법은 한 글자다 - 이모티콘을 떼어낸 글자에서 찾으면 된다.

## 이 검사가 보는 것
"이모티콘이 하나면 그림 자리도 하나"다. 실제로 위젯을 만들어 센다.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, REPO)

from PySide6.QtGui import QPixmap  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])

from chat_core.commands import format_emoji  # noqa: E402
from gui.components.message_item import MessageWidget  # noqa: E402

checks = []


def check(name, ok, detail=""):
    checks.append((name, ok, detail))


EMOJI = "https://jsserv.pdlab.kr/files/090267a2f49dd02ec06d2e27/%ED%95%98%EA%B8%B0.png"
LINK = "https://example.com/news/article"

avatar = QPixmap(24, 24)
avatar.fill()


def build(text):
    return MessageWidget("몽키", text, False, 0, avatar, preview=True)


# ---------- 1) 이모티콘만 보낸 경우 ----------
one = build(format_emoji(EMOJI))
check(f"이모티콘 하나로 센다({len(one.emoji_urls)}개)", one.emoji_urls == [EMOJI],
      one.emoji_urls)
check(f"**미리보기 대상에는 안 들어간다**({one.preview_urls})",
      one.preview_urls == [], one.preview_urls)

# ---------- 2) 글 + 이모티콘 ----------
mixed = build(f"이거 봐 {format_emoji(EMOJI)} 귀엽지")
check("글과 섞여도 이모티콘은 하나", mixed.emoji_urls == [EMOJI], mixed.emoji_urls)
check(f"그래도 미리보기는 안 만든다({mixed.preview_urls})",
      mixed.preview_urls == [], mixed.preview_urls)

# ---------- 3) 이모티콘 여러 개 ----------
many = build(format_emoji(EMOJI) + format_emoji(EMOJI.replace("090", "091")))
check(f"여러 개도 이모티콘으로만 센다({len(many.emoji_urls)}개)",
      len(many.emoji_urls) == 2 and many.preview_urls == [],
      (many.emoji_urls, many.preview_urls))

# ---------- 4) 진짜 링크는 그대로 미리보기 ----------
# 이모티콘을 거르느라 평범한 링크 미리보기까지 죽이면 안 된다
link = build(f"이 기사 봐 {LINK}")
check(f"보통 링크는 여전히 미리보기 대상({link.preview_urls})",
      link.preview_urls == [LINK], link.preview_urls)
check("그건 이모티콘이 아니다", link.emoji_urls == [], link.emoji_urls)

# ---------- 5) 둘이 같이 있는 경우 ----------
both = build(f"{format_emoji(EMOJI)} 그리고 {LINK}")
check(f"이모티콘은 이모티콘, 링크는 링크({both.emoji_urls} / {both.preview_urls})",
      both.emoji_urls == [EMOJI] and both.preview_urls == [LINK],
      (both.emoji_urls, both.preview_urls))

# ---------- 6) 그림 자리가 실제로 하나뿐인가 ----------
# 숫자만 보지 말고 "화면에 그림 칸이 몇 개 만들어졌는가"를 센다
from gui.preview.area import LinkPreviewArea  # noqa: E402

areas = one.findChildren(LinkPreviewArea)
check(f"이모티콘만 보낸 줄에는 미리보기 칸이 아예 없다({len(areas)}개)",
      not areas, len(areas))

print("=== 검증 결과 (이모티콘이 두 번 안 그려지는가) ===")
all_ok = True
for name, ok, *detail in checks:
    extra = f"  <- {detail[0]}" if detail and detail[0] and not ok else ""
    print(f"[{'OK' if ok else 'FAIL'}] {name}{extra}")
    all_ok = all_ok and ok
print(f"\n검사 {len(checks)}개")
print("전체 통과:", all_ok)
sys.exit(0 if all_ok else 1)
