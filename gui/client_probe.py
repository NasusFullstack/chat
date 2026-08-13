"""누가 무슨 프로그램으로 접속했는지 알아보는 일만 담당한다.

창(MainWindow)에서 떼어낸 이유: 이 일은 화면과 거의 상관이 없는데도 상태를 다섯 개나
들고 있었다(이미 물어본 사람, 채널별 마지막 요청 시각, 예약 여부, 거절당한 시각,
직전에 본 참여자 목록). 창을 열 때마다 이 상태들이 같이 보여서 "창이 무슨 일을 하는
물건인지"가 흐려졌다.

여기서 하는 판단은 전부 **아껴 묻기**에 관한 것이다 - 자세한 근거는 CLAUDE.md 2-4 참고.
화면에 직접 손대지 않고, 사용자에게 알릴 일이 있으면 생성자로 받은 notify()에 맡긴다.
"""
import time

from PySide6.QtCore import QObject, QTimer

import app_prefs
import client_version_store


class ClientProbeController(QObject):
    def __init__(self, prober, notify, parent=None):
        """prober: 천천히 물어보는 담당(gui/version_prober.py)
        notify(채널, 글자): 사용자에게 한 줄 알려야 할 때 부르는 함수"""
        super().__init__(parent)
        self._prober = prober
        self._notify = notify
        self._seen_members: dict[str, set] = {}
        self._asked_in_channel: dict[str, set] = {}
        self._channel_probed: dict[str, float] = {}
        self._retry_scheduled: set[str] = set()
        self._probe_refused_at = 0.0

    def reset(self):
        """서버가 바뀌면 사람도 프로그램도 다른 세상이다 - 전부 잊는다."""
        self._prober.reset()
        self._seen_members.clear()
        self._asked_in_channel.clear()
        self._channel_probed.clear()
        self._retry_scheduled.clear()
        self._probe_refused_at = 0.0

    # 서버가 "그런 요청은 못 받는다"고 알려주는 말들. 서버마다 문구가 달라서 표로 둔다.
    # (실제로 UnrealIRCd가 "Multi-target messaging is not allowed"로 거절했고,
    #  참여자 수만큼 경고가 채팅창에 쏟아졌다)
    _PROBE_REFUSED_MARKERS = (
        "multi-target messaging is not allowed",
        "too many targets",
        "target change too fast",
        "no ctcp allowed",
        "ctcp is not allowed",
        "excess flood",
    )

    # 채널에 한 줄 물어보는 것 사이의 최소 간격. 새로 들어온 사람도 결국 표시되지만,
    # 사람이 들락거릴 때마다 채널 전체에 요청이 나가지는 않는다
    _CHANNEL_PROBE_COOLDOWN_SEC = 90

    # 거절이 한 번 나온 뒤 이만큼은 같은 경고를 우리 탓으로 보고 삼킨다.
    # 이미 보내놓은 요청들의 답이 뒤늦게 도착하기 때문(실제로 멈춘 뒤에도 한 줄 더 떴다)
    _PROBE_REFUSAL_QUIET_SEC = 60

    def probe(self, session, host: str, channel: str):
        """그 채널에서 아직 모르는 사람에게만, 그것도 아껴서 물어본다.

        서버와 상대에게 부담을 주지 않으려고 이렇게 아낀다:
        0. 새로 들어온 사람은 **예전 기억을 버리고 다시 확인한다.** 같은 닉네임으로
           다른 프로그램을 켜고 들어올 수 있어서, 기억을 그대로 믿으면 엉뚱한 로고가
           며칠씩 붙어 있게 된다. 처음 채널에 들어가 참여자 목록을 받을 때는 해당 없음
           (그때는 저장해둔 것을 그대로 써서 조용히 시작한다)
           다만 사람이 들락거릴 때마다 요청이 나가면 채널 사람들 화면이 시끄러우므로,
           채널에 묻는 것은 일정 시간에 한 번으로 제한하고, 그 사이에 들어온 사람들은
           쿨타임이 풀리는 시점에 한 번에 확인한다(예약을 걸어둔다)
        1. **예전에 알아낸 사람은 안 묻는다** - 저장해둔 것을 그대로 쓴다
           (client_version_store, 기한이 지나면 그때 한 번 다시 물음)
        2. **지금 보고 있는 채널만** 묻는다 - 여러 채널에 들어가 있어도 한꺼번에
           수십 명에게 보내지 않는다. 다른 채널은 그 채널을 볼 때 알아본다
        3. 모르는 사람이 여럿이면 **채널에 한 줄**만 보낸다. 실측(home.pdlab.kr)에서
           개인에게 연달아 보내면 서버가 막지만("Multi-target messaging is not
           allowed"), 채널로 한 줄 보내면 전원이 답했다. 줄 수도 N개 -> 1개다
        4. 한 명뿐이면(누가 나중에 혼자 들어온 경우) 그 사람에게만 조용히 물어본다.
           한 명에게 보내는 건 실측에서도 막히지 않았고, 채널 전체를 건드릴 이유가 없다
        """
        if not app_prefs.get("show_client_badges"):
            return
        if channel != session.active_channel:
            return
        # 방금 들어온 사람은 예전 기억을 버리고 다시 확인한다
        current = set(session.members.get(channel, ()))
        previous = self._seen_members.get(channel)
        self._seen_members[channel] = current
        if previous is not None:
            for user_id in current - previous:
                if user_id == session.my_id:
                    continue
                session.forget_client_version(user_id)
                client_version_store.forget(host, user_id)
                # 새로 들어온 사람은 '이미 물어본 사람'에서도 빼야 다시 물어본다
                self._asked_in_channel.get(channel, set()).discard(user_id)

        unknown = session.unknown_client_users(channel)
        if not unknown:
            return
        remembered = client_version_store.load(host)
        ask = []
        for user_id in unknown:
            known = remembered.get(user_id)
            if known:
                session.apply_client_version(user_id, known)   # 묻지 않고 바로 표시
            else:
                ask.append(user_id)
        # 이미 한 번 물어본 사람은 답이 없어도 다시 묻지 않는다(응답을 꺼둔 사람일 수 있고,
        # 그런 사람에게 계속 묻는 건 실례이자 채널 전체에 소음이다)
        already = self._asked_in_channel.setdefault(channel, set())
        ask = [user_id for user_id in ask if user_id not in already]
        if not ask:
            return
        # 한 명뿐이고 개인에게 물어도 되는 서버면 그 사람에게만(가장 조용한 방법)
        if len(ask) == 1 and client_version_store.probe_allowed(host):
            already.update(ask)
            self._prober.enqueue(ask)
            return
        # 여럿이거나 개인 요청이 막힌 서버 - 채널에 한 줄. 다만 너무 자주 보내지 않는다
        last = self._channel_probed.get(channel, 0.0)
        remaining = self._CHANNEL_PROBE_COOLDOWN_SEC - (time.time() - last)
        if remaining > 0:
            # 지금은 참고 나중에 한 번 더 본다. 이 예약이 없으면, 쿨타임 동안 들어온
            # 사람들은 그 뒤로 아무도 들락거리지 않는 한 영영 확인되지 않는다
            # (물어보는 계기가 '참여자 목록이 바뀔 때'뿐이므로)
            self._schedule_channel_retry(channel, remaining)
            return
        self._channel_probed[channel] = time.time()
        already.update(ask)          # 이번 한 줄로 이 사람들에게는 물어본 셈이다
        session.request_client_versions_in_channel(channel)

    def _schedule_channel_retry(self, channel: str, after_sec: float):
        """쿨타임이 풀리는 시점에 한 번만 다시 살피도록 예약한다."""
        if channel in self._retry_scheduled:
            return   # 이미 예약돼 있음 - 여러 명이 몰려 들어와도 예약은 하나면 된다
        self._retry_scheduled.add(channel)

        def run():
            self._retry_scheduled.discard(channel)
            self.probe(session, host, channel)

        QTimer.singleShot(int(after_sec * 1000) + 250, run)

    def note_server_message(self, session, host: str, text: str) -> bool:
        """서버가 우리 요청을 거절하는 말이면 요청을 멈춘다.

        돌려주는 값이 True면 **그 말을 화면에 보여주지 말라**는 뜻이다. 우리가 보낸 것
        때문에 난 오류라서, 사용자에게는 우리 안내문 한 줄이면 충분하다. 서버가 참여자
        수만큼 돌려주므로 그대로 두면 경고가 줄줄이 쌓인다(실제 화면에서 확인).
        """
        if not text:
            return False
        lowered = text.lower()
        if not any(marker in lowered for marker in self._PROBE_REFUSED_MARKERS):
            return False
        recently_refused = (time.time() - self._probe_refused_at) < self._PROBE_REFUSAL_QUIET_SEC
        if not (self._prober.is_working() or recently_refused):
            return False   # 우리 때문에 난 말이 아님(그냥 서버 안내였을 수 있음)
        if recently_refused:
            return True    # 이미 알렸다 - 뒤늦게 온 답들은 조용히 버린다
        self._probe_refused_at = time.time()
        self._prober.reset()
        client_version_store.mark_probe_refused(host)
        # 왜 로고가 안 뜨는지 모르면 고장으로 보이므로 한 번은 알려준다
        self._notify(
            session.active_channel,
            "이 서버는 접속 프로그램 확인을 허용하지 않아 껐습니다. "
            "(참여자 로고는 우리 클라이언트끼리만 표시됩니다)")
        return True
