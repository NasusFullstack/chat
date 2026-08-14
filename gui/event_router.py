"""도메인 이벤트를 화면 동작으로 옮기는 곳.

예전에는 MainWindow 안에 isinstance 149줄짜리 사슬 하나로 있었다. 이벤트를 하나 추가할
때마다 그 사슬을 열어 고쳐야 했고, 어떤 이벤트가 화면의 무엇을 건드리는지 한눈에 안 보였다.
지금은 **이벤트 종류 -> 처리 함수** 표 하나로 두고, 처리 함수는 각자 짧게 둔다
(프로토콜 전략/치트 명세와 같은 규칙 - CLAUDE.md의 "if/elif 사슬 대신 표" 참고).

여기 있는 함수들은 `view`(=MainWindow)를 통해 화면을 만진다. 화면을 직접 만들거나 상태를
판단하지 않는다 - "무슨 일이 일어났는가"는 이미 코어가 판단해서 이벤트로 넘겨준 상태다.

새 이벤트를 지원하려면: 처리 함수 하나 만들고 아래 EVENT_HANDLERS에 한 줄 추가하면 끝.
표에 없는 이벤트는 조용히 무시된다(구버전 코어가 모르는 이벤트를 보내도 죽지 않게).
"""
import avatar_store
import error_log
from chat_core import events as domain_events


# ---------------- 로그인 / 계정 ----------------

def _logged_in(view, event):
    view.chat_page.my_id = event.user_id
    # 이름이 밀린 채로 들어왔으면(Mong -> Mong_) 곧바로 되찾기를 시작한다.
    # 연결 확인 타이머(15초)를 기다리면 그동안 남들에게 _ 붙은 이름으로 보인다
    if event.user_id != getattr(view.session, "wanted_nick", event.user_id):
        view.reclaim_nickname_soon()
    if view.is_reconnecting:
        view.on_reconnect_logged_in()
        return
    # 아직 로그인 단계일 때만 채널 화면으로 넘어감. IRC 닉네임 변경도 LoggedIn을
    # 발생시키는데(내 식별자가 바뀌는 건 같으므로) 그때는 이미 채팅 중이라 되돌리면 안 됨.
    # 시작화면도 '로그인 전'에 포함해야 함 - 자동로그인은 시작화면 직후에 걸린다
    if not view.is_pre_login():
        return
    view.stop_connecting()
    view.channel_page.set_mode(view.protocol_mode)
    view.show_page(view.channel_page)
    view.save_login_prefs()
    # 예전에 이 아이디로 설정해둔 아이콘을 되살림(로컬 저장분)
    view.session.restore_my_profile(avatar_store.load_avatars().get(event.user_id))


def _register_succeeded(view, event):
    view.stop_connecting()
    view.login_page.show_status("회원가입 완료! 이제 로그인하세요.", error=False)


def _auth_failed(view, event):
    view.stop_connecting()
    if view.is_reconnecting:
        # 재접속했는데 로그인이 거절됨(비번 변경/계정 삭제 등) - 다시 시도해도 소용없음
        view.cancel_reconnect()
        view.notify_all_channels(f"다시 로그인하지 못했습니다: {event.text}")
        return
    view.login_page.show_status(event.text)


def _nickname_retrying(view, event):
    view.login_page.show_status(
        f"닉네임이 사용 중이라 '{event.new_nickname}'(으)로 재시도합니다.", error=False)


def _nickname_change_failed(view, event):
    view.warn("닉네임 변경 실패", event.text)


# ---------------- 채널 ----------------

def _channel_created(view, event):
    view.channel_page.show_status("채널 생성 완료! 입장 버튼을 눌러주세요.", error=False)


def _channel_joined(view, event):
    # 이미 화면에 있는 채널로 다시 들어온 것 = 재접속 후 복구. 안내와 지난 기록을 또 쌓으면
    # 대화가 두 번 보임(입장 응답이 늦게 오므로 시간 기준 플래그로는 못 거름)
    rejoining = view.chat_page.has_channel(event.channel)
    first_time = view.current_page() is view.channel_page
    view.chat_page.add_channel(event.channel, activate=True)
    if first_time:
        view.show_page(view.chat_page)
        view.chat_page.focus_input()
    if rejoining:
        return
    view.chat_page.append_system(event.channel, event.text)
    view.chat_page.load_history(event.channel, event.history)
    # 업데이트 직후라면 무엇이 바뀌었는지 한 줄 남긴다(창을 닫아도 여기 남아 있게).
    # 나에게만 보이는 안내라 채널 사람들에게는 안 간다
    update_note = view.take_update_note()
    if update_note:
        view.chat_page.append_system(event.channel, update_note)


def _channel_join_failed(view, event):
    if view.current_page() is view.channel_page:
        view.channel_page.show_status(event.text)
    else:
        view.warn("채널 입장 실패", event.text)


def _channel_left(view, event):
    # 채널에서 빠지면 채팅이 통째로 사라지고 입력창까지 잠긴다. 내가 나가기를 누른 게
    # 아닌데 이 일이 벌어지면 원인을 알 방법이 없으므로, 그 직전에 서버가 보낸 줄들을
    # 같이 남긴다(재현이 안 되는 사고의 유일한 단서)
    error_log.log_text(
        f"채널 {event.channel}에서 빠짐. 직전 수신 내용:\n  "
        + "\n  ".join(view.recent_server_lines()[-15:]),
        tag="채널 이탈",
    )
    view.chat_page.remove_channel(event.channel)


def _channel_leave_failed(view, event):
    view.warn("채널 나가기 실패", event.text)


# ---------------- 대화 ----------------

def _message_received(view, event):
    view.chat_page.append_message(
        event.channel, event.sender, event.text, event.mine, event.ts,
        is_mention=event.is_mention, kind=event.kind,
    )
    if not event.mine:
        # 내가 보낸 건 알릴 이유가 없다. 창을 보고 있는지 판단은 창이 한다
        view.notify_new_message(event.sender, event.text, event.channel)


def _system_notice(view, event):
    # 서버가 우리 요청을 거절한 것이면 그 요청을 멈추고, 그 경고는 화면에 안 보여준다
    # (우리가 보낸 것 때문에 난 오류라 우리 안내문 한 줄로 갈음한다)
    if view.note_server_message(event.text):
        return
    if not event.channel:
        # 등록 전 NOTICE 등 - 채널이 없으면 로그인 화면 상태줄에 표시.
        # 서버가 보내는 접속 안내는 오류가 아니므로 빨간색으로 보여주면 안 됨
        if view.is_pre_login():
            view.login_page.show_status(event.text, error=False)
        return
    view.chat_page.append_system(event.channel, event.text)


def _userlist_updated(view, event):
    view.chat_page.update_userlist(event.channel, event.users)
    # 새로 보이는 사람들에게 "무슨 프로그램 쓰세요?"를 천천히 물어본다(gui/version_prober.py)
    view.probe_client_versions(event.channel)


def _client_version_updated(view, event):
    view.chat_page.set_client_version(event.user_id, event.version)
    # 다음에 켤 때는 다시 묻지 않도록 적어둔다(같은 값이면 적은 시각은 그대로 둔다)
    view.remember_client_version(event.user_id, event.version)


def _avatar_updated(view, event):
    view.chat_page.set_avatar(event.user_id, event.avatar_b64)


def _nickname_updated(view, event):
    view.chat_page.set_nickname(event.user_id, event.nickname)


# ---------------- 명령 / 치트 / 안내 ----------------

def _cheat_activated(view, event):
    # 치트별 화면 동작은 표로 두고, 모르는 치트는 조용히 무시(구버전 클라이언트가 모르는
    # 치트 문구를 받아도 죽지 않게)
    view.play_cheat(event.cheat_id)


def _cheat_blocked(view, event):
    view.chat_page.show_mention_notice(
        f"치트는 {event.remaining_sec}초 후에 다시 사용할 수 있습니다.")


def _command_help(view, event):
    view.chat_page.append_system(event.channel, "사용 가능한 명령")
    for line in event.lines:
        view.chat_page.append_system(event.channel, line)


def _command_error(view, event):
    view.chat_page.show_mention_notice(event.text)


def _mention_blocked(view, event):
    view.chat_page.show_mention_notice(
        f"@{event.target_display} 호출은 {event.remaining_sec}초 후에 다시 가능합니다.")


def _connection_closed(view, event):
    active = view.chat_page.active_channel()
    if active:
        view.chat_page.append_system(active, f"서버 연결이 종료되었습니다: {event.text}")


def _generic_error(view, event):
    if view.is_pre_login():
        view.login_page.show_status(event.text)
    elif view.current_page() is view.channel_page:
        view.channel_page.show_status(event.text)
    else:
        view.warn("오류", event.text)


# 이벤트 종류 -> 처리 함수. 새 이벤트는 여기 한 줄만 추가하면 된다
EVENT_HANDLERS = {
    domain_events.LoggedIn: _logged_in,
    domain_events.RegisterSucceeded: _register_succeeded,
    domain_events.AuthFailed: _auth_failed,
    domain_events.NicknameRetrying: _nickname_retrying,
    domain_events.NicknameChangeFailed: _nickname_change_failed,
    domain_events.ChannelCreated: _channel_created,
    domain_events.ChannelJoined: _channel_joined,
    domain_events.ChannelJoinFailed: _channel_join_failed,
    domain_events.ChannelLeft: _channel_left,
    domain_events.ChannelLeaveFailed: _channel_leave_failed,
    domain_events.MessageReceived: _message_received,
    domain_events.SystemNotice: _system_notice,
    domain_events.UserlistUpdated: _userlist_updated,
    domain_events.AvatarUpdated: _avatar_updated,
    domain_events.ClientVersionUpdated: _client_version_updated,
    domain_events.NicknameUpdated: _nickname_updated,
    domain_events.CheatActivated: _cheat_activated,
    domain_events.CheatBlocked: _cheat_blocked,
    domain_events.CommandHelp: _command_help,
    domain_events.CommandError: _command_error,
    domain_events.MentionBlocked: _mention_blocked,
    domain_events.ConnectionClosed: _connection_closed,
    domain_events.GenericError: _generic_error,
}


def route(view, event) -> bool:
    """이벤트를 알맞은 처리 함수로 보냄. 표에 없으면 아무 일도 안 하고 False."""
    handler = EVENT_HANDLERS.get(type(event))
    if handler is None:
        return False
    handler(view, event)
    return True
