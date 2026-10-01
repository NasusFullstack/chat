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
import 'core/client_badge.dart';
import 'core/events.dart';
import 'core/relay.dart' as relay;
import 'core/session.dart';
import 'net/irc_client.dart';
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
    _client.state.listen(_onLink);
    _client.lines.listen((line) => _session?.handleLine(line));
  }

  final IrcClient _client = IrcClient();

  /// 처음 보는 인증서를 만났으면 그 지문(없으면 빈 값). 화면이 사람에게 물어본다
  String get pendingFingerprint => _client.pendingFingerprint;

  /// 전에 믿기로 한 것과 달라졌는가
  bool get fingerprintChanged => _client.fingerprintChanged;
  ChatSession? _session;

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
  final FileApi files = FileApi();

  /// 사람마다의 아이콘(base64). 서버에서 받아온다 - 상대가 접속해 있지 않아도 보인다
  final Map<String, String> avatars = {};

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
    _session?.send('PRIVMSG $channel :${bp.formatRoomNotice(room)}');
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
  Future<bool> connect({
    required String host,
    required int port,
    required String nick,
    String password = '',
    bool secure = true,
    String appVersion = '0.0.0',
  }) async {
    statusText = '연결 중...';
    notifyListeners();

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

    _session = ChatSession(
      send: _client.send,
      emit: handleEvent,
      wantedNick: nick,
      appVersion: appVersion,
    );
    // 기록·프로필이 놓이는 자리는 (프로토콜, 호스트, 포트)로 정해진다. 서버가 바뀌면
    // 같이 바꿔야 **다른 서버 기록에 우리 대화가 쌓이지 않는다**
    _me = ourClient(appVersion);
    _profiles = ProfileApi('irc', host, port);
    _logs = ChatLogApi('irc', host, port);
    files.group = relay.groupId('irc', host, port);
    unawaited(files.refreshLimits());
    // 모아서 보낸다. 말 한마디마다 보내면 수다 떠는 속도가 곧 요청 속도가 된다
    _flushTimer?.cancel();
    _flushTimer = Timer.periodic(const Duration(seconds: 8), (_) => _logs?.flush());

    // **여기서 끝이 아니다.** IRC 는 서버가 001 을 보내줘야 '등록된 사용자'가 된다.
    // 그 전에 채널 입장을 보내면 서버가 조용히 무시하므로, 화면도 그때까지 기다린다
    _loginDone = Completer<bool>();
    _session!.login(password: password, realname: nick);
    statusText = '로그인 중...';
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
    return true;
  }

  /// 지난번에 들어가 있던 채널에 다시 들어간다.
  ///
  /// 한꺼번에 보내지 않고 한 박자씩 띄운다. 서버는 짧은 시간에 몰린 요청을 폭주로
  /// 보고 연결을 끊는다(CLAUDE.md 2-4 에 실측표가 있다).
  Future<void> rejoinSaved() async {
    final rooms = await loadRooms(host, port, myId);
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
    _roomWrite = _roomWrite.then((_) => saveRooms(host, port, myId, now));
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
    // 30초짜리 예약을 기다리면 그동안 먹통처럼 보인다
    reconnect.tryNow();
  }

  /// 검사가 "실제로 입장 요청이 나갔는가"를 볼 수 있게 열어둔 구멍.
  /// 핸들러를 직접 부르는 검사는 사람이 눌렀을 때만 나는 버그를 못 잡는다
  void Function(String)? onJoinForTest;

  void joinChannel(String name) {
    onJoinForTest?.call(name);
    _session?.joinChannel(name);
  }

  void leaveChannel(String channel) => _session?.leaveChannel(channel);

  void sendChat(String text) {
    if (current.isEmpty || text.trim().isEmpty) return;
    _session?.sendChat(current, text.trim());
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
    _client.dispose();
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
    final seen = lines[channel] ?? const <ChatLine>[];
    double newest = 0;
    for (final line in seen) {
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
