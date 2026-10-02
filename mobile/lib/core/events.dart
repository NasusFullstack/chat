/// 무슨 일이 일어났는가 - 상태 판단이 화면에 알리는 것들.
///
/// PC 앱 `chat_core/events.py`를 옮긴 것이다. 화면은 이것만 보고 그리고,
/// "무슨 일인지"는 절대 스스로 판단하지 않는다(PC 앱과 같은 규칙).
///
/// `toMap()`은 검사용이다 - 파이썬이 내놓은 이벤트와 하나하나 맞춰보려면 비교할 수 있는
/// 모양이어야 한다(`test/session_test.dart`).
library;

/// 이벤트를 받는 곳. 판단하는 쪽은 화면도 상태도 모른 채 이 함수만 부른다.
///
/// **여기 있는 이유**: 예전에는 `core/session.dart`(IRC) 안에 있었는데, 그러면 서버
/// 채팅 판단이 IRC 파일을 가져다 써야 한다. 이벤트와 같은 자리가 맞다.
typedef EmitEvent = void Function(ChatEvent event);

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

/// 채널에 전투 방이 열렸다 - "이 방으로 와라".
///
/// **주소는 안 실린다.** 방 번호만 오고, 중계 서버 주소는 각자 안다. 번호를 모르면
/// 들어갈 수 없으므로 아무나 끼어들지 못한다.
class BattleRoomOpened extends ChatEvent {
  const BattleRoomOpened(this.channel, this.host, this.room);

  final String channel;

  /// 방을 연 사람
  final String host;

  /// 방 번호
  final String room;

  @override
  String get type => 'BattleRoomOpened';

  @override
  Map<String, Object?> toMap() =>
      {'type': type, 'channel': channel, 'host': host, 'room': room};
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

/// 누군가의 **표시 이름**을 알게 됐다.
///
/// 서버 채팅에서만 나온다. IRC 는 닉네임이 곧 아이디였지만(한글도 못 썼다), 서버
/// 채팅은 아이디와 보이는 이름이 따로다 - 참여자 목록에 같이 실려 온다.
class NicknameUpdated extends ChatEvent {
  const NicknameUpdated(this.userId, this.nickname);

  final String userId;
  final String nickname;

  @override
  String get type => 'NicknameUpdated';

  @override
  Map<String, Object?> toMap() =>
      {'type': type, 'user_id': userId, 'nickname': nickname};
}

/// 누군가의 아이콘을 알게 됐다.
///
/// 서버 채팅에서만 나온다. **참여자 목록에 같이 오므로 따로 물어볼 것이 없다** -
/// IRC 는 CTCP 로 300자씩 쪼개 주고받아야 했고 조각이 하나 빠지면 아무것도 안 떴다.
class AvatarUpdated extends ChatEvent {
  const AvatarUpdated(this.userId, this.avatar);

  final String userId;

  /// base64 PNG. 빈 값이면 "지웠다"는 뜻이다
  final String avatar;

  @override
  String get type => 'AvatarUpdated';

  @override
  Map<String, Object?> toMap() =>
      {'type': type, 'user_id': userId, 'avatar': avatar};
}

/// 들어가지 못했다 - 아이디나 비밀번호가 틀렸거나 서버가 거절했다.
///
/// 끊긴 것(`ConnectionClosed`)과 **나눠 둔다.** 둘을 같은 것으로 쓰면 비밀번호가
/// 틀렸을 때도 "연결이 종료되었습니다"가 뜨는데, 그건 사람이 읽고 무엇을 해야 할지
/// 알 수 없는 말이다.
class AuthFailed extends ChatEvent {
  const AuthFailed(this.text);

  final String text;

  @override
  String get type => 'AuthFailed';

  @override
  Map<String, Object?> toMap() => {'type': type, 'text': text};
}

/// 서버에 있는 방 하나.
class RoomInfo {
  const RoomInfo({
    required this.name,
    this.users = 0,
    this.locked = false,
  });

  final String name;

  /// 지금 그 방에 있는 사람 수. 0이어도 방과 기록은 남아 있다
  final int users;

  /// 비밀번호가 걸렸는가. **비밀번호 자체는 서버가 안 보낸다** - 걸렸다는 사실만 온다
  final bool locked;

  static RoomInfo? fromJson(Object? raw) {
    if (raw is! Map) return null;
    final name = raw['name'];
    if (name is! String || name.isEmpty) return null;
    final users = raw['users'];
    return RoomInfo(
      name: name,
      users: users is num ? users.toInt() : 0,
      locked: raw['locked'] == true,
    );
  }
}

/// 서버에 어떤 방이 있는지 받았다.
class RoomListReceived extends ChatEvent {
  const RoomListReceived(this.rooms);

  final List<RoomInfo> rooms;

  @override
  String get type => 'RoomListReceived';

  @override
  Map<String, Object?> toMap() => {
        'type': type,
        'rooms': [
          for (final one in rooms)
            {'name': one.name, 'users': one.users, 'locked': one.locked}
        ],
      };
}
