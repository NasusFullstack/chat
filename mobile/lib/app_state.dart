/// 화면이 보는 상태 한 곳 - 어느 채널이 있고 무슨 말이 오갔는가.
///
/// PC 앱에서 `ChatPage`가 들고 있던 **화면용 캐시**에 해당한다. 여기서 "무슨 일인지"를
/// 판단하지 않는다 - 그건 `core/session.dart`가 하고, 여기는 그 결과(이벤트)를 받아
/// 모아둘 뿐이다. 이 경계를 흐리면 PC와 모바일이 서로 다르게 해석하기 시작한다.
library;

import 'package:flutter/foundation.dart';

import 'dart:async';
import 'dart:io';

import 'core/battle_protocol.dart' as bp;
import 'core/chat_port.dart';
import 'core/client_badge.dart';
import 'core/events.dart';
import 'core/relay.dart' as relay;
import 'core/server_session.dart';
import 'core/session.dart';
import 'net/chat_link.dart';
import 'net/irc_client.dart';
import 'net/server_chat_client.dart';
import 'login_store.dart';
import 'net/reconnect.dart';
import 'net/relay_api.dart';
import 'prefs.dart';

/// 화면에 한 줄로 그려지는 것.
class ChatLine {
  ChatLine.message({
    required this.sender,
    required this.text,
    required this.mine,
    required this.isMention,
    required this.at,
  })  : isSystem = false;

  ChatLine.system({required this.text, required this.at})
      : sender = '',
        mine = false,
        isMention = false,
        isSystem = true;

  final String sender;
  final String text;
  final bool mine;
  final bool isMention;
  final bool isSystem;
  final DateTime at;
}

class AppState extends ChangeNotifier {
  AppState() {
    // **한 번만** 듣는다. connect() 안에서 듣기 시작하면 다시 붙을 때마다 듣는
    // 사람이 하나씩 늘어나서 같은 줄을 두 번, 세 번 해석한다 - 인증서를 믿고 다시
    // 붙는 경우에 바로 겪는다(메시지가 두 번 보인다)
    _listenTo(ChatKind.irc, _irc);
    _listenTo(ChatKind.server, _ws);
  }

  /// 통로 하나를 듣기 시작한다.
  ///
  /// **지금 쓰는 쪽에서 온 것만 본다.** 둘 다 열어두고 듣기 때문에, 확인하지 않으면
  /// 쓰지 않는 쪽이 늦게 올린 '끊겼다'가 지금 접속을 끊은 것처럼 보인다
  void _listenTo(ChatKind which, ChatLink link) {
    link.state.listen((s) {
      if (chatKind == which) _onLink(s);
    });
    link.incoming.listen((raw) {
      if (chatKind == which) _session?.handleIncoming(raw);
    });
  }

  final IrcClient _irc = IrcClient();
  final ServerChatClient _ws = ServerChatClient();

  /// 지금 어느 쪽인가. 통로·판단·**쌓이는 자리**가 전부 이 값으로 갈린다
  ChatKind chatKind = ChatKind.irc;

  /// 지금 쓰는 통로. 화면과 상태는 이것이 TLS 소켓인지 WebSocket 인지 모른다
  ChatLink get _client => chatKind == ChatKind.server ? _ws : _irc;

  /// 처음 보는 인증서를 만났으면 그 지문(없으면 빈 값). 화면이 사람에게 물어본다
  String get pendingFingerprint => _client.pendingFingerprint;

  /// 전에 믿기로 한 것과 달라졌는가
  bool get fingerprintChanged => _client.fingerprintChanged;
  /// 받은 것을 무슨 일로 읽을지 아는 쪽. IRC 면 `ChatSession`,
  /// 서버 채팅이면 `ServerSession` - **화면은 어느 쪽인지 모른다**
  ChatPort? _session;

  LinkState link = LinkState.idle;
  String statusText = '';

  /// 서버가 우리를 받아줬는가(001). **소켓이 붙은 것과 다르다.**
  /// 이게 되기 전에 채널 입장을 보내면 서버가 그냥 무시한다
  bool get loggedIn => myId.isNotEmpty;

  /// 서버가 확정해준 내 이름. **001 이 와야 채워진다.**
  ///
  /// 세션에서 파생시키지 않고 여기에 따로 둔다 - 세션은 접속할 때 새로 만들어지는데,
  /// 화면은 그보다 오래 살아 있고 '로그인했는가'를 계속 봐야 하기 때문이다
  String myId = '';

  /// 지금 붙어 있는 서버. 채널 목록을 **서버+닉네임별로** 적어두는 데 쓴다
  String host = '';
  int port = 0;

  /// 채널마다 쌓인 줄. 들어간 순서를 지키려고 목록을 따로 둔다
  final List<String> channels = [];
  final Map<String, List<ChatLine>> lines = {};
  final Map<String, List<String>> members = {};
  final Map<String, int> unread = {};

  String current = '';

  /// 한 채널에 들고 있을 줄 수. 폰은 메모리가 넉넉하지 않다
  static const int keepLines = 500;

  // ---------------------------------------------------------- 중계 서버
  ProfileApi? _profiles;
  ChatLogApi? _logs;

  /// 검사가 가짜 기록 창구를 끼울 수 있게 열어둔다.
  ///
  /// 왜 필요한가: "지난 대화를 어디서부터 받아올까"를 정하는 규칙이 틀려서 **언제나
  /// 0줄**이 오던 버그가 있었다. 그 규칙을 검사에 베껴 쓰면 코드가 바뀔 때 검사는
  /// 안 바뀌어서 또 못 잡는다(CLAUDE.md 11-5). 진짜 코드가 무엇을 묻는지 봐야 한다
  set logsForTest(ChatLogApi fake) => _logs = fake;
  final FileApi files = FileApi();

  /// 사람마다의 아이콘(base64). 서버에서 받아온다 - 상대가 접속해 있지 않아도 보인다
  final Map<String, String> avatars = {};

  /// 사람마다 **보이는 이름**. 서버 채팅에서만 채워진다 - IRC 는 닉네임이 곧
  /// 아이디였고 한글도 못 썼다. 화면은 [displayName] 으로 묻는다
  final Map<String, String> nicknames = {};

  /// 이 사람을 화면에 뭐라고 쓸까. 모르면 아이디 그대로.
  ///
  /// 화면이 `nicknames[id] ?? id` 를 곳곳에서 쓰면 한 군데를 빠뜨리는 날이 온다
  /// (그러면 같은 사람이 어떤 칸에서는 아이디로, 어떤 칸에서는 이름으로 보인다).
  String displayName(String id) {
    final nick = nicknames[id];
    return nick == null || nick.isEmpty ? id : nick;
  }

  /// 채널마다 직전에 본 참여자. 새로 들어온 사람을 가려내는 데 쓴다
  final Map<String, Set<String>> _seenMembers = {};

  // ------------------------------------------------------------ 전투
  /// 채널마다 알려진 전투 방(번호, 연 사람, 알려진 때).
  ///
  /// **오래된 것은 잊는다.** 아침에 열린 방에 저녁에 들어가려다 "이미 끝난 방"을
  /// 만나는 것보다, "열린 방이 없다"고 말해주는 편이 낫다
  final Map<String, (String room, String host, DateTime at)> knownRooms = {};

  /// 이만큼 지난 방 알림은 잊는다(PC 와 같은 30분)
  static const Duration roomMemory = Duration(minutes: 30);

  /// 이 채널에 지금 들어갈 수 있는 방. 없으면 null
  (String, String)? openRoom(String channel) {
    final known = knownRooms[channel];
    if (known == null) return null;
    if (DateTime.now().difference(known.$3) > roomMemory) {
      knownRooms.remove(channel);
      return null;
    }
    return (known.$1, known.$2);
  }

  /// 방을 하나 열고 채널에 알린다. 돌려주는 것은 방 번호.
  ///
  /// **주소는 안 나간다** - 번호만 알린다. 중계 서버 주소는 각자 안다
  String openBattleRoom(String channel) {
    final room = bp.newRoom();
    // 알리는 방법은 프로토콜마다 다르다(IRC 는 CTCP, 서버 채팅은 걸러지는 채팅).
    // **여기서 갈라지지 않는다** - 그걸 아는 쪽이 한다
    _session?.announceBattleRoom(channel, room);
    knownRooms[channel] = (room, myId, DateTime.now());
    return room;
  }

  /// 사람마다 쓰는 프로그램. 이것도 서버에서 받아온다 - IRC 로 물어보던 길은
  /// `core/session.dart`에 남겨둔 채 꺼뒀다(core/client_badge.dart 에 이유)
  final Map<String, ClientInfo> clients = {};

  /// 내가 무엇인지(버전 포함). 로그인할 때 받아 서버에 적는다
  ClientInfo _me = const ClientInfo();

  /// 내 프로필을 고칠 수 있는 표. 없으면 서버가 안 고쳐준다
  String _profileToken = '';

  /// 올린 파일의 표 - 이게 있으면 내가 올린 것이고, 도로 내릴 수 있다
  final Map<String, String> fileTokens = {};

  Timer? _flushTimer;

  /// 올리는 중인 파일(화면이 진행 상태를 보여주는 데 쓴다).
  String uploading = '';

  /// 로그인이 끝나기를 기다리는 쪽
  Completer<bool>? _loginDone;

  // ------------------------------------------------------------ 설정
  /// 사람이 고른 설정. 화면이 고친 뒤 [applySettings] 를 부른다
  Prefs prefs = Prefs();

  /// 지금 앱을 보고 있는가. 수명주기 관찰(main.dart)이 알려준다
  bool inForeground = true;

  /// 이름을 기억할까 / 다음에 알아서 들어갈까. 로그인 화면의 체크 두 개다
  bool rememberLogin = true;
  bool autoLogin = true;

  // 예전에는 여기서 안드로이드 서비스를 띄워 접속을 붙잡아 뒀다. 한국 폰의
  // 보이스피싱 탐지가 그걸 보고 **설치 자체를 막아서** 뺐다(mobile/README.md).
  // 대신 서버가 푸시로 깨워주는 길로 간다

  // ------------------------------------------------------------ 다시 붙기
  /// 다시 붙을 때 쓸 접속 정보. 사람에게 또 물어볼 수는 없다
  String _nick = '';
  String _password = '';
  bool _secure = true;
  String _appVersion = '0.0.0';

  /// 일부러 끊는 중인가(로그아웃·종료). 그때는 다시 붙지 않는다 - 안 그러면
  /// 로그아웃하자마자 방금 나온 이름으로 다시 들어간다(CLAUDE.md 10번)
  bool _leaving = false;

  late final ReconnectPolicy reconnect = ReconnectPolicy(
    connectNow: _reconnectNow,
    notify: (text) {
      statusText = text;
      notifyListeners();
    },
  );

  // ------------------------------------------------------------------ 접속
  /// 붙는다. [kind] 가 **어느 쪽인지**를 정하고, 나머지는 그쪽 사정이다.
  ///
  /// - IRC: 주소·포트·인증서를 사람이 정한다. 이름은 닉네임이고 비밀번호는 서버
  ///   비밀번호다(대개 없다)
  /// - 서버 채팅: 주소는 **우리가 안다**. 이름은 계정 아이디고 비밀번호는 그 계정의
  ///   것이다. [makeAccount] 면 가입부터 하고 이어서 로그인한다
  Future<bool> connect({
    required String host,
    required int port,
    required String nick,
    String password = '',
    bool secure = true,
    String appVersion = '0.0.0',
    ChatKind kind = ChatKind.irc,
    bool makeAccount = false,
  }) async {
    statusText = '연결 중...';
    chatKind = kind;
    notifyListeners();

    if (kind == ChatKind.server) {
      // 주소를 사람에게 받지 않는다 - 우리 서버 하나뿐이라 잘못 적을 여지를 없앤다.
      // **고정값이어야 한다** - 기록·프로필이 쌓이는 자리가 이 값으로 정해지고,
      // PC 와 같은 값이라야 폰과 PC 가 같은 자리를 본다
      host = relay.serverChatHost;
      port = relay.serverChatPort;
      secure = true;
    }
    this.host = host;
    this.port = port;
    // 다시 붙을 때 쓴다. 사람에게 또 물어볼 수는 없다
    _nick = nick;
    _password = password;
    _secure = secure;
    _appVersion = appVersion;
    _leaving = false;
    final ok = await _client.connect(host: host, port: port, secure: secure);
    if (!ok) return false;

    _session = switch (kind) {
      ChatKind.irc => ChatSession(
          send: _irc.send,
          emit: handleEvent,
          wantedNick: nick,
          appVersion: appVersion,
        ),
      ChatKind.server => ServerSession(
          send: _ws.sendRaw,
          emit: handleEvent,
          userId: nick,
        ),
    };
    // 기록·프로필이 놓이는 자리는 (프로토콜, 호스트, 포트)로 정해진다. 프로토콜이
    // 같이 들어가므로 **IRC 방과 서버 채팅 방은 저절로 갈린다**
    _me = ourClient(appVersion);
    final where = kind.wireName;
    _profiles = ProfileApi(where, host, port);
    files.group = relay.groupId(where, host, port);
    unawaited(files.refreshLimits());
    _flushTimer?.cancel();
    if (kind == ChatKind.server) {
      // **서버가 기록을 들고 있다.** 각자 올려서 모으던 길(아래 IRC 쪽)은 쓸 일이
      // 없다 - 들어가면 응답에 하루치가 실려 오고, 그래서 올리는 요청도 0건이다
      _logs = null;
    } else {
      _logs = ChatLogApi(where, host, port);
      // 모아서 보낸다. 말 한마디마다 보내면 수다 떠는 속도가 곧 요청 속도가 된다
      _flushTimer = Timer.periodic(const Duration(seconds: 8), (_) => _logs?.flush());
    }

    // **여기서 끝이 아니다.** IRC 는 서버가 001 을 보내줘야 '등록된 사용자'가 된다.
    // 그 전에 채널 입장을 보내면 서버가 조용히 무시하므로, 화면도 그때까지 기다린다
    _loginDone = Completer<bool>();
    final session = _session;
    if (makeAccount && session is ServerSession) {
      // 가입이 끝나면 **세션이 알아서 이어서 로그인한다** - 사람이 두 번 누를 일이 없게
      session.register(password);
      statusText = '가입하는 중...';
    } else {
      session!.login(password: password, realname: nick);
      statusText = '로그인 중...';
    }
    notifyListeners();

    final accepted = await _loginDone!.future.timeout(
      const Duration(seconds: 25),
      onTimeout: () {
        statusText = '서버가 응답하지 않습니다. 이름이나 비밀번호를 확인해 주세요.';
        return false;
      },
    );
    _loginDone = null;
    if (!accepted) {
      await _client.close();
      notifyListeners();
      return false;
    }

    // **앱이 보이는 동안** 해둬야 하는 두 가지다.
    //  - 접속 붙잡기: 안드로이드 12부터 배경에서 포그라운드 서비스를 띄우면 거절한다.
    //    홈으로 나간 뒤에 띄우려 하면 늦는다
    //  - 알림 허락: 배경에서 물어보면 창이 안 뜨고 조용히 거절된 것처럼 된다

    // 다음에 켤 때 이름을 다시 치지 않게 적어둔다. **성공한 뒤에만** 적는다 -
    // 거절당한 이름을 기억하면 다음에도 같은 실패로 시작한다
    unawaited(saveLastLogin(
      kind: kind,
      host: host,
      port: port,
      nick: myId,
      secure: secure,
      remember: rememberLogin,
      auto: autoLogin,
    ));
    // 참여자 목록에 "춥채팅 · 폰"이 뜨게 내가 무엇인지 적어둔다. IRC 로 서로
    // 물어보던 길은 꺼뒀다(core/client_badge.dart 에 이유)
    unawaited(publishClient());
    unawaited(rejoinSaved());
    return true;
  }

  /// 연결 상태가 바뀌었다.
  void _onLink(LinkState s) {
    link = s;
    if (s == LinkState.failed) statusText = _client.lastError;
    if (s == LinkState.closed) {
      statusText = '연결이 끊겼습니다.';
      _lostConnection();
    }
    notifyListeners();
  }

  /// 예기치 않게 끊겼다 - 다시 붙기를 시작한다.
  ///
  /// 폰은 신호가 끊기는 자리가 PC 보다 훨씬 많다. 다시 안 붙으면 사람은 **죽은 채팅
  /// 화면**을 보게 되고 앱을 끄고 다시 켜는 수밖에 없다.
  void _lostConnection() {
    // 일부러 끊은 것이거나 아직 로그인도 안 됐으면 다시 붙지 않는다
    if (_leaving || !loggedIn) return;
    reconnect.start(channels);
  }

  /// 다시 붙어본다. 되면 보던 채널로 돌아간다.
  Future<bool> _reconnectNow() async {
    final rooms = reconnect.pendingRooms;
    final ok = await connect(
      kind: chatKind,
      host: host,
      port: port,
      nick: _nick,
      password: _password,
      secure: _secure,
      appVersion: _appVersion,
    );
    if (!ok) {
      // 다음 차례를 예약한다. 시도할수록 간격이 늘어난다
      reconnect.schedule();
      return false;
    }
    reconnect.succeeded();
    // **채널 목록에 있어도 다시 보낸다.** 서버는 우리가 그 방에 있었다는 걸 잊었다 -
    // 우리 화면에만 남아 있으면 말을 해도 아무에게도 안 간다
    for (final room in rooms) {
      _session?.joinChannel(room);
      await Future<void>.delayed(const Duration(milliseconds: 400));
    }
    // 들어간 뒤에 보낸다 - 들어가기 전에 보내면 서버가 조용히 무시한다
    _flushOutbox();
    return true;
  }

  /// 지난번에 들어가 있던 채널에 다시 들어간다.
  ///
  /// 한꺼번에 보내지 않고 한 박자씩 띄운다. 서버는 짧은 시간에 몰린 요청을 폭주로
  /// 보고 연결을 끊는다(CLAUDE.md 2-4 에 실측표가 있다).
  Future<void> rejoinSaved() async {
    final rooms = await loadRooms(host, port, myId, kind: chatKind);
    // 다시 들어가는 **동안에는 기억을 건드리지 않는다.** 한 방에 들어갈 때마다
    // 적어버리면, 도중에 앱이 꺼지면 아직 못 들어간 방들이 통째로 사라진다
    _rejoining = true;
    try {
      for (final room in rooms) {
        if (channels.contains(room)) continue;
        joinChannel(room);
        await Future<void>.delayed(const Duration(milliseconds: 400));
      }
    } finally {
      _rejoining = false;
    }
    _rememberRooms();
  }

  /// 지금 지난번 채널에 다시 들어가는 중인가
  bool _rejoining = false;

  /// 채널 목록을 적는 일은 **차례대로** 한다.
  ///
  /// 한꺼번에 던지면 끝나는 순서가 뒤바뀌어 옛 목록이 나중에 덮어쓸 수 있다
  /// (실측: 들어가기 두 번을 연달아 했을 때 두 번째가 사라졌다).
  Future<void> _roomWrite = Future<void>.value();

  /// 들어가 있는 채널을 적어둔다(다음에 켤 때 그대로 들어가게).
  void _rememberRooms() {
    if (_rejoining || !loggedIn || host.isEmpty) return;
    final now = List<String>.of(channels);
    final kind = chatKind;
    _roomWrite =
        _roomWrite.then((_) => saveRooms(host, port, myId, now, kind: kind));
  }

  /// 적어두는 일이 끝나기를 기다린다(검사와 종료 때 쓴다).
  Future<void> get roomsWritten => _roomWrite;

  /// 설정이 바뀌었다 - 지금 상태에 반영한다.
  ///
  /// 접속 유지를 껐으면 붙잡기를 **바로** 놓아야 한다. 안 그러면 "실행 중" 알림이
  /// 다음 실행까지 남아서 끈 것처럼 보이지 않는다.
  Future<void> applySettings() async {
    await prefs.save();
    notifyListeners();
  }

  /// 홈으로 나갔다. 이제부터 오는 말은 알림으로 알린다
  void wentBackground() {
    inForeground = false;
  }

  /// 앱으로 돌아왔다.
  Future<void> cameBack() async {
    inForeground = true;
    // 사람이 앱을 다시 보고 있다는 건 신호가 돌아왔을 가능성이 가장 큰 순간이다.
    // 30초짜리 예약을 기다리면 그동안 먹통처럼 보인다.
    //
    // **끊김을 아직 못 알아챘을 수도 있다** - 홈으로 나가 있는 동안 안드로이드가
    // 우리를 멈춰 세우면 그 사실조차 돌아온 뒤에야 안다. 그래서 상태를 보고 시작한다
    if (loggedIn && link != LinkState.connected) {
      ensureConnected();
    } else {
      reconnect.tryNow();
    }
  }

  /// 검사가 "실제로 입장 요청이 나갔는가"를 볼 수 있게 열어둔 구멍.
  /// 핸들러를 직접 부르는 검사는 사람이 눌렀을 때만 나는 버그를 못 잡는다
  void Function(String)? onJoinForTest;

  void joinChannel(String name) {
    onJoinForTest?.call(name);
    _session?.joinChannel(name);
  }

  void leaveChannel(String channel) => _session?.leaveChannel(channel);

  /// 아직 못 보낸 말. 끊겨 있는 동안 친 것을 모아뒀다가 다시 붙으면 보낸다
  final List<({String channel, String text})> _outbox = [];

  /// 아직 안 나간 말이 있는가(화면이 "보내는 중"을 보여주는 데 쓴다)
  bool get hasUnsent => _outbox.isNotEmpty;

  void sendChat(String text) {
    if (current.isEmpty || text.trim().isEmpty) return;
    final body = text.trim();

    // **끊겨 있으면 버리지 않는다.** 홈으로 나갔다 오면 접속이 끊겨 있는데, 그때 친
    // 말이 그냥 사라지면 사람은 보낸 줄 안다. 모아뒀다가 다시 붙는 대로 보낸다
    if (!loggedIn || link != LinkState.connected) {
      _outbox.add((channel: current, text: body));
      _add(
        current,
        ChatLine.system(
          text: '연결이 끊겨 있어 다시 붙는 중입니다. 친 말은 붙는 대로 전해집니다.',
          at: DateTime.now(),
        ),
      );
      ensureConnected();
      notifyListeners();
      return;
    }
    _session?.sendChat(current, body);
  }

  /// 끊겨 있으면 **지금** 다시 붙어본다.
  ///
  /// 홈으로 나가 있는 동안 안드로이드가 우리를 멈춰 세우면, 끊겼다는 것조차 돌아온
  /// 뒤에야 알게 된다. 그래서 "끊김을 알아챈 뒤에 시작하는" 재접속만으로는 모자란다
  void ensureConnected() {
    if (!reconnect.active) {
      reconnect.start(channels);
    } else {
      reconnect.tryNow();
    }
  }

  /// 모아둔 말을 보낸다. 다시 붙어 채널까지 들어간 뒤에 부른다
  void _flushOutbox() {
    if (_outbox.isEmpty) return;
    final waiting = List.of(_outbox);
    _outbox.clear();
    for (final one in waiting) {
      // 그 사이에 나온 방이면 보낼 곳이 없다 - 조용히 버리지 말고 알린다
      if (!channels.contains(one.channel)) {
        _add(
          current.isEmpty ? one.channel : current,
          ChatLine.system(
            text: '${one.channel}에 못 들어가 "${one.text}"를 보내지 못했습니다.',
            at: DateTime.now(),
          ),
        );
        continue;
      }
      _session?.sendChat(one.channel, one.text);
    }
    notifyListeners();
  }

  void showChannel(String channel) {
    current = channel;
    unread[channel] = 0;
    notifyListeners();
  }

  Future<void> disconnect() async {
    // 일부러 끊는 것이다 - 다시 붙기를 완전히 접는다
    _leaving = true;
    reconnect.cancel();
    // 모아둔 대화를 마지막으로 밀어낸다 - 안 하면 방금 나눈 이야기가 통째로 안 올라가서
    // 그 사이에 없던 사람이 그만큼을 영영 못 본다
    _flushTimer?.cancel();
    await _logs?.flush();
    _session?.quit();
    await _client.close();
    _session = null;
    myId = '';
    channels.clear();
    lines.clear();
    members.clear();
    unread.clear();
    current = '';
    link = LinkState.idle;
    notifyListeners();
  }

  @override
  void dispose() {
    _flushTimer?.cancel();
    reconnect.cancel();
    // **둘 다 치운다.** 지금 쓰는 쪽만 치우면 다른 쪽 스트림이 열린 채로 남는다
    _irc.dispose();
    _ws.dispose();
    super.dispose();
  }

  // ---------------------------------------------------------- 중계 서버 기능
  /// 내 아이콘을 서버에 올린다(내가 꺼져 있어도 남에게 보이게).
  Future<void> publishProfile(String avatarB64) async {
    final token = await _profiles?.publish(myId,
        avatar: avatarB64, client: _me.known ? _me : null, token: _profileToken);
    if (token != null && token.isNotEmpty) _profileToken = token;
    avatars[myId] = avatarB64;
    notifyListeners();
  }

  /// 지금 보이는 사람들의 얼굴과 **쓰는 프로그램**을 받아온다.
  ///
  /// 이미 아는 사람은 알아서 건너뛴다. 둘을 한 번에 받아오는 이유는 어차피 같은
  /// 조회라서다 - 따로 물으면 참여자 수만큼 요청이 두 배가 된다.
  Future<void> wantFaces(String channel) async {
    final people = members[channel] ?? const <String>[];
    final found = await _profiles?.lookup(people) ?? const <String, Who>{};
    if (found.isEmpty) return;
    found.forEach((nick, who) {
      if (who.avatar.isNotEmpty) avatars[nick] = who.avatar;
      if (who.client.known) clients[nick] = who.client;
    });
    notifyListeners();
  }

  /// "나는 춥채팅 모바일 x.y.z"를 서버에 적는다.
  ///
  /// 아이콘은 **같이 보내지 않는다.** 모바일에는 아이콘 편집기가 없어서 빈 값을
  /// 보내게 되는데, 그러면 그 사람이 PC에서 정해둔 얼굴이 서버에서 지워진다.
  Future<void> publishClient() async {
    if (!_me.known || myId.isEmpty) return;
    final token = await _profiles?.publish(myId,
        client: _me, token: _profileToken);
    if (token != null && token.isNotEmpty) _profileToken = token;
    clients[myId] = _me;
    notifyListeners();
  }

  /// 내가 없는 동안 오간 이야기를 받아온다.
  ///
  /// 기준은 **내가 마지막으로 본 줄의 시각**이다. 그보다 뒤엣것만 달라고 하면 이미
  /// 화면에 있는 것과 겹치지 않는다.
  Future<void> fetchMissed(String channel) async {
    // **서버 채팅은 받아올 것이 없다.** 들어갈 때 응답에 하루치가 실려 온다 -
    // 여기서 또 물으면 같은 이야기가 두 벌로 쌓인다
    if (_logs == null) return;
    final seen = lines[channel] ?? const <ChatLine>[];
    double newest = 0;
    for (final line in seen) {
      // **안내 줄은 세지 않는다.** 들어가면 "입장 완료"를 먼저 올리는데 그 시각이
      // 지금이라, 그걸 기준으로 삼으면 서버에 "지금 이후 것만 달라"고 묻게 되어
      // **언제나 0줄**이 온다. 실제로 그래서 지난 대화가 안 보였다
      if (line.isSystem) continue;
      final ts = line.at.millisecondsSinceEpoch / 1000;
      if (ts > newest) newest = ts;
    }
    if (newest == 0) {
      // 여기 기록이 아예 없으면 하루치를 다 받아온다(처음 들어온 채널)
      newest = DateTime.now().millisecondsSinceEpoch / 1000 - 24 * 3600;
    }
    final missed = await _logs?.missed(channel, newest) ?? const [];
    if (missed.isEmpty) return;
    _add(channel, ChatLine.system(
        text: '── 내가 없는 동안 오간 이야기 ${missed.length}줄 ──', at: DateTime.now()));
    for (final line in missed) {
      final ts = ((line['ts'] as num?) ?? 0).toDouble();
      _add(channel, ChatLine.message(
        sender: '${line['sender']}',
        text: '${line['text']}',
        mine: '${line['sender']}' == myId,
        isMention: false,
        at: DateTime.fromMillisecondsSinceEpoch((ts * 1000).round()),
      ));
    }
    _add(channel, ChatLine.system(text: '── 여기까지 ──', at: DateTime.now()));
    notifyListeners();
  }

  /// 파일을 올리고 **주소를 입력줄에 넣을 수 있게** 돌려준다.
  ///
  /// 바로 보내지 않는 이유: 사람이 한마디 덧붙이거나("이거 봐") 잘못 고른 것을 지울 수
  /// 있어야 한다. 주소가 들어가면 그 뒤는 이미 있는 길이 알아서 한다.
  Future<UploadResult> upload(File file, {String kind = 'file'}) async {
    uploading = file.uri.pathSegments.last;
    notifyListeners();
    final result = await files.upload(file, kind: kind);
    uploading = '';
    if (result.ok && result.token.isNotEmpty) {
      fileTokens[result.id] = result.token;
    }
    notifyListeners();
    return result;
  }

  // ------------------------------------------------------------------ 이벤트
  /// 세션이 "무슨 일이 일어났다"고 알려주는 곳.
  ///
  /// 공개해 둔 이유: 화면 검사가 **이 길 그대로** 상태를 만들 수 있어야 한다.
  /// 가짜를 따로 만들면 진짜 앱과 다른 것을 시험하게 된다
  void handleEvent(ChatEvent event) {
    switch (event) {
      case LoggedIn(:final userId):
        myId = userId;
        statusText = '';
        _loginDone?.complete(true);
        _loginDone = null;
      case ChannelJoined(:final channel, :final text):
        // 이미 화면에 있는 방이면 **다시 붙어서 돌아온 것**이다. 들어간 안내를 또
        // 쌓으면 끊길 때마다 "입장 완료"가 줄줄이 늘어난다
        final returning = channels.contains(channel);
        if (!returning) channels.add(channel);
        lines.putIfAbsent(channel, () => []);
        members.putIfAbsent(channel, () => []);
        if (current.isEmpty) current = channel;
        if (!returning) {
          _add(channel, ChatLine.system(text: text, at: DateTime.now()));
        }
        // 내가 없는 동안 오간 이야기를 채워 넣는다. 돌아온 경우에도 해야 한다 -
        // 끊겨 있던 사이에 오간 말이 폰에는 아예 없다(PC 는 기록 파일이 있다)
        unawaited(fetchMissed(channel));
        _rememberRooms();
      case ChannelLeft(:final channel):
        channels.remove(channel);
        lines.remove(channel);
        members.remove(channel);
        unread.remove(channel);
        _seenMembers.remove(channel);
        _rememberRooms();
        if (current == channel) current = channels.isEmpty ? '' : channels.first;
      case ChannelJoinFailed(:final text):
        statusText = text;
      case MessageReceived(:final channel, :final sender, :final text, :final mine,
            :final isMention):
        _add(
          channel,
          ChatLine.message(
            sender: sender,
            text: text,
            mine: mine,
            isMention: isMention,
            at: DateTime.now(),
          ),
        );
        if (!mine && channel != current) {
          unread[channel] = (unread[channel] ?? 0) + 1;
        }
        // 받아본 줄을 중계 서버에 올린다 - 앱을 꺼둔 사람이 나중에 따라잡을 수 있게.
        // 내가 보낸 것도 올린다(빠지면 남이 받아갈 기록에 구멍이 생긴다)
        _logs?.record(channel, sender, text,
            DateTime.now().millisecondsSinceEpoch / 1000);
      case SystemNotice(:final channel, :final text):
        final where = channel.isEmpty ? current : channel;
        if (where.isEmpty) {
          statusText = text;
        } else {
          _add(where, ChatLine.system(text: text, at: DateTime.now()));
        }
      case UserlistUpdated(:final channel, :final users):
        // **새로 들어온 사람은 예전 답을 버리고 다시 묻는다.** 같은 이름으로 다른
        // 기기에서 들어올 수 있다 - 어제는 폰, 오늘은 PC. 한 번 받은 것을 그대로
        // 믿으면 PC 로 들어온 사람에게 폰 표시가 계속 붙어 있게 된다.
        // 처음 목록을 받을 때는 '새로 들어온 사람'이 없다(서버 것을 그대로 쓴다)
        final before = _seenMembers[channel];
        final now = users.toSet();
        _seenMembers[channel] = now;
        if (before != null) {
          for (final who in now.difference(before)) {
            _profiles?.forget(who);
            clients.remove(who);
          }
        }
        members[channel] = users;
        // 얼굴은 채팅 통로로 오기를 기다리지 않고 서버에도 물어본다 - 그 사람이 지금
        // 접속해 있지 않아도 보이게
        unawaited(wantFaces(channel));
      case BattleRoomOpened(:final channel, :final host, :final room):
        knownRooms[channel] = (room, host, DateTime.now());
        _add(
          channel,
          ChatLine.system(
            text: '$host님이 배틀크루저 전투 방을 열었습니다. '
                "'배틀크루저 전투 참가'를 치면 들어갑니다.",
            at: DateTime.now(),
          ),
        );
      case NicknameUpdated(:final userId, :final nickname):
        // 서버 채팅에서만 온다. 아이디와 **보이는 이름**이 따로다
        nicknames[userId] = nickname;
      case AvatarUpdated(:final userId, :final avatar):
        // **참여자 목록에 같이 온다** - 따로 물어볼 것이 없다(IRC 는 CTCP 로 300자씩
        // 쪼개 주고받아야 했고 조각이 하나 빠지면 아무것도 안 떴다)
        if (avatar.isEmpty) {
          avatars.remove(userId);
        } else {
          avatars[userId] = avatar;
        }
      case NicknameRetrying(:final newNickname):
        statusText = '닉네임이 사용 중이라 $newNickname(으)로 다시 시도합니다.';
      case ConnectionClosed(:final text):
        statusText = '연결이 종료되었습니다: $text';
        _loginDone?.complete(false);
        _loginDone = null;
      default:
        break;
    }
    notifyListeners();
  }

  void _add(String channel, ChatLine line) {
    final list = lines.putIfAbsent(channel, () => []);
    list.add(line);
    // 오래된 것부터 버린다. 폰에서 몇 만 줄을 들고 있을 이유가 없다
    if (list.length > keepLines) list.removeRange(0, list.length - keepLines);
  }
}
