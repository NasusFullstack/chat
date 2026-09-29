"""전투 한 판을 처음부터 끝까지 끌고 가는 담당.

창(MainWindow)이 이 일을 직접 하면 그 파일이 또 불어난다. 여기가 하는 일은 하나다 -
**대기방 · 중계 연결 · 전투 화면을 서로 이어주는 것.**

    '배틀크루저 전투'     -> 방 번호를 만들고 대기방을 연다 + 채널에 방 번호를 알린다
    '배틀크루저 전투 참가' -> 이 채널에 알려진 방으로 들어가 대기방을 본다
    방장이 [시작]         -> 대기방을 닫고 전투 화면을 띄운다
    ESC                  -> "이탈하시겠습니까?" 물어보고 그만둔다

바깥과는 신호로만 대화한다. 채팅에 글을 남기는 것도 신호로 올려서 창이 한다 -
여기가 채팅 화면을 직접 만지면 또 서로 엉킨다.
"""
from PySide6.QtCore import QObject, Signal

import battle_protocol as bp
from gui.battle.arena import BattleArena, format_kill_line
from gui.battle.lobby import BattleLobby
from gui.battle.net import BattleLink

# 방 알림을 이만큼 지나면 잊는다. 옛날에 열린 방에 들어가려다 "이미 끝난 방"을 만나는
# 것보다, 아예 "열린 방이 없다"고 말해주는 편이 낫다
ROOM_MEMORY_SEC = 30 * 60


class BattleController(QObject):
    """전투 진행. 창은 이걸 하나 들고 치트 두 개만 넘겨주면 된다."""

    system_notice = Signal(str, str)     # 채널, 글 - 채팅에 안내 한 줄
    announce_room = Signal(str, str)     # 채널, 방 번호 - 채널에 알려야 함

    def __init__(self, chat_page, parent=None):
        super().__init__(parent)
        self._page = chat_page
        self._link = None
        self._lobby = None
        self._arena = None
        self._channel = ""
        self._room = ""
        self._is_host = False
        self._nick = ""
        self._known_rooms = {}           # 채널 -> (방 번호, 연 사람)

    # ---------------- 치트가 부르는 것 ----------------
    def open_room(self, channel: str, nick: str, now: float):
        """'배틀크루저 전투' - 방을 열고 대기방을 띄운다."""
        if self._busy(channel):
            return
        self._begin(channel, nick, room=bp.new_room(), is_host=True)
        # 채널 사람들이 들어올 수 있게 방 번호를 알린다. **주소는 안 나간다**
        self.announce_room.emit(channel, self._room)

    def join_room(self, channel: str, nick: str, now: float):
        """'배틀크루저 전투 참가' - 이 채널에 알려진 방으로 들어간다."""
        if self._busy(channel):
            return
        known = self._known_rooms.get(channel)
        if known is None or now - known[2] > ROOM_MEMORY_SEC:
            self._known_rooms.pop(channel, None)
            self.system_notice.emit(
                channel, "지금 열린 전투가 없습니다. '배틀크루저 전투'로 방을 만들 수 있습니다.")
            return
        self._begin(channel, nick, room=known[0], is_host=False)

    def remember_room(self, channel: str, host: str, room: str, now: float):
        """누가 방을 열었다는 알림을 받았다 - 참가할 수 있게 적어둔다."""
        self._known_rooms[channel] = (room, host, now)
        self.system_notice.emit(
            channel, f"{host}님이 배틀크루저 전투를 열었습니다. "
                     f"'배틀크루저 전투 참가'를 입력하면 들어갑니다.")

    def stop(self):
        """화면 전환·로그아웃 등 - 연출 없이 즉시 정리한다."""
        self._teardown()

    @property
    def is_running(self) -> bool:
        return self._link is not None

    # ---------------- 준비 ----------------
    def _busy(self, channel: str) -> bool:
        if self._link is None:
            return False
        self.system_notice.emit(channel, "이미 전투에 참여하고 있습니다.")
        return True

    def _begin(self, channel: str, nick: str, room: str, is_host: bool):
        self._channel = channel
        self._nick = nick
        self._room = room
        self._is_host = is_host

        self._lobby = BattleLobby(is_host=is_host, my_nick=nick, parent=self._page.window())
        self._lobby.color_chosen.connect(self._on_color_chosen)
        self._lobby.capacity_chosen.connect(self._on_capacity_chosen)
        self._lobby.bots_chosen.connect(self._on_bots_chosen)
        self._lobby.start_pressed.connect(self._on_start_pressed)
        self._lobby.closed.connect(self._on_lobby_closed)

        self._link = BattleLink(self)
        self._link.joined.connect(self._on_joined)
        self._link.peer_joined.connect(self._on_peer_joined)
        self._link.peer_left.connect(self._on_peer_left)
        self._link.started.connect(self._on_started)
        self._link.peer_input.connect(self._on_peer_input)
        self._link.peer_hit.connect(self._on_peer_hit)
        self._link.peer_dead.connect(self._on_peer_dead)
        self._link.refused.connect(self._on_refused)
        self._link.failed.connect(self._on_failed)

        self._lobby.show()
        self._link.join(room, nick, color=self._lobby.color.currentData() or 0,
                        cap=self._lobby.capacity.currentData() or bp.MAX_HUMANS,
                        bots=self._lobby.bot_count_now())

    # ---------------- 대기방에서 오는 것 ----------------
    def _on_color_chosen(self, color: int):
        """색을 바꾸면 자리를 다시 잡는다(서버가 색을 자리에 매어두기 때문).

        **끊었다 다시 붙는 것이라 그 사이의 '끊김'을 사고로 보면 안 된다.** 예전에는
        그걸 연결 실패로 읽어 전투가 통째로 취소됐다 - link.rejoin()이 그 구간을
        표시해 두고 조용히 넘어간다.
        """
        if self._link is None or self._arena is not None:
            return
        self._link.rejoin(self._room, self._nick, color=color,
                          cap=self._lobby.capacity.currentData() or bp.MAX_HUMANS,
                          bots=self._lobby.bot_count_now())

    def _on_capacity_chosen(self, _capacity: int):
        self._resettle()

    def _on_bots_chosen(self, _count: int):
        self._resettle()

    def _resettle(self):
        """정원/연습 상대 수가 바뀌면 서버에 다시 알린다(방장만 정할 수 있다)."""
        if self._link is None or not self._is_host or self._arena is not None:
            return
        self._on_color_chosen(self._lobby.color.currentData() or 0)

    def _on_start_pressed(self):
        if self._link is not None:
            self._link.start_battle()

    def _on_lobby_closed(self):
        # 대기방을 닫은 것이 전투를 그만둔 것인지, 전투가 시작돼 닫힌 것인지 가른다
        if self._arena is None:
            self._teardown()

    # ---------------- 중계에서 오는 것 ----------------
    def _on_joined(self, slot, color, capacity, players, bots):
        if self._lobby is None:
            return
        self._lobby.set_me(slot, color, capacity)
        self._lobby.set_bots(bots)     # 손님도 몇 대인지 알아야 같은 배를 그린다
        self._lobby.set_players(players)

    def _on_peer_joined(self, slot, nick, color):
        if self._lobby is not None:
            self._lobby.add_player(slot, nick, color)

    def _on_peer_left(self, slot):
        if self._lobby is not None:
            self._lobby.remove_player(slot)
        if self._arena is not None:
            self._arena.remove_player(slot)

    def _on_started(self):
        if self._lobby is None or self._arena is not None:
            return
        players = dict(self._lobby._players)          # 자리 -> (이름, 색)
        # **연습 상대는 방장만 굴린다.** 손님도 같은 자리에 같은 배를 그리지만, 그 배의
        # 조작은 방장이 보내준 것을 받아 쓴다(각자 계산하면 위치가 갈린다)
        ai_slots = self._lobby.bot_slots() if self._is_host else []
        taken = {color for _n, color in players.values()}
        for index, slot in enumerate(self._lobby.all_bot_slots()):
            color = next((c for c in range(bp.COLOR_COUNT - 1) if c not in taken),
                         index % (bp.COLOR_COUNT - 1))
            taken.add(color)
            players[slot] = (f"연습 상대 {index + 1}", color)

        self._arena = BattleArena(self._page.battle_host())
        self._arena.setGeometry(self._page.battle_host().rect())
        self._arena.attach_input(self._page.message_input.line)
        self._arena.input_ready.connect(self._on_my_input)
        # 연습 상대는 방장만 굴린다 - 손님 쪽에서는 이 신호가 아예 안 나온다
        self._arena.bot_input.connect(self._link.send_bot_input)
        self._arena.bot_hit.connect(self._link.send_bot_hit)
        self._arena.bot_dead.connect(self._link.send_bot_dead)
        self._arena.i_was_hit.connect(self._link.send_hit)
        self._arena.i_died.connect(self._link.send_dead)
        self._arena.killed.connect(self._on_kill)
        self._arena.escape_pressed.connect(self._ask_leave)
        self._arena.start(self._lobby._my_slot, players, ai_slots=ai_slots)

        self._lobby.close()
        self._lobby = None
        self.system_notice.emit(self._channel,
                                "전투 시작! 방향키로 움직이고 스페이스로 야마토포를 쏩니다. "
                                "ESC를 누르면 나갑니다.")

    def _on_my_input(self, tick, keys):
        if self._link is not None:
            self._link.send_input(tick, keys)

    def _on_peer_input(self, slot, tick, keys):
        if self._arena is not None:
            self._arena.apply_peer_input(slot, tick, keys)

    def _on_peer_hit(self, slot, by, hp):
        if self._arena is not None:
            self._arena.apply_peer_hit(slot, by, hp)

    def _on_peer_dead(self, slot, by):
        if self._arena is not None:
            self._arena.apply_peer_dead(slot, by)

    def _on_kill(self, slot, by):
        if self._arena is None:
            return
        self.system_notice.emit(
            self._channel, format_kill_line(self._arena.name_of(by), self._arena.name_of(slot)))

    def _on_refused(self, why: str):
        self.system_notice.emit(self._channel, f"전투에 들어갈 수 없습니다: {why}")
        self._teardown()

    def _on_failed(self, why: str):
        self.system_notice.emit(self._channel, why)
        self._teardown()

    # ---------------- 이탈 ----------------
    def _ask_leave(self):
        import gui_client  # 지연 import - 이유는 CLAUDE.md 1번

        if gui_client.themed_question(self._page.window(), "전투 이탈",
                                      "전투에서 이탈하시겠습니까?"):
            self.system_notice.emit(self._channel, "전투에서 이탈했습니다.")
            self._teardown()

    def _teardown(self):
        if self._arena is not None:
            self._arena.attach_input(None)
            self._arena.stop()
            self._arena.deleteLater()
            self._arena = None
        if self._lobby is not None:
            lobby, self._lobby = self._lobby, None
            lobby.close()
        if self._link is not None:
            link, self._link = self._link, None
            link.leave()
        self._channel = ""
        self._room = ""
