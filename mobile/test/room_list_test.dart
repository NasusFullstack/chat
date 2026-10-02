/// 서버에 **어떤 방이 있는지 보고 고를 수 있는가**, 그리고 가입은 따로 띄우는가.
///
/// 예전에는 방 이름을 글자로 쳐야 했다. 이름을 모르면 들어갈 방법이 없고, 폰에서
/// 글자를 치는 것은 더 번거롭다.
///
/// 가입도 같은 이야기다 - 로그인 화면에 체크 하나로 뜻이 바뀌면 지금 가입을 하는
/// 건지 들어가는 건지 알기 어렵다. 가입은 한 번뿐이고 들어가기는 매번이다.
library;

import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

import 'package:chupchat/core/events.dart';
import 'package:chupchat/core/server_session.dart';
import 'package:chupchat/core/session.dart';

void main() {
  group('누가 방 목록을 줄 수 있나', () {
    test('서버 채팅은 준다', () {
      final sent = <Map<String, Object?>>[];
      final session =
          ServerSession(send: sent.add, emit: (_) {}, userId: 'mong22');
      expect(session.canListRooms, isTrue);
      session.requestRoomList();
      expect(sent.single, {'cmd': 'channels'});
    });

    test('IRC 는 안 준다 - 큰 서버는 방이 수만 개다', () {
      final sent = <String>[];
      final session =
          ChatSession(send: sent.add, emit: (_) {}, wantedNick: 'mong');
      expect(session.canListRooms, isFalse);
      session.requestRoomList();
      expect(sent, isEmpty, reason: '줄 하나도 나가면 안 된다');
    });
  });

  group('받아서 읽기', () {
    late List<ChatEvent> events;
    late ServerSession session;

    setUp(() {
      events = [];
      session = ServerSession(send: (_) {}, emit: events.add, userId: 'mong22');
    });

    test('쓸 수 없는 줄은 버리고 나머지를 준다', () {
      session.handleIncoming({
        'type': 'channel_list',
        'channels': [
          {'name': '일반', 'users': 3, 'locked': false},
          {'name': '비밀방', 'users': 0, 'locked': true},
          {'users': 9}, // 이름이 없다
          '방이 아니다',
        ],
      });
      final rooms = events.whereType<RoomListReceived>().single.rooms;
      expect(rooms.map((r) => r.name), ['일반', '비밀방']);
      expect(rooms[0].users, 3);
      expect(rooms[1].locked, isTrue);
    });

    test('비밀번호가 걸린 방에는 열쇠를 같이 보낸다', () {
      final sent = <Map<String, Object?>>[];
      final s = ServerSession(send: sent.add, emit: (_) {}, userId: 'mong22');
      s.joinChannel('비밀방', key: '열쇠');
      expect(sent.single, {'cmd': 'join', 'channel': '비밀방', 'key': '열쇠'});
    });

    test('pong 은 화면에 아무 것도 안 띄운다', () {
      // 받았다는 사실 자체가 전부다 - 글자로 보이면 안 된다
      session.handleIncoming({'type': 'pong', 'ts': 1.0});
      expect(events, isEmpty);
    });
  });

  group('화면이 지켜야 하는 것', () {
    test('방 고르기 화면은 **프로토콜을 모른다**', () {
      // "지금 서버 채팅인가"가 아니라 "목록을 줄 수 있나"를 물어야 한다. 그래야
      // 나중에 목록을 줄 수 있는 쪽이 늘어도 화면은 안 바뀐다
      final source = File('lib/ui/room_picker.dart').readAsStringSync();
      expect(source.contains('ChatKind'), isFalse);
      expect(source.contains('canListRooms'), isTrue);
    });

    test('채팅 화면도 여전히 프로토콜을 모른다', () {
      final source = File('lib/ui/chat_page.dart').readAsStringSync();
      expect(source.contains('ChatKind'), isFalse);
    });

    test('가입은 **따로 띄운다**', () {
      // 로그인 화면에 체크 하나로 뜻이 바뀌면 지금 무엇을 하는 건지 알기 어렵다
      expect(File('lib/ui/signup_page.dart').existsSync(), isTrue);
      final login = File('lib/ui/login_page.dart').readAsStringSync();
      expect(login.contains('SignupPage'), isTrue);
      expect(login.contains('_makeAccount'), isFalse,
          reason: '체크 하나로 가입/로그인을 가르던 것은 걷어냈다');
    });

    test('가입 화면은 비밀번호를 **두 번** 받는다', () {
      // 기기에 저장하지 않으므로 오타가 나면 다음에 못 들어온다 - 만들 때 걸러야 한다
      final source = File('lib/ui/signup_page.dart').readAsStringSync();
      expect(source.contains('비밀번호 다시'), isTrue);
      expect(source.contains('비밀번호가 서로 다릅니다'), isTrue);
    });

    test('쪽 고르기는 **상단 탭**이다', () {
      final login = File('lib/ui/login_page.dart').readAsStringSync();
      expect(login.contains('TabBar'), isTrue);
      expect(login.contains('SegmentedButton'), isFalse,
          reason: '박스로 고르던 것은 탭으로 바꿨다');
    });
  });
}
