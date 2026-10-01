/// 무슨 일이 일어났는가 - 상태 판단이 화면에 알리는 것들.
///
/// PC 앱 `chat_core/events.py`를 옮긴 것이다. 화면은 이것만 보고 그리고,
/// "무슨 일인지"는 절대 스스로 판단하지 않는다(PC 앱과 같은 규칙).
///
/// `toMap()`은 검사용이다 - 파이썬이 내놓은 이벤트와 하나하나 맞춰보려면 비교할 수 있는
/// 모양이어야 한다(`test/session_test.dart`).
library;

abstract class ChatEvent {
  const ChatEvent();

  String get type;

  Map<String, Object?> toMap();
}

/// 접속이 확정됐다(IRC는 001 응답).
class LoggedIn extends ChatEvent {
  const LoggedIn(this.userId);

  final String userId;

  @override
  String get type => 'LoggedIn';

  @override
  Map<String, Object?> toMap() => {'type': type, 'user_id': userId};
}

/// 채널에 들어갔다.
class ChannelJoined extends ChatEvent {
  const ChannelJoined(this.channel, this.text);

  final String channel;
  final String text;

  @override
  String get type => 'ChannelJoined';

  @override
  Map<String, Object?> toMap() =>
      {'type': type, 'channel': channel, 'text': text};
}

/// 채널에서 빠졌다(내가 나갔을 때).
class ChannelLeft extends ChatEvent {
  const ChannelLeft(this.channel);

  final String channel;

  @override
  String get type => 'ChannelLeft';

  @override
  Map<String, Object?> toMap() => {'type': type, 'channel': channel};
}

/// 채널에 못 들어갔다.
class ChannelJoinFailed extends ChatEvent {
  const ChannelJoinFailed(this.channel, this.text);

  final String channel;
  final String text;

  @override
  String get type => 'ChannelJoinFailed';

  @override
  Map<String, Object?> toMap() =>
      {'type': type, 'channel': channel, 'text': text};
}

/// 누가 무슨 말을 했다.
class MessageReceived extends ChatEvent {
  const MessageReceived({
    required this.channel,
    required this.sender,
    required this.text,
    required this.mine,
    this.isMention = false,
    this.kind = 'chat',
  });

  final String channel;
  final String sender;
  final String text;
  final bool mine;
  final bool isMention;

  /// `action`(/me) · `notice`(/notice) · `chat`. 종류 판정은 여기서 하고
  /// 화면은 그리기만 한다.
  final String kind;

  @override
  String get type => 'MessageReceived';

  @override
  Map<String, Object?> toMap() => {
        'type': type,
        'channel': channel,
        'sender': sender,
        'text': text,
        'mine': mine,
        'is_mention': isMention,
        'kind': kind,
      };
}

/// 사람이 아니라 상황을 알리는 한 줄(입장·퇴장·서버 안내).
class SystemNotice extends ChatEvent {
  const SystemNotice(this.channel, this.text, {this.hasTime = false});

  final String channel;
  final String text;

  /// 시각을 붙일 일인가. 사람이 오간 알림에만 붙고 안내문에는 안 붙는다
  /// (붙일지 말지는 "무슨 일인지" 아는 쪽이 정한다 - PC와 같은 규칙).
  final bool hasTime;

  @override
  String get type => 'SystemNotice';

  @override
  Map<String, Object?> toMap() =>
      {'type': type, 'channel': channel, 'text': text, 'has_time': hasTime};
}

/// 참여자 목록이 바뀌었다.
class UserlistUpdated extends ChatEvent {
  const UserlistUpdated(this.channel, this.users);

  final String channel;
  final List<String> users;

  @override
  String get type => 'UserlistUpdated';

  @override
  Map<String, Object?> toMap() =>
      {'type': type, 'channel': channel, 'users': users};
}

/// 닉네임이 밀려서 다시 시도하는 중.
class NicknameRetrying extends ChatEvent {
  const NicknameRetrying(this.newNickname);

  final String newNickname;

  @override
  String get type => 'NicknameRetrying';

  @override
  Map<String, Object?> toMap() => {'type': type, 'new_nickname': newNickname};
}

/// 접속이 끊겼다.
class ConnectionClosed extends ChatEvent {
  const ConnectionClosed(this.text);

  final String text;

  @override
  String get type => 'ConnectionClosed';

  @override
  Map<String, Object?> toMap() => {'type': type, 'text': text};
}
