/// 지난번 접속을 기억한다 - 이름, 서버, 그리고 **들어가 있던 채널**.
///
/// ## 왜
/// 폰에서 글자를 치는 것은 PC보다 훨씬 번거롭다. 앱을 켤 때마다 이름과 서버 주소를
/// 다시 치게 하면 그것만으로 안 쓰게 된다. PC 앱이 로그인 정보를 기억하는 것과 같다.
///
/// ## IRC 와 서버 채팅은 **따로 기억한다**
/// 둘은 이름 체계가 아예 다르다 - IRC 는 닉네임만 있고, 서버 채팅은 아이디와 비밀번호가
/// 있는 계정이다. 한 칸에 같이 적어두면 IRC 로 들어갔다가 서버 채팅으로 바꿀 때 엉뚱한
/// 이름이 들어가 있고, 그걸 그대로 보내면 로그인이 실패한다. 그래서 열쇠에 어느 쪽인지를
/// 넣는다(`login_irc_nick` / `login_server_nick`).
///
/// **옛 열쇠(`login_nick` 등)는 IRC 쪽에서 그대로 읽는다.** 이미 깔려 있는 앱이
/// 기억해둔 이름을 잃어버리면 안 된다(v2.6.8 까지는 열쇠가 하나였다).
///
/// ## 채널은 이름마다 따로 기억한다
/// 같은 폰을 두 이름으로 쓸 수 있다. 한 이름으로 들어갔던 방을 다른 이름으로 켤 때
/// 멋대로 들어가면 안 된다 - 그래서 열쇠에 서버와 이름을 같이 넣는다. 자리 계산에
/// 프로토콜이 들어가므로 IRC 방과 서버 채팅 방은 **저절로** 갈린다.
///
/// 비밀번호는 **적어두지 않는다.** 기기에 평문으로 남길 이유가 없다 - 서버 채팅
/// 비밀번호도 마찬가지다(그래서 서버 채팅은 켤 때마다 비밀번호를 받는다).
library;

import 'package:shared_preferences/shared_preferences.dart';

import 'core/chat_port.dart';
import 'core/relay.dart' as relay;

/// 기억해둔 접속 정보.
class LastLogin {
  /// 주소·포트는 **비어서 시작한다**(0 = 안 적힘). 채워지는 것은 이 기기에
  /// 저장해둔 것뿐이다 - 미리 박아두면 다른 서버를 쓰는 사람이 매번 지우고 다시 친다
  const LastLogin({
    this.kind = ChatKind.irc,
    this.host = '',
    this.port = 0,
    this.nick = '',
    this.secure = true,
    this.remember = true,
    this.auto = true,
  });

  /// IRC 였나 서버 채팅이었나
  final ChatKind kind;

  final String host;
  final int port;

  /// IRC 면 닉네임, 서버 채팅이면 아이디
  final String nick;

  final bool secure;

  /// 이름을 기억해 둘까. 끄면 적어둔 이름을 지운다
  final bool remember;

  /// 켜면 앱을 켤 때 **알아서** 들어간다. 이름이 기억되어 있어야 의미가 있다
  final bool auto;

  /// 알아서 들어갈 수 있는 상태인가.
  ///
  /// **서버 채팅은 알아서 들어갈 수 없다** - 비밀번호를 기기에 안 남기기 때문이다.
  /// 이름은 채워주되 비밀번호는 사람이 쳐야 한다.
  bool get canAuto =>
      auto && remember && nick.isNotEmpty && kind == ChatKind.irc;

  /// 한 군데만 고친 새 값(나머지는 그대로).
  LastLogin copyWith({bool? remember, bool? auto}) => LastLogin(
        kind: kind,
        host: host,
        port: port,
        nick: nick,
        secure: secure,
        remember: remember ?? this.remember,
        auto: auto ?? this.auto,
      );
}

/// 어느 쪽 설정인지를 열쇠에 넣는다.
String _key(ChatKind kind, String name) => 'login_${kind.wireName}_$name';

/// 지난번에 어느 쪽으로 들어갔나. 로그인 화면이 그쪽을 먼저 보여준다
Future<ChatKind> loadLastKind() async {
  try {
    final store = await SharedPreferences.getInstance();
    return store.getString('login_kind') == ChatKind.server.wireName
        ? ChatKind.server
        : ChatKind.irc;
  } on Object {
    return ChatKind.irc;
  }
}

/// 그쪽의 지난번 접속을 읽어온다. 없으면 기본값.
Future<LastLogin> loadLastLogin([ChatKind kind = ChatKind.irc]) async {
  try {
    final store = await SharedPreferences.getInstance();
    // IRC 는 옛 열쇠를 **되읽는다.** 이미 깔려 있는 앱이 기억해둔 이름을 잃지 않게
    String? text(String name) =>
        store.getString(_key(kind, name)) ??
        (kind == ChatKind.irc ? store.getString('login_$name') : null);
    bool? flag(String name) =>
        store.getBool(_key(kind, name)) ??
        (kind == ChatKind.irc ? store.getBool('login_$name') : null);

    if (kind == ChatKind.server) {
      return LastLogin(
        kind: kind,
        host: relay.serverChatHost,
        port: relay.serverChatPort,
        nick: text('nick') ?? '',
        remember: flag('remember') ?? true,
        // 서버 채팅은 비밀번호를 안 남기므로 알아서 들어갈 수 없다
        auto: false,
      );
    }
    return LastLogin(
      kind: kind,
      host: text('host') ?? '',
      port: store.getInt(_key(kind, 'port')) ??
          store.getInt('login_port') ??
          0,
      nick: text('nick') ?? '',
      secure: flag('secure') ?? true,
      remember: flag('remember') ?? true,
      auto: flag('auto') ?? true,
    );
  } on Object {
    // 못 읽어도 로그인 화면은 떠야 한다
    return LastLogin(kind: kind);
  }
}

/// 이번 접속을 기억한다. **로그인이 성공한 뒤에만** 부른다 - 실패한 이름을
/// 기억해두면 다음에도 같은 실패로 시작한다.
///
/// [remember]가 꺼져 있으면 서버 주소만 남기고 **이름은 지운다.** 남의 폰을 잠깐
/// 쓰거나 둘이 번갈아 쓰는 경우에 이름이 남아 있으면 안 된다.
Future<void> saveLastLogin({
  required String host,
  required int port,
  required String nick,
  required bool secure,
  ChatKind kind = ChatKind.irc,
  bool remember = true,
  bool auto = true,
}) async {
  try {
    final store = await SharedPreferences.getInstance();
    // 다음에 켤 때 **같은 쪽**을 먼저 보여준다
    await store.setString('login_kind', kind.wireName);
    await store.setString(_key(kind, 'host'), host);
    await store.setInt(_key(kind, 'port'), port);
    await store.setString(_key(kind, 'nick'), remember ? nick : '');
    await store.setBool(_key(kind, 'secure'), secure);
    await store.setBool(_key(kind, 'remember'), remember);
    await store.setBool(_key(kind, 'auto'), auto);
  } on Object {
    // 못 적어도 이번 접속은 되어 있다
  }
}

/// 자동으로 들어갈지를 바꾼다(설정 화면).
Future<void> saveAutoLogin(bool on, [ChatKind kind = ChatKind.irc]) async {
  try {
    final store = await SharedPreferences.getInstance();
    await store.setBool(_key(kind, 'auto'), on);
  } on Object {
    // 다음 실행에 반영이 안 될 뿐이다
  }
}

/// 채널 목록을 적어두는 열쇠. 서버와 이름이 같이 들어간다.
///
/// 자리 계산에 프로토콜이 들어가므로 **IRC 방과 서버 채팅 방은 저절로 갈린다**.
/// IRC 쪽 열쇠는 예전과 **글자 그대로 같다** - 이미 적어둔 채널 목록을 잃지 않는다.
String _roomsKey(ChatKind kind, String host, int port, String nick) =>
    'rooms_${relay.groupId(kind.wireName, host, port)}_${nick.toLowerCase()}';

/// 이 이름으로 들어가 있던 채널들.
Future<List<String>> loadRooms(String host, int port, String nick,
    {ChatKind kind = ChatKind.irc}) async {
  if (nick.isEmpty) return const [];
  try {
    final store = await SharedPreferences.getInstance();
    return store.getStringList(_roomsKey(kind, host, port, nick)) ?? const [];
  } on Object {
    return const [];
  }
}

/// 들어가 있는 채널을 적어둔다. 들어가고 나갈 때마다 부른다.
Future<void> saveRooms(String host, int port, String nick, List<String> rooms,
    {ChatKind kind = ChatKind.irc}) async {
  if (nick.isEmpty) return;
  try {
    final store = await SharedPreferences.getInstance();
    await store.setStringList(_roomsKey(kind, host, port, nick), rooms);
  } on Object {
    // 다음에 다시 들어가야 할 뿐이다
  }
}
