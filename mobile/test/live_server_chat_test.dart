/// 폰이 **진짜 서버 채팅에 붙어서** 한 바퀴 도는가.
///
/// 여기서만 확인되는 것들이다. 앞 검사들은 우리끼리 맞춘 것뿐이라, 서버가 실제로
/// 받아주는지는 붙어봐야 안다:
///
/// - WebSocket 통로가 진짜로 열리는가
/// - 우리가 만든 사전을 서버가 받아주는가(로그인·입장·말하기)
/// - 서버가 보낸 것을 판단이 **같은 이벤트**로 바꾸는가(화면은 이것만 본다)
/// - **지난 기록이 입장 응답에 실려 오는가** - IRC 모드는 따로 받아와야 했다
/// - **한글 채널 이름·한글 표시 이름·긴 글**이 되는가(IRC 가 못 하던 것)
///
/// 서버에 못 닿으면 **건너뛰고 그 사실을 말한다** - 조용히 통과시키면 "안 되는데
/// 검사는 초록"이 된다.
library;

import 'dart:convert';
import 'dart:math';

// 무엇을 했는지 **말해야** 한다 - 건너뛴 것을 통과로 착각하지 않게
// ignore_for_file: avoid_print

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;

import 'package:chupchat/core/chat_port.dart';
import 'package:chupchat/core/events.dart';
import 'package:chupchat/core/relay.dart' as relay;
import 'package:chupchat/core/server_session.dart';
import 'package:chupchat/net/server_chat_client.dart';

/// 서버가 올라와 있고, 어떤 버전인가.
Future<Map<String, Object?>?> chatFeature() async {
  try {
    final r = await http
        .get(Uri.parse(relay.chatUrl))
        .timeout(const Duration(seconds: 8));
    if (r.statusCode != 200) return null;
    final body = jsonDecode(r.body);
    return body is Map<String, Object?> && body['feature'] == 'chat'
        ? body
        : null;
  } on Object {
    return null;
  }
}

/// 올라가 있는 기능이 그걸 할 수 있는가.
///
/// **모르는 명령은 조용히 버리도록** 되어 있다(구버전 앱이 죽지 않게). 그래서 옛
/// 서버에 새 명령을 보내면 실패도 안 오고 그냥 답이 없다 - 실제로 PC 에서 그렇게
/// 겪었다(가입이 아무 답 없이 멎었다). 버전을 먼저 보는 것이 유일한 분간법이다.
bool atLeast(Map<String, Object?> info, List<int> want) {
  final have = '${info['version'] ?? '0'}'.split('.').map(int.tryParse).toList();
  for (var i = 0; i < want.length; i++) {
    final part = i < have.length ? (have[i] ?? 0) : 0;
    if (part != want[i]) return part > want[i];
  }
  return true;
}

String freshId() {
  final rng = Random();
  return 'ph${List.generate(8, (_) => rng.nextInt(16).toRadixString(16)).join()}';
}

/// HTTP 창구로 계정을 만든다 - 서버가 WebSocket 가입을 아직 모를 때 쓴다.
Future<bool> makeAccountOverHttp(String id, String password) async {
  try {
    final r = await http
        .post(Uri.parse('${relay.chatUrl}/register'),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({'id': id, 'pw': password}))
        .timeout(const Duration(seconds: 12));
    return r.statusCode == 200;
  } on Object {
    return false;
  }
}

/// 한 사람 - 통로와 판단을 묶어둔다.
class Peer {
  Peer(this.id) {
    session = ServerSession(
      send: link.sendRaw,
      emit: events.add,
      userId: id,
    );
    link.incoming.listen(session.handleIncoming);
  }

  final String id;
  final ServerChatClient link = ServerChatClient();
  final List<ChatEvent> events = [];
  late final ServerSession session;

  Future<bool> open() => link.connect(
      host: relay.serverChatHost, port: relay.serverChatPort, secure: true);

  /// 그 일이 일어날 때까지 기다린다. 안 오면 null.
  ///
  /// **시간 제한을 둔다** - 안 오는 것을 그냥 기다리면 검사가 통째로 멈춘다.
  Future<T?> waitFor<T extends ChatEvent>(
      {Duration within = const Duration(seconds: 12)}) async {
    final until = DateTime.now().add(within);
    while (DateTime.now().isBefore(until)) {
      final found = events.whereType<T>();
      if (found.isNotEmpty) return found.first;
      await Future<void>.delayed(const Duration(milliseconds: 60));
    }
    return null;
  }

  Future<void> close() => link.close();
}

void main() {
  late Map<String, Object?>? info;

  setUpAll(() async {
    info = await chatFeature();
  });

  test('서버 채팅에 붙어서 한 바퀴 돈다', () async {
    if (info == null) {
      print('[건너뜀] 서버 채팅에 닿지 않음');
      markTestSkipped('서버 채팅에 닿지 않음 - 건너뜀');
      return;
    }
    final server = info!;
    print('[실행] 올라가 있는 chat ${server['version']} 에 실제로 붙는다');
    final id = freshId();
    const password = '비밀1234';
    final channel = '검사${DateTime.now().millisecondsSinceEpoch % 100000}';

    final me = Peer(id);
    expect(await me.open(), isTrue,
        reason: 'WebSocket 통로가 열려야 한다: ${me.link.lastError}');

    // ---------- 가입 ----------
    if (atLeast(server, [1, 1, 0])) {
      me.session.register(password);
      // 가입이 되면 판단이 **이어서 로그인까지** 보낸다
      expect(await me.waitFor<LoggedIn>(), isNotNull,
          reason: '연결 하나로 가입하고 들어가야 한다');
    } else {
      // 올라간 서버가 아직 옛것이다. 말하고 넘어간다 - 뒤 검사는 돌아야 하니
      // HTTP 창구로 계정만 만든다
      print('[건너뜀] 연결 하나로 가입 - 올라간 chat 이 ${server['version']}'
          ' (1.1.0 이상 필요). HTTP 창구로 계정만 만들고 이어서 본다');
      expect(await makeAccountOverHttp(id, password), isTrue);
      me.session.login(password: password);
      expect(await me.waitFor<LoggedIn>(), isNotNull);
    }
    expect(me.session.myId, id);

    // ---------- 들어가기 ----------
    me.events.clear();
    me.session.joinChannel(channel);
    final joined = await me.waitFor<ChannelJoined>();
    expect(joined, isNotNull, reason: '채널에 들어가야 한다');
    // **한글 채널 이름이 된다** - IRC 는 # 가 필요하고 한글도 안 됐다
    expect(joined!.channel, channel);
    expect(await me.waitFor<UserlistUpdated>(), isNotNull,
        reason: '참여자 목록이 따로 묻지 않고 같이 와야 한다');

    // ---------- 말하기 ----------
    me.events.clear();
    me.session.sendChat(channel, '안녕하세요');
    final said = await me.waitFor<MessageReceived>();
    expect(said, isNotNull, reason: '내가 보낸 말이 돌아와야 한다');
    expect(said!.text, '안녕하세요');
    expect(said.mine, isTrue);
    expect(me.events.whereType<MessageReceived>().length, 1,
        reason: '로컬 에코까지 하면 두 번 보인다');

    // ---------- IRC 가 못 하던 것 ----------
    me.events.clear();
    me.session.setNickname('한글이름');
    final renamed = await me.waitFor<NicknameUpdated>();
    expect(renamed?.nickname, '한글이름',
        reason: 'IRC 서버는 한글 닉네임을 거절했다');

    me.events.clear();
    final long = '가' * 1000; // IRC 는 한 줄 512바이트에서 잘린다
    me.session.sendChat(channel, long);
    final longSaid = await me.waitFor<MessageReceived>();
    expect(longSaid?.text, long, reason: '긴 글이 잘리면 안 된다');

    // ---------- 서버에 어떤 방이 있는지 ----------
    if (atLeast(server, [1, 2, 0])) {
      me.events.clear();
      me.session.requestRoomList();
      final listed = await me.waitFor<RoomListReceived>();
      expect(listed, isNotNull, reason: '방 목록을 받아야 한다');
      expect(listed!.rooms.map((r) => r.name), contains(channel),
          reason: '방금 만든 방이 목록에 있어야 한다');

      // 조용해도 끊기지 않게 - 답이 와야 한다
      me.events.clear();
      me.session.keepalive();
      await Future<void>.delayed(const Duration(seconds: 2));
      expect(me.events.whereType<MessageReceived>(), isEmpty,
          reason: '살아 있는지 묻고 받은 답이 글자로 보이면 안 된다');
    } else {
      print('[건너뜀] 방 목록·살아있나 - 올라간 chat 이 ${server['version']}');
    }

    // ---------- 다시 들어가면 **지난 기록이 같이 온다** ----------
    await me.close();
    final again = Peer(id);
    expect(await again.open(), isTrue);
    again.session.login(password: password);
    expect(await again.waitFor<LoggedIn>(), isNotNull);
    again.events.clear();
    again.session.joinChannel(channel);
    expect(await again.waitFor<ChannelJoined>(), isNotNull);
    // 올 때까지 조금 기다린다 - 입장 응답과 같은 묶음으로 오지만 한 박자 늦을 수 있다
    await again.waitFor<MessageReceived>();
    final history =
        again.events.whereType<MessageReceived>().map((m) => m.text).toList();
    expect(history, contains('안녕하세요'),
        reason: 'IRC 모드는 중계 서버에서 따로 받아와야 했다 - 여기서는 입장과 함께 온다');
    await again.close();
    print('[통과] 가입·입장·말하기·한글 이름·긴 글·지난 기록까지 실제 서버에서 확인');
  }, timeout: const Timeout(Duration(seconds: 120)));

  test('쪽마다 쌓이는 자리가 갈린다', () {
    // 서버에 안 닿아도 확인할 수 있는 것 - 자리 계산에 프로토콜이 들어가는가
    expect(
        relay.roomId(ChatKind.server.wireName, relay.serverChatHost,
            relay.serverChatPort, '일반'),
        isNot(relay.roomId(
            ChatKind.irc.wireName, 'home.pdlab.kr', 6697, '#일반')));
  });
}
