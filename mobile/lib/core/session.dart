/// 받은 줄을 보고 **무슨 일이 일어났는지** 판단한다. 화면도 소켓도 모른다.
///
/// PC 앱의 `chat_core/session.py` + `chat_core/protocols/irc.py`를 명세서로 읽고
/// 채팅에 필요한 만큼 옮긴 것이다. 화면은 여기서 나온 이벤트만 보고 그린다 -
/// "무슨 일인지"를 화면이 또 판단하면 PC와 모바일이 서로 다르게 해석하게 된다.
///
/// 여기 담긴 규칙 몇 개는 **실제 사고에서 나온 것**이라 지워서는 안 된다.
/// 각각 주석에 이유를 적어뒀다.
library;

import 'events.dart';
import 'battle_protocol.dart' as bp;
import 'irc_protocol.dart';

/// 서버로 한 줄 보내는 통로. 소켓을 여기 끌어들이지 않으려고 함수로 받는다.
typedef SendLine = void Function(String line);

typedef EmitEvent = void Function(ChatEvent event);

class ChatSession {
  ChatSession({
    required this.send,
    required this.emit,
    required this.wantedNick,
    this.appVersion = '0.0.0',
  });


  final SendLine send;
  final EmitEvent emit;

  /// 서버가 확정해준 내 이름. 접속 전에는 비어 있다.
  String myId = '';

  /// 내가 쓰려던 이름. 밀리면 여기에 `_`를 붙여 다시 시도한다.
  String wantedNick;

  /// 지금 앱 버전. "무슨 프로그램 쓰세요?"에 답할 때 같이 알려준다
  final String appVersion;

  int _nickTries = 0;

  /// 채널마다 지금 누가 있는가.
  final Map<String, Set<String>> members = {};

  /// 지금 보고 있는 채널(서버가 채널을 안 알려주는 경우에 쓴다).
  String activeChannel = '';

  /// 353은 여러 줄로 쪼개져 오므로 모아뒀다가 366에서 한 번에 확정한다.
  final Map<String, List<String>> _namesBuffer = {};

  // ------------------------------------------------------------------ 보내기
  void login({String? password, String realname = ''}) {
    if (password != null && password.isNotEmpty) {
      send(formatPass(password));
    }
    send(formatNick(wantedNick));
    send(formatUser(wantedNick, realname.isEmpty ? wantedNick : realname));
  }

  void joinChannel(String name) {
    final channel = normalizeChannel(name);
    if (channel.isEmpty) return;
    send(formatJoin(channel));
  }

  void leaveChannel(String channel) => send(formatPart(channel));

  /// 한 줄 보낸다. 긴 글은 나눠 보내고, **보낸 것은 내가 직접 화면에 올린다**.
  ///
  /// IRC 서버는 내가 보낸 말을 나에게 되돌려주지 않는다. 그래서 여기서 올리지 않으면
  /// 내 말만 화면에 안 보인다(PC 앱의 `IrcProtocol.send_chat`과 같은 이유).
  void sendChat(String channel, String text) {
    if (channel.isEmpty || text.isEmpty) return;
    for (final piece in splitMessage(text)) {
      send(formatPrivmsg(channel, piece));
      emit(MessageReceived(
        channel: channel,
        sender: myId,
        text: piece,
        mine: true,
      ));
    }
  }

  void quit([String reason = '종료']) => send(formatQuit(reason));

  // ------------------------------------------------------------------ 받기
  void handleLine(String raw) {
    final msg = parseLine(raw);
    final handler = _handlers[msg.command];
    if (handler != null) {
      handler(this, msg);
      return;
    }
    if (nickCollisionNumerics.contains(msg.command)) {
      _onNickCollision(this, msg);
    } else if (channelJoinErrorNumerics.contains(msg.command)) {
      emit(ChannelJoinFailed(
          '', msg.trailing.isEmpty ? '채널 입장에 실패했습니다.' : msg.trailing));
    } else if (_isReportableNumeric(msg.command)) {
      // 명령을 보냈는데 답이 화면에 하나도 안 뜨면 먹통처럼 보인다.
      // 그래서 4xx/5xx 와 몇몇 안내 응답은 그대로 보여준다
      emit(SystemNotice(activeChannel, _numericText(msg)));
    }
  }

  static bool _isReportableNumeric(String command) {
    final n = int.tryParse(command);
    return n != null && n >= 400 && n <= 599;
  }

  static String _numericText(IrcMessage msg) {
    // 숫자 응답은 첫 칸이 항상 내 닉네임이라 빼고 나머지를 이어 붙인다
    final parts = msg.params.skip(1).where((p) => p.isNotEmpty).toList();
    return parts.isEmpty ? msg.raw.trim() : parts.join(' ');
  }

  static final Map<String, void Function(ChatSession, IrcMessage)> _handlers = {
    'PING': _onPing,
    rplWelcome: _onWelcome,
    rplNamReply: _onNamReply,
    rplEndOfNames: _onEndOfNames,
    'JOIN': _onJoin,
    'PART': _onPart,
    'QUIT': _onQuit,
    'NICK': _onNick,
    'PRIVMSG': _onPrivmsg,
    'NOTICE': _onNotice,
    'ERROR': _onError,
  };

  static void _onPing(ChatSession s, IrcMessage msg) {
    s.send(formatPong(msg.trailing));
  }

  static void _onWelcome(ChatSession s, IrcMessage msg) {
    // 서버가 **실제로 확정한 이름**을 001 첫 칸으로 알려준다. 길이 제한이나 치환 때문에
    // 우리가 보낸 것과 다를 수 있어서, 우리 값을 그냥 쓰면 엉뚱한 이름이 남는다
    s.myId = msg.params.isNotEmpty ? msg.params.first : s.wantedNick;
    s.emit(LoggedIn(s.myId));
  }

  static void _onNickCollision(ChatSession s, IrcMessage msg) {
    s._nickTries += 1;
    if (s._nickTries > maxNickRetries) {
      s.emit(SystemNotice('', '닉네임을 정하지 못했습니다: ${msg.trailing}'));
      return;
    }
    s.wantedNick = '${s.wantedNick}_';
    s.emit(NicknameRetrying(s.wantedNick));
    s.send(formatNick(s.wantedNick));
  }

  static void _onNamReply(ChatSession s, IrcMessage msg) {
    final channel = msg.params.length > 2 ? msg.params[2] : '';
    s._namesBuffer.putIfAbsent(channel, () => []).addAll(parseNamesReply(msg));
  }

  static void _onEndOfNames(ChatSession s, IrcMessage msg) {
    final channel = msg.params.length > 1 ? msg.params[1] : '';
    final found = s._namesBuffer.remove(channel) ?? const <String>[];
    if (found.isEmpty) {
      // **빈 목록은 반영하지 않는다.** 353 없이 366만 오는 경우가 있는데(요청이 겹치거나
      // 다른 데서 NAMES를 부르거나), 그걸 그대로 쓰면 참여자 목록이 통째로 비어버린다.
      // PC 앱에서 "참여자가 다 사라져서 빈 공간으로 보인다"는 제보의 원인이었다.
      // 내가 들어가 있는 채널이 빈 목록일 수는 없다 - 최소한 내가 있다
      return;
    }
    s.members[channel] = found.toSet();
    s.emit(UserlistUpdated(channel, s._sortedMembers(channel)));
  }

  static void _onJoin(ChatSession s, IrcMessage msg) {
    final nick = msg.sourceNick;
    final channel =
        msg.trailing.isNotEmpty ? msg.trailing : (msg.params.isNotEmpty ? msg.params.first : '');
    s._addMember(channel, nick);
    if (nick == s.myId) {
      s.activeChannel = channel;
      s.emit(ChannelJoined(channel, '$channel 입장 완료'));
      s.send(formatNames(channel));
    } else {
      s.emit(SystemNotice(channel, '$nick님이 입장했습니다.', hasTime: true));
    }
  }

  static void _onPart(ChatSession s, IrcMessage msg) {
    final nick = msg.sourceNick;
    final channel = msg.params.isNotEmpty ? msg.params.first : '';
    s._removeMember(channel, nick);
    s.emit(SystemNotice(channel, '$nick님이 나갔습니다.', hasTime: true));
    if (nick == s.myId) {
      s.members.remove(channel);
      s.emit(ChannelLeft(channel));
    }
  }

  static void _onQuit(ChatSession s, IrcMessage msg) {
    // QUIT은 채널 정보가 없다. 그 사람이 있던 **모든 채널**에 반영해야 한다
    final nick = msg.sourceNick;
    for (final channel in s.members.keys.toList()) {
      if (s.members[channel]?.contains(nick) ?? false) {
        s._removeMember(channel, nick);
        s.emit(SystemNotice(channel, '$nick님이 접속을 종료했습니다.', hasTime: true));
      }
    }
  }

  static void _onNick(ChatSession s, IrcMessage msg) {
    final oldNick = msg.sourceNick;
    final newNick =
        msg.trailing.isNotEmpty ? msg.trailing : (msg.params.isNotEmpty ? msg.params.first : '');
    if (oldNick == s.myId) {
      s.myId = newNick;
      s.wantedNick = newNick;
      s.emit(LoggedIn(newNick));
    }
    for (final channel in s.members.keys.toList()) {
      final set = s.members[channel]!;
      if (set.remove(oldNick)) {
        set.add(newNick);
        s.emit(UserlistUpdated(channel, s._sortedMembers(channel)));
        s.emit(SystemNotice(channel, '$oldNick님이 $newNick(으)로 이름을 바꿨습니다.',
            hasTime: true));
      }
    }
  }

  static void _onPrivmsg(ChatSession s, IrcMessage msg) {
    final target = msg.params.isNotEmpty ? msg.params.first : '';
    final text = msg.trailing;
    if (isVersionRequest(text)) {
      // "무슨 프로그램 쓰세요?" - 답해야 상대 화면에 춥채팅 + 폰으로 보인다.
      // 사람에게는 아무것도 안 보여준다(기계끼리 주고받는 것이다)
      s.send(formatVersionReply(msg.sourceNick, ourClientVersion(s.appVersion)));
      return;
    }
    if (isCtcpFrame(text)) {
      // 전투 방 알림이면 알려준다 - 이걸 못 알아들으면 폰에서는 전투에 아예 못 들어간다.
      // **방 번호 모양을 먼저 검사한다** - 다른 클라이언트가 흉내낸 값일 수 있다
      final room = bp.parseRoomNotice(text);
      if (room.isNotEmpty && msg.sourceNick != s.myId) {
        final where = target.startsWith('#') ? target : s.activeChannel;
        if (where.isNotEmpty) {
          s.emit(BattleRoomOpened(where, msg.sourceNick, room));
        }
        return;
      }
      // **해석 못 해도 채팅으로 흘리지 않는다.** PC 앱에서 잘린 base64 483자가
      // 채널에 그대로 쏟아진 사고가 있었다. 모르는 프레임은 조용히 버린다
      return;
    }
    final isWhisper = !target.startsWith('#') && !target.startsWith('&');
    final channel = isWhisper ? s.activeChannel : target;
    final sender = isWhisper ? '${msg.sourceNick} (귓속말)' : msg.sourceNick;
    s.emit(MessageReceived(
      channel: channel,
      sender: sender,
      text: text,
      mine: false,
      isMention: s.myId.isNotEmpty && text.contains('@${s.myId}'),
    ));
  }

  static void _onNotice(ChatSession s, IrcMessage msg) {
    final text = msg.trailing;
    if (isCtcpFrame(text)) {
      // 기계끼리 주고받는 답(CTCP VERSION 응답 등)은 사람에게 보이면 안 된다
      return;
    }
    final target = msg.params.isNotEmpty ? msg.params.first : '';
    final channel = target.startsWith('#') ? target : s.activeChannel;
    s.emit(SystemNotice(channel, text));
  }

  static void _onError(ChatSession s, IrcMessage msg) {
    s.emit(ConnectionClosed(msg.trailing));
  }

  /// 참여자가 하나 늘었다. **바로 알린다** - 알리는 시점이 곳곳으로 갈라지면
  /// 화면에 뜨는 차례가 PC와 달라진다(파이썬도 add_member 안에서 바로 알린다).
  void _addMember(String channel, String nick) {
    members.putIfAbsent(channel, () => <String>{}).add(nick);
    emit(UserlistUpdated(channel, _sortedMembers(channel)));
  }

  void _removeMember(String channel, String nick) {
    members[channel]?.remove(nick);
    emit(UserlistUpdated(channel, _sortedMembers(channel)));
  }

  List<String> _sortedMembers(String channel) {
    final list = (members[channel] ?? const <String>{}).toList();
    list.sort();
    return list;
  }
}
