/// 서버 채팅(jsserv `/chat/ws`) - 받은 사전을 보고 **무슨 일인지** 판단한다.
///
/// PC 쪽 `chat_core/protocols/server.py` 와 짝이고, 같은 답을 내야 한다. 소켓도 화면도
/// 모른다 - `core/session.dart`(IRC) 와 같은 규칙이다.
///
/// ## IRC 와 달라지는 것만 적는다
/// - **보낸 말을 서버가 돌려준다.** IRC 는 안 돌려줘서 각자 자기 말을 화면에 올려야
///   했다(로컬 에코). 여기서 또 올리면 **두 번 보인다**
/// - **아이콘·표시이름을 따로 물어보지 않는다.** 참여자 목록에 같이 온다. IRC 는
///   CTCP 로 주고받았고 아이콘은 300자씩 쪼개야 해서, 조각이 하나 빠지면 아무것도
///   안 떴다
/// - **지난 기록이 입장 응답에 실려 온다.** IRC 모드는 각자 올린 것을 중계 서버가
///   모아둔 것을 따로 받아와야 했다(`fetchMissed`)
/// - **한글 이름·긴 글·큰 아이콘이 된다.** IRC 한 줄 512바이트 제한이 없다
///
/// 메시지 종류 분기는 if/elif 사슬이 아니라 표(`_handlers`)다 - 새 종류를 지원할 때
/// 기존 코드를 안 열어도 되게. **표에 없는 종류는 조용히 버린다**(서버가 새 것을
/// 보내도 옛 앱이 죽지 않게).
library;

import 'battle_protocol.dart' as bp;
import 'chat_port.dart';
import 'events.dart';

/// 서버로 사전 하나 보내는 통로. 소켓을 여기 끌어들이지 않으려고 함수로 받는다.
typedef SendMap = void Function(Map<String, Object?> payload);

/// 서버가 받아주는 아이디·비밀번호인가. 괜찮으면 빈 글자.
///
/// **보내기 전에 막는다.** 그냥 보내면 서버가 거절하고, 그 답을 사람이 읽을 수 있는
/// 말로 바꾸는 코드가 또 필요해진다. IRC 쪽 `nickProblem()` 과 같은 자리다.
///
/// 규칙은 서버와 **같아야 한다**(jsserv `features/chat.py`):
/// 아이디 `^[A-Za-z0-9_.-]{2,24}$`, 비밀번호 4~128자.
String accountProblem(String id, String password) {
  if (id.isEmpty) return '아이디를 입력해 주세요.';
  if (!RegExp(r'^[A-Za-z0-9_.\-]{2,24}$').hasMatch(id)) {
    return '아이디는 영문·숫자 2~24자입니다. (_ . - 도 됩니다)';
  }
  if (password.length < 4) return '비밀번호는 4자 이상입니다.';
  if (password.length > 128) return '비밀번호가 너무 깁니다.';
  return '';
}

class ServerSession implements ChatPort {
  ServerSession({
    required this.send,
    required this.emit,
    required this.userId,
  });

  final SendMap send;
  final EmitEvent emit;

  /// 로그인에 쓸 아이디. 서버가 확정해주면 [myId] 가 채워진다.
  final String userId;

  @override
  String myId = '';

  /// 지금 보고 있는 채널. 서버가 채널을 안 알려주는 것(귓속말)에 쓴다.
  String activeChannel = '';

  /// 서버가 들고 있던 표시 이름. IRC 에서는 닉네임이 곧 아이디였다
  final Map<String, String> nicknames = {};

  // ------------------------------------------------------------------ 보내기
  /// 가입을 보낼 때 받은 비밀번호. **가입이 끝나면 바로 로그인에 쓴다** -
  /// 사람이 같은 것을 두 번 입력할 일이 없게
  String _madeWith = '';

  /// 계정을 만든다. **연결 하나로 가입과 로그인을 다 한다.**
  void register(String password) {
    _madeWith = password;
    send({'cmd': 'register', 'id': userId, 'pw': password});
  }

  @override
  void login({String? password, String realname = ''}) =>
      send({'cmd': 'login', 'id': userId, 'pw': password ?? ''});

  /// 들어간다. **없으면 서버가 만든다** - IRC 처럼 입장이 곧 생성이다.
  ///
  /// 이름을 다듬지 않는다. `#` 도 필요 없고 **한글도 된다** - IRC 쪽
  /// `normalizeChannel()` 이 하던 일이 여기서는 할 일이 아니다.
  @override
  void joinChannel(String name) {
    if (name.trim().isEmpty) return;
    send({'cmd': 'join', 'channel': name.trim(), 'key': ''});
  }

  @override
  void leaveChannel(String channel) =>
      send({'cmd': 'leave', 'channel': channel});

  /// 말한다. **화면에 직접 올리지 않는다** - 서버가 돌려주므로 올리면 두 번 보인다.
  ///
  /// 쪼개지도 않는다. IRC 는 한 줄 512바이트라 나눠 보내야 했다.
  @override
  void sendChat(String channel, String text) {
    if (channel.isEmpty || text.isEmpty) return;
    send({'cmd': 'msg', 'channel': channel, 'text': text});
  }

  /// 귓속말 - **IRC 에서는 기록도 안 되던 것이다.**
  void whisper(String to, String text) {
    if (to.isEmpty || text.isEmpty) return;
    send({'cmd': 'whisper', 'to': to, 'text': text});
  }

  /// 표시 이름을 바꾼다. **한글도 된다**(IRC 서버는 거절했다).
  void setNickname(String nick) => send({'cmd': 'set_nickname', 'nick': nick});

  /// 아이콘을 올린다. **쪼개지 않는다**(IRC 는 300자씩 나눠야 했다).
  void setAvatar(String avatarB64) =>
      send({'cmd': 'set_avatar', 'avatar': avatarB64});

  @override
  void announceBattleRoom(String channel, String room) {
    // CTCP 가 없으므로 채팅으로 보내되, 받는 쪽이 아래에서 걸러내 글자로는 안 보인다
    send({'cmd': 'msg', 'channel': channel, 'text': bp.formatRoomNotice(room)});
  }

  @override
  void quit([String reason = '종료']) {
    // 끊기는 즉시 서버가 알아채므로 따로 알릴 것이 없다(IRC 는 QUIT 을 보내야 했다).
  }

  // ------------------------------------------------------------------ 받기
  @override
  void handleIncoming(Object raw) {
    if (raw is! Map) return;
    final handler = _handlers[raw['type']];
    if (handler == null) return; // 모르는 종류는 조용히 버린다
    handler(this, raw);
  }

  static final Map<Object?, void Function(ServerSession, Map)> _handlers = {
    'auth_result': _onAuthResult,
    'channel_result': _onChannelResult,
    'leave_result': _onLeaveResult,
    'chat': _onChat,
    'whisper': _onWhisper,
    'system': _onSystem,
    'userlist': _onUserlist,
    'member_avatar': _onMemberAvatar,
    'member_nickname': _onMemberNickname,
    'error': _onError,
  };

  static String _text(Map msg, String key, [String fallback = '']) {
    final value = msg[key];
    return value is String ? value : fallback;
  }

  static void _onAuthResult(ServerSession s, Map msg) {
    if (msg['ok'] != true) {
      // 화면이 기다리고 있으므로 **끝났다고 알려야 한다** - 안 알리면 로그인 버튼이
      // 영원히 돌아간다. 끊긴 것과는 **다른 일**로 알린다 - 같은 것으로 쓰면
      // 비밀번호가 틀렸을 때도 "연결이 종료되었습니다"가 뜬다
      s.emit(AuthFailed(_text(msg, 'text', '아이디나 비밀번호가 다릅니다')));
      return;
    }
    if (msg['made'] == true) {
      // 가입만 된 것이다. **이어서 로그인을 보낸다** - 사람이 두 번 누를 일이 없게.
      // 화면은 아직 기다리는 중이고, 곧 올 두 번째 auth_result 로 끝난다
      s.login(password: s._madeWith);
      s._madeWith = '';
      return;
    }
    s.myId = _text(msg, 'id', s.userId);
    // 서버가 들고 있던 내 이름과 아이콘이 따라온다 - 기기를 바꿔도 그대로다
    final nick = _text(msg, 'nick');
    if (nick.isNotEmpty) {
      s.nicknames[s.myId] = nick;
      s.emit(NicknameUpdated(s.myId, nick));
    }
    final avatar = _text(msg, 'avatar');
    if (avatar.isNotEmpty) s.emit(AvatarUpdated(s.myId, avatar));
    s.emit(LoggedIn(s.myId));
  }

  static void _onChannelResult(ServerSession s, Map msg) {
    final channel = _text(msg, 'channel');
    if (msg['ok'] != true) {
      s.emit(ChannelJoinFailed(channel, _text(msg, 'text', '입장에 실패했습니다.')));
      return;
    }
    s.activeChannel = channel;
    s.emit(ChannelJoined(channel, _text(msg, 'text', '입장 완료')));
    // **지난 기록이 응답에 실려 온다.** 중계 서버에 따로 받아올 것이 없다
    final history = msg['history'];
    if (history is List) {
      for (final line in history) {
        if (line is! Map) continue;
        final sender = _text(line, 'sender', '?');
        s.emit(MessageReceived(
          channel: channel,
          sender: sender,
          text: _text(line, 'text'),
          mine: sender == s.myId,
        ));
      }
    }
    _applyUsers(s, channel, msg['users']);
  }

  static void _onLeaveResult(ServerSession s, Map msg) {
    final channel = _text(msg, 'channel');
    if (msg['ok'] == true) {
      s.emit(ChannelLeft(channel));
    } else {
      s.emit(SystemNotice(channel, _text(msg, 'text', '나가지 못했습니다.')));
    }
  }

  static void _onChat(ServerSession s, Map msg) {
    final sender = _text(msg, 'sender', '?');
    final channel = _text(msg, 'channel');
    final text = _text(msg, 'text');
    // 우리끼리 쓰는 숨김 프레임은 **채팅으로 새면 안 된다**(CLAUDE.md 2-2).
    // 예전에 잘린 base64 가 채널에 쓰레기로 쏟아진 적이 있다
    if (bp.isBattleNotice(text)) {
      final room = bp.parseRoomNotice(text);
      if (room.isNotEmpty && sender != s.myId && channel.isNotEmpty) {
        s.emit(BattleRoomOpened(channel, sender, room));
      }
      return;
    }
    s.emit(MessageReceived(
      channel: channel,
      sender: sender,
      text: text,
      mine: sender == s.myId,
      isMention: _mentionsMe(s, text),
    ));
  }

  static void _onWhisper(ServerSession s, Map msg) {
    // 보이는 자리는 지금 보고 있는 채널이다. 받는 쪽과 보내는 쪽이 같은 자리에 남아야
    // 대화가 이어져 보인다
    final channel = s.activeChannel;
    if (channel.isEmpty) return;
    final sender = _text(msg, 'sender', '?');
    final mine = sender == s.myId;
    final who = mine ? _text(msg, 'to') : sender;
    s.emit(MessageReceived(
      channel: channel,
      sender: '$who (귓속말)',
      text: _text(msg, 'text'),
      mine: mine,
    ));
  }

  static void _onSystem(ServerSession s, Map msg) {
    final channel = _text(msg, 'channel').isEmpty
        ? s.activeChannel
        : _text(msg, 'channel');
    if (channel.isEmpty) return;
    s.emit(SystemNotice(channel, _text(msg, 'text'), hasTime: true));
  }

  static void _onUserlist(ServerSession s, Map msg) {
    final channel = _text(msg, 'channel').isEmpty
        ? s.activeChannel
        : _text(msg, 'channel');
    if (channel.isEmpty) return;
    _applyUsers(s, channel, msg['users']);
  }

  /// 참여자 목록 - **아이콘과 표시 이름이 같이 온다.**
  ///
  /// IRC 는 아이디만 와서 나머지를 CTCP 로 따로 물어야 했고, 그 과정에서 서버가
  /// 폭주로 보고 끊는 일이 있었다. 여기서는 받은 것을 그대로 쓴다 - 요청 0줄.
  static void _applyUsers(ServerSession s, String channel, Object? users) {
    if (users is! List) return;
    final ids = <String>[];
    for (final one in users) {
      if (one is! Map) continue;
      final id = _text(one, 'id');
      if (id.isEmpty) continue;
      ids.add(id);
      final nick = _text(one, 'nick');
      if (nick.isNotEmpty && s.nicknames[id] != nick) {
        s.nicknames[id] = nick;
        s.emit(NicknameUpdated(id, nick));
      }
      final avatar = _text(one, 'avatar');
      if (avatar.isNotEmpty) s.emit(AvatarUpdated(id, avatar));
    }
    s.emit(UserlistUpdated(channel, ids));
  }

  static void _onMemberAvatar(ServerSession s, Map msg) {
    final id = _text(msg, 'id');
    if (id.isNotEmpty) s.emit(AvatarUpdated(id, _text(msg, 'avatar')));
  }

  static void _onMemberNickname(ServerSession s, Map msg) {
    final id = _text(msg, 'id');
    final nick = _text(msg, 'nick');
    if (id.isEmpty || nick.isEmpty) return;
    s.nicknames[id] = nick;
    s.emit(NicknameUpdated(id, nick));
  }

  static void _onError(ServerSession s, Map msg) {
    final where = s.activeChannel;
    if (where.isEmpty) return;
    s.emit(SystemNotice(where, _text(msg, 'text', '오류')));
  }

  /// 내 이름이 불렸는가. 표시 이름으로 불릴 수도 있다
  static bool _mentionsMe(ServerSession s, String text) {
    if (s.myId.isEmpty) return false;
    final lower = text.toLowerCase();
    if (lower.contains('@${s.myId.toLowerCase()}')) return true;
    final nick = s.nicknames[s.myId];
    return nick != null && nick.isNotEmpty && text.contains('@$nick');
  }
}
