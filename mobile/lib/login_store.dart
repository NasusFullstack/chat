/// 지난번 접속을 기억한다 - 닉네임, 서버, 그리고 **들어가 있던 채널**.
///
/// ## 왜
/// 폰에서 글자를 치는 것은 PC보다 훨씬 번거롭다. 앱을 켤 때마다 이름과 서버 주소를
/// 다시 치게 하면 그것만으로 안 쓰게 된다. PC 앱이 로그인 정보를 기억하는 것과 같다.
///
/// ## 채널은 닉네임마다 따로 기억한다
/// 같은 폰을 두 이름으로 쓸 수 있다. 한 이름으로 들어갔던 방을 다른 이름으로 켤 때
/// 멋대로 들어가면 안 된다 - 그래서 열쇠에 서버와 닉네임을 같이 넣는다.
///
/// 비밀번호는 **적어두지 않는다.** 우리 서버는 접속 비밀번호를 쓰지 않고, 그걸
/// 기기에 평문으로 남길 이유가 없다.
library;

import 'package:shared_preferences/shared_preferences.dart';

import 'core/relay.dart' as relay;

/// 기억해둔 접속 정보.
class LastLogin {
  const LastLogin({
    this.host = 'home.pdlab.kr',
    this.port = 6697,
    this.nick = '',
    this.secure = true,
    this.remember = true,
    this.auto = true,
  });

  final String host;
  final int port;
  final String nick;
  final bool secure;

  /// 이름을 기억해 둘까. 끄면 적어둔 이름을 지운다
  final bool remember;

  /// 켜면 앱을 켤 때 **알아서** 들어간다. 이름이 기억되어 있어야 의미가 있다
  final bool auto;

  /// 알아서 들어갈 수 있는 상태인가.
  bool get canAuto => auto && remember && nick.isNotEmpty;

  /// 한 군데만 고친 새 값(나머지는 그대로).
  LastLogin copyWith({bool? remember, bool? auto}) => LastLogin(
        host: host,
        port: port,
        nick: nick,
        secure: secure,
        remember: remember ?? this.remember,
        auto: auto ?? this.auto,
      );
}

/// 지난번 접속을 읽어온다. 없으면 기본값(우리 서버).
Future<LastLogin> loadLastLogin() async {
  try {
    final store = await SharedPreferences.getInstance();
    return LastLogin(
      host: store.getString('login_host') ?? 'home.pdlab.kr',
      port: store.getInt('login_port') ?? 6697,
      nick: store.getString('login_nick') ?? '',
      secure: store.getBool('login_secure') ?? true,
      remember: store.getBool('login_remember') ?? true,
      auto: store.getBool('login_auto') ?? true,
    );
  } on Object {
    // 못 읽어도 로그인 화면은 떠야 한다
    return const LastLogin();
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
  bool remember = true,
  bool auto = true,
}) async {
  try {
    final store = await SharedPreferences.getInstance();
    await store.setString('login_host', host);
    await store.setInt('login_port', port);
    await store.setString('login_nick', remember ? nick : '');
    await store.setBool('login_secure', secure);
    await store.setBool('login_remember', remember);
    await store.setBool('login_auto', auto);
  } on Object {
    // 못 적어도 이번 접속은 되어 있다
  }
}

/// 자동으로 들어갈지를 바꾼다(설정 화면).
Future<void> saveAutoLogin(bool on) async {
  try {
    final store = await SharedPreferences.getInstance();
    await store.setBool('login_auto', on);
  } on Object {
    // 다음 실행에 반영이 안 될 뿐이다
  }
}

/// 채널 목록을 적어두는 열쇠. 서버와 닉네임이 같이 들어간다
String _roomsKey(String host, int port, String nick) =>
    'rooms_${relay.groupId('irc', host, port)}_${nick.toLowerCase()}';

/// 이 이름으로 들어가 있던 채널들.
Future<List<String>> loadRooms(String host, int port, String nick) async {
  if (nick.isEmpty) return const [];
  try {
    final store = await SharedPreferences.getInstance();
    return store.getStringList(_roomsKey(host, port, nick)) ?? const [];
  } on Object {
    return const [];
  }
}

/// 들어가 있는 채널을 적어둔다. 들어가고 나갈 때마다 부른다.
Future<void> saveRooms(
    String host, int port, String nick, List<String> rooms) async {
  if (nick.isEmpty) return;
  try {
    final store = await SharedPreferences.getInstance();
    await store.setStringList(_roomsKey(host, port, nick), rooms);
  } on Object {
    // 다음에 다시 들어가야 할 뿐이다
  }
}
