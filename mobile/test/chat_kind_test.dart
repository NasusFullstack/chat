/// IRC 와 서버 채팅이 **안 섞이는가.**
///
/// 사용자가 바란 것이 "둘을 따로 쓴다"라서, 여기서 보는 것은 하나다 - 한쪽을 쓰는
/// 동안 다른 쪽 것이 끼어들지 않는가. 섞이면 이렇게 보인다:
///
/// - IRC 닉네임이 서버 채팅 아이디 칸에 남아 있고, 그대로 보내면 로그인 실패
/// - IRC 방 기록이 서버 방에 보이거나 그 반대
/// - IRC 로 들어가 있던 방에 서버 채팅으로 들어가려 함
///
/// 그리고 **이미 깔려 있는 앱이 기억해둔 것을 잃지 않아야 한다**(v2.6.8 까지는
/// 설정 열쇠가 하나였다).
library;

import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:chupchat/core/chat_port.dart';
import 'package:chupchat/core/relay.dart' as relay;
import 'package:chupchat/login_store.dart';

const String ircHost = 'home.pdlab.kr';
const int ircPort = 6697;

void main() {
  setUp(() {
    TestWidgetsFlutterBinding.ensureInitialized();
    SharedPreferences.setMockInitialValues({});
  });

  group('쌓이는 자리가 갈린다', () {
    test('같은 이름이어도 자리가 다르다', () {
      // 자리 계산에 프로토콜이 들어가는 덕이다 - 안 들어가면 섞인다
      final server = relay.roomId(ChatKind.server.wireName,
          relay.serverChatHost, relay.serverChatPort, '일반');
      final irc = relay.roomId(ChatKind.irc.wireName, ircHost, ircPort, '#일반');
      expect(server, isNot(irc));
    });

    test('서버 채팅 자리는 **고정값**이다', () {
      // PC 의 gui/login_request.py 와 **같은 값**이어야 폰과 PC 가 같은 자리를 본다.
      // 바꾸면 그동안 쌓인 기록·프로필을 통째로 못 찾는다
      expect(relay.serverChatHost, 'chupchat');
      expect(relay.serverChatPort, 0);
    });

    test('자리 계산에 쓰는 이름이 PC 와 같다', () {
      // PC 는 chat_core/protocols/*.py 의 `name`
      expect(ChatKind.irc.wireName, 'irc');
      expect(ChatKind.server.wireName, 'server');
    });
  });

  group('기억해둔 접속 정보가 쪽마다 따로다', () {
    test('한쪽에 적어도 다른 쪽은 안 바뀐다', () async {
      await saveLastLogin(
          kind: ChatKind.irc,
          host: ircHost,
          port: ircPort,
          nick: 'mong',
          secure: true);
      await saveLastLogin(
          kind: ChatKind.server,
          host: relay.serverChatHost,
          port: relay.serverChatPort,
          nick: 'mong22',
          secure: true);

      expect((await loadLastLogin(ChatKind.irc)).nick, 'mong');
      expect((await loadLastLogin(ChatKind.server)).nick, 'mong22');
    });

    test('서버 채팅은 주소를 사람에게 받지 않는다', () async {
      final last = await loadLastLogin(ChatKind.server);
      expect(last.host, relay.serverChatHost);
      expect(last.port, relay.serverChatPort);
    });

    test('서버 채팅은 **알아서 들어갈 수 없다**', () async {
      // 비밀번호를 기기에 안 남기기 때문이다. 켜 둘 수 있게 보여주면 거짓말이 된다
      await saveLastLogin(
          kind: ChatKind.server,
          host: relay.serverChatHost,
          port: relay.serverChatPort,
          nick: 'mong22',
          secure: true,
          remember: true,
          auto: true);
      expect((await loadLastLogin(ChatKind.server)).canAuto, isFalse);
    });

    test('IRC 는 예전처럼 알아서 들어간다', () async {
      await saveLastLogin(
          kind: ChatKind.irc,
          host: ircHost,
          port: ircPort,
          nick: 'mong',
          secure: true);
      expect((await loadLastLogin(ChatKind.irc)).canAuto, isTrue);
    });

    test('지난번에 어느 쪽으로 들어갔는지 기억한다', () async {
      expect(await loadLastKind(), ChatKind.irc, reason: '처음에는 IRC');
      await saveLastLogin(
          kind: ChatKind.server,
          host: relay.serverChatHost,
          port: relay.serverChatPort,
          nick: 'mong22',
          secure: true);
      expect(await loadLastKind(), ChatKind.server);
    });
  });

  group('이미 깔려 있는 앱이 잃지 않는다', () {
    test('옛 열쇠에 적힌 이름을 IRC 쪽이 되읽는다', () async {
      // v2.6.8 까지는 열쇠가 하나였다(login_nick). 그걸 못 읽으면 쓰던 사람이
      // 업데이트하자마자 이름을 다시 쳐야 한다
      SharedPreferences.setMockInitialValues({
        'login_host': 'irc.example.com',
        'login_port': 6667,
        'login_nick': '옛이름',
        'login_secure': false,
        'login_remember': true,
        'login_auto': true,
      });
      final last = await loadLastLogin(ChatKind.irc);
      expect(last.nick, '옛이름');
      expect(last.host, 'irc.example.com');
      expect(last.port, 6667);
      expect(last.secure, isFalse);
      expect(last.canAuto, isTrue);
    });

    test('옛 이름이 서버 채팅 쪽으로는 **새지 않는다**', () async {
      SharedPreferences.setMockInitialValues({'login_nick': '옛이름'});
      expect((await loadLastLogin(ChatKind.server)).nick, isEmpty);
    });

    test('IRC 채널 목록 열쇠가 예전과 글자 그대로 같다', () async {
      // 적어둔 채널 목록을 잃으면 켤 때 아무 방에도 안 들어가 있다
      final legacyKey =
          'rooms_${relay.groupId('irc', ircHost, ircPort)}_mong';
      SharedPreferences.setMockInitialValues({
        legacyKey: ['#일반', '#잡담'],
      });
      expect(await loadRooms(ircHost, ircPort, 'mong', kind: ChatKind.irc),
          ['#일반', '#잡담']);
    });
  });

  group('채널 목록도 쪽마다 따로다', () {
    test('IRC 방과 서버 방이 안 섞인다', () async {
      await saveRooms(ircHost, ircPort, 'mong', ['#일반'], kind: ChatKind.irc);
      await saveRooms(relay.serverChatHost, relay.serverChatPort, 'mong',
          ['한글방'],
          kind: ChatKind.server);

      expect(await loadRooms(ircHost, ircPort, 'mong', kind: ChatKind.irc),
          ['#일반']);
      expect(
          await loadRooms(relay.serverChatHost, relay.serverChatPort, 'mong',
              kind: ChatKind.server),
          ['한글방']);
    });

    test('이름이 다르면 방도 따로 기억한다', () async {
      await saveRooms(ircHost, ircPort, 'mong', ['#일반'], kind: ChatKind.irc);
      expect(await loadRooms(ircHost, ircPort, 'duri', kind: ChatKind.irc),
          isEmpty);
    });
  });

  group('화면은 어느 쪽인지 모른다', () {
    test('채팅 화면에 프로토콜 분기가 없다', () {
      // 알게 되면 `if 서버면 ...` 이 화면 곳곳으로 번지고, 한쪽을 고칠 때 다른 쪽이
      // 깨진다. 프로토콜 차이는 판단하는 쪽(core/)이 갖는다
      final source = File('lib/ui/chat_page.dart').readAsStringSync();
      expect(source.contains('ChatKind'), isFalse,
          reason: '채팅 화면은 IRC 인지 서버 채팅인지 몰라야 한다');
    });

    test('로그인 화면만 고르는 일을 안다', () {
      // 고르는 것은 로그인 화면의 일이다 - 여기만 알아야 한다
      final source = File('lib/ui/login_page.dart').readAsStringSync();
      expect(source.contains('ChatKind'), isTrue);
    });

    test('상태는 통로를 직접 만들지 않고 약속으로 쥔다', () {
      // `ChatLink` 로 쥐어야 화면·상태가 TLS 소켓인지 WebSocket 인지 모른다
      final source = File('lib/app_state.dart').readAsStringSync();
      expect(source.contains('ChatLink get _client'), isTrue);
      expect(source.contains('ChatPort? _session'), isTrue);
    });
  });
}
