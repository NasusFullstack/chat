/// 화면이 보는 상태 한 곳 - 어느 채널이 있고 무슨 말이 오갔는가.
///
/// PC 앱에서 `ChatPage`가 들고 있던 **화면용 캐시**에 해당한다. 여기서 "무슨 일인지"를
/// 판단하지 않는다 - 그건 `core/session.dart`가 하고, 여기는 그 결과(이벤트)를 받아
/// 모아둘 뿐이다. 이 경계를 흐리면 PC와 모바일이 서로 다르게 해석하기 시작한다.
library;

import 'package:flutter/foundation.dart';

import 'dart:async';
import 'dart:io';

import 'core/events.dart';
import 'core/relay.dart' as relay;
import 'core/session.dart';
import 'net/irc_client.dart';
import 'net/relay_api.dart';

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
  AppState();

  final IrcClient _client = IrcClient();
  ChatSession? _session;

  LinkState link = LinkState.idle;
  String statusText = '';

  String get myId => _session?.myId ?? '';

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

  /// 내 프로필을 고칠 수 있는 표. 없으면 서버가 안 고쳐준다
  String _profileToken = '';

  /// 올린 파일의 표 - 이게 있으면 내가 올린 것이고, 도로 내릴 수 있다
  final Map<String, String> fileTokens = {};

  Timer? _flushTimer;

  /// 올리는 중인 파일(화면이 진행 상태를 보여주는 데 쓴다).
  String uploading = '';

  // ------------------------------------------------------------------ 접속
  Future<bool> connect({
    required String host,
    required int port,
    required String nick,
    String password = '',
    bool secure = true,
    bool allowBadCertificate = false,
  }) async {
    _client.state.listen((s) {
      link = s;
      if (s == LinkState.failed) statusText = _client.lastError;
      if (s == LinkState.closed) statusText = '연결이 끊겼습니다.';
      notifyListeners();
    });
    _client.lines.listen((line) => _session?.handleLine(line));

    statusText = '연결 중...';
    notifyListeners();

    final ok = await _client.connect(
      host: host,
      port: port,
      secure: secure,
      allowBadCertificate: allowBadCertificate,
    );
    if (!ok) return false;

    _session = ChatSession(
      send: _client.send,
      emit: _onEvent,
      wantedNick: nick,
    );
    // 기록·프로필이 놓이는 자리는 (프로토콜, 호스트, 포트)로 정해진다. 서버가 바뀌면
    // 같이 바꿔야 **다른 서버 기록에 우리 대화가 쌓이지 않는다**
    _profiles = ProfileApi('irc', host, port);
    _logs = ChatLogApi('irc', host, port);
    files.group = relay.groupId('irc', host, port);
    unawaited(files.refreshLimits());
    // 모아서 보낸다. 말 한마디마다 보내면 수다 떠는 속도가 곧 요청 속도가 된다
    _flushTimer?.cancel();
    _flushTimer = Timer.periodic(const Duration(seconds: 8), (_) => _logs?.flush());

    _session!.login(password: password, realname: nick);
    statusText = '로그인 중...';
    notifyListeners();
    return true;
  }

  void joinChannel(String name) => _session?.joinChannel(name);

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
    // 모아둔 대화를 마지막으로 밀어낸다 - 안 하면 방금 나눈 이야기가 통째로 안 올라가서
    // 그 사이에 없던 사람이 그만큼을 영영 못 본다
    _flushTimer?.cancel();
    await _logs?.flush();
    _session?.quit();
    await _client.close();
    _session = null;
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
    _client.dispose();
    super.dispose();
  }

  // ---------------------------------------------------------- 중계 서버 기능
  /// 내 아이콘을 서버에 올린다(내가 꺼져 있어도 남에게 보이게).
  Future<void> publishProfile(String avatarB64) async {
    final token = await _profiles?.publish(myId, avatarB64, token: _profileToken);
    if (token != null && token.isNotEmpty) _profileToken = token;
    avatars[myId] = avatarB64;
    notifyListeners();
  }

  /// 지금 보이는 사람들의 얼굴을 받아온다(이미 아는 사람은 알아서 건너뛴다).
  Future<void> wantFaces(String channel) async {
    final people = members[channel] ?? const <String>[];
    final found = await _profiles?.lookup(people) ?? const <String, String>{};
    if (found.isEmpty) return;
    avatars.addAll(found);
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
  void _onEvent(ChatEvent event) {
    switch (event) {
      case LoggedIn():
        statusText = '';
      case ChannelJoined(:final channel, :final text):
        if (!channels.contains(channel)) channels.add(channel);
        lines.putIfAbsent(channel, () => []);
        members.putIfAbsent(channel, () => []);
        if (current.isEmpty) current = channel;
        _add(channel, ChatLine.system(text: text, at: DateTime.now()));
        // 내가 없는 동안 오간 이야기를 채워 넣는다
        unawaited(fetchMissed(channel));
      case ChannelLeft(:final channel):
        channels.remove(channel);
        lines.remove(channel);
        members.remove(channel);
        unread.remove(channel);
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
        members[channel] = users;
        // 얼굴은 채팅 통로로 오기를 기다리지 않고 서버에도 물어본다 - 그 사람이 지금
        // 접속해 있지 않아도 보이게
        unawaited(wantFaces(channel));
      case NicknameRetrying(:final newNickname):
        statusText = '닉네임이 사용 중이라 $newNickname(으)로 다시 시도합니다.';
      case ConnectionClosed(:final text):
        statusText = '연결이 종료되었습니다: $text';
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
