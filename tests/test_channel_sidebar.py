"""왼쪽 채널 사이드바 - 진짜 마우스 클릭 경로로 검증.

예전 가로 탭 시절 테스트(test_addtab_*.py)가 지키던 보장을 새 구조로 옮긴 것.
CLAUDE.md 6번 규칙: 핸들러 직접 호출로는 못 잡는 버그가 있었으므로 QTest로 진짜 클릭함
(disabled 탭이 마우스 이벤트를 아예 못 받던 문제를 그렇게 발견했었다).
"""
import os as _os
import sys as _sys

_HERE = _os.path.dirname(_os.path.abspath(__file__))
_REPO = _os.path.dirname(_HERE)

import os, sys
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, _REPO)

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMenu

import gui_client as g

app = QApplication.instance() or QApplication([])
app.setStyleSheet(g.STYLE_SHEET)
fails = []


def check(label, cond, extra=""):
    print(("  OK   " if cond else "  FAIL ") + label + ("" if cond else f"  <- {extra}"))
    if not cond:
        fails.append(label)


events = {"add": 0, "leave": []}
page = g.ChatPage(
    on_send=lambda ch, t: None,
    on_add_channel=lambda: events.__setitem__("add", events["add"] + 1),
    on_leave_channel=lambda ch: events["leave"].append(ch),
    on_set_avatar=lambda: None,
)
page.resize(900, 600)
page.show()
app.processEvents()


def click_row(row):
    """사이드바 항목을 진짜 마우스로 클릭"""
    lst = page.channel_sidebar.list
    rect = lst.visualItemRect(lst.item(row))
    QTest.mouseClick(lst.viewport(), Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier, rect.center())
    QTest.qWait(30)


print("[1] 초기 상태")
check("채널이 없으면 사이드바도 비어있음", page.channel_sidebar.list.count() == 0)
check("'+' 버튼은 항상 있음", page.channel_sidebar.add_btn.isVisible())
check("채널 헤더는 비어있음", page.channel_header.text() == "", page.channel_header.text())

print("\n[2] 채널 추가")
page.add_channel("chanA")
page.add_channel("chanB")
app.processEvents()
check("사이드바에 2줄", page.channel_sidebar.list.count() == 2, page.channel_sidebar.list.count())
check("추가 순서대로", [page.channel_sidebar.list.item(i).text() for i in range(2)] == ["chanA", "chanB"])
check("마지막에 추가한 채널이 활성", page.active_channel() == "chanB", page.active_channel())
check("사이드바 선택도 그 채널", page.channel_sidebar.list.currentRow() == 1, page.channel_sidebar.list.currentRow())
check("채널 헤더에 이름 표시", page.channel_header.text() == "chanB", page.channel_header.text())

print("\n[3] '+' 버튼을 진짜 클릭하면 채널 추가 콜백이 불리는가")
before = page.active_channel()
QTest.mouseClick(page.channel_sidebar.add_btn, Qt.MouseButton.LeftButton)
QTest.qWait(30)
check("on_add_channel 호출됨(진짜 클릭 경로)", events["add"] == 1, events["add"])
check("'+' 눌러도 활성 채널은 그대로", page.active_channel() == before, page.active_channel())

print("\n[4] 사이드바 항목을 진짜 클릭하면 채널이 바뀌는가")
click_row(0)
check("chanA로 전환됨", page.active_channel() == "chanA", page.active_channel())
check("채팅 내용도 같이 바뀜",
      page.tabs.currentWidget() is page._log_views["chanA"])
check("헤더도 따라 바뀜", page.channel_header.text() == "chanA", page.channel_header.text())
click_row(1)
check("chanB로 되돌아옴", page.active_channel() == "chanB", page.active_channel())

print("\n[5] 우클릭 나가기")
# QMenu.exec는 모달이라 테스트에서 그대로 부르면 멈춘다(실제로 멈춰서 중단시켰음).
# 메뉴가 열리는 순간 첫 항목을 고른 것처럼 만들기 위해, ChatPage가 쓰는 QMenu를
# 잠깐 가짜로 바꿔치기함
import gui.pages as pages_mod


class FakeMenu:
    """QMenu 대역 - addAction으로 담긴 첫 항목을 고른 것으로 처리"""
    last = None

    def __init__(self, *a, **k):
        self._actions = []
        FakeMenu.last = self

    def addAction(self, text):
        self._actions.append(text)
        return text

    def exec(self, *a, **k):
        return self._actions[0] if self._actions else None


# 우클릭 메뉴는 이제 사이드바 컴포넌트가 띄운다
from gui.components import channel_sidebar as sidebar_mod
orig_menu = sidebar_mod.QMenu
orig_question = g.themed_question
sidebar_mod.QMenu = FakeMenu
g.themed_question = lambda *a, **k: True
try:
    lst = page.channel_sidebar.list
    rect = lst.visualItemRect(lst.item(0))
    page.channel_sidebar._show_menu(rect.center())
finally:
    sidebar_mod.QMenu = orig_menu
    g.themed_question = orig_question

menu_text = FakeMenu.last._actions[0] if FakeMenu.last and FakeMenu.last._actions else ""
check("메뉴에 나가기 항목이 뜸", "나가기" in menu_text, menu_text)
check("메뉴에 어느 채널인지 표시됨", "chanA" in menu_text, menu_text)
check("나가기 콜백이 그 채널로 불림", events["leave"] == ["chanA"], events["leave"])

print("\n[6] 안읽음 표시가 사이드바에 뜨는가")
page.append_message("chanA", "Mong", "안녕", False, 1.0)  # chanA는 비활성
QTest.qWait(60)
row_a = page.channel_sidebar.row_of("chanA")
check("비활성 채널 줄에 표시 아이콘", row_a >= 0 and not page.channel_sidebar.list.item(row_a).icon().isNull(),
      "아이콘 없음")
click_row(row_a)
check("그 채널을 보면 표시가 사라짐", page.channel_sidebar.list.item(row_a).icon().isNull())

print("\n[7] 채널 제거")
page.remove_channel("chanA")
app.processEvents()
check("사이드바에서도 사라짐", page.channel_sidebar.list.count() == 1, page.channel_sidebar.list.count())
check("남은 건 chanB", page.channel_sidebar.list.item(0).text() == "chanB")
check("남은 채널이 활성", page.active_channel() == "chanB", page.active_channel())

print("\n[8] 로그아웃 정리")
page.reset()
app.processEvents()
check("사이드바 비워짐", page.channel_sidebar.list.count() == 0, page.channel_sidebar.list.count())
check("헤더도 비워짐", page.channel_header.text() == "", page.channel_header.text())

print("\n[9] 긴 채널명도 사이드바 폭 안에 들어옴")
page.add_channel("#아주아주긴채널이름입니다정말로깁니다")
app.processEvents()
lst = page.channel_sidebar.list
check("항목 폭이 사이드바를 안 넘음",
      lst.visualItemRect(lst.item(0)).width() <= lst.viewport().width(),
      (lst.visualItemRect(lst.item(0)).width(), lst.viewport().width()))
check("가로 스크롤 없음", lst.horizontalScrollBar().maximum() == 0,
      lst.horizontalScrollBar().maximum())
check("전체 이름은 툴팁으로", "긴채널이름" in lst.item(0).toolTip())

print()
if fails:
    print(f"실패 {len(fails)}건: {fails}")
    sys.exit(1)
print("전부 통과")
