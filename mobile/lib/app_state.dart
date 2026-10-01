/// 화면이 보는 상태 한 곳 - 어느 채널이 있고 무슨 말이 오갔는가.
///
/// PC 앱에서 `ChatPage`가 들고 있던 **화면용 캐시**에 해당한다. 여기서 "무슨 일인지"를
/// 판단하지 않는다 - 그건 `core/session.dart`가 하고, 여기는 그 결과(이벤트)를 받아
/// 모아둘 뿐이다. 이 경계를 흐리면 PC와 모바일이 서로 다르게 해석하기 시작한다.
library;

import 'package:flutter/foundation.dart';

import 'core/events.dart';
import 'core/session.dart';
import 'net/irc_client.dart';

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
    _client.dispose();
    super.dispose();
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
      case SystemNotice(:final channel, :final text):
        final where = channel.isEmpty ? current : channel;
        if (where.isEmpty) {
          statusText = text;
        } else {
          _add(where, ChatLine.system(text: text, at: DateTime.now()));
        }
      case UserlistUpdated(:final channel, :final users):
        members[channel] = users;
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
