/// 서버 채팅 판단 - **IRC 때 하던 우회를 여기서도 하고 있지 않은가.**
///
/// 이 프로토콜을 만든 이유가 "IRC 제약을 걷어내는 것"이라, 그 제약 때문에 생겼던
/// 동작이 여기 남아 있으면 안 된다. PC 쪽 `tests/test_server_protocol.py` 와 같은
/// 것을 본다 - **두 앱이 같은 대화를 다르게 해석하면 그게 가장 찾기 어렵다.**
///
/// 소켓도 화면도 없이 돈다. 판단은 그렇게 만들어져 있다.
library;

import 'package:flutter_test/flutter_test.dart';

import 'package:chupchat/core/battle_protocol.dart' as bp;
import 'package:chupchat/core/events.dart';
import 'package:chupchat/core/server_session.dart';

/// 세션 하나 - 보낸 것과 일어난 일을 모아둔다.
class Fake {
  Fake() {
    session = ServerSession(
      send: sent.add,
      emit: events.add,
      userId: 'mong22',
    );
  }

  final List<Map<String, Object?>> sent = [];
  final List<ChatEvent> events = [];
  late final ServerSession session;

  List<T> kinds<T>() => events.whereType<T>().toList();

  /// 들어가서 이야기할 준비까지 - 반복되는 앞단을 줄인다
  void getIn({String channel = '일반'}) {
    session.handleIncoming({'type': 'auth_result', 'ok': true, 'id': 'mong22'});
    session.handleIncoming(
        {'type': 'channel_result', 'ok': true, 'channel': channel});
    sent.clear();
    events.clear();
  }
}

void main() {
  group('들어가기', () {
    test('로그인을 보낸다', () {
      final f = Fake();
      f.session.login(password: '비밀1234');
      expect(f.sent.last['cmd'], 'login');
      expect(f.sent.last['id'], 'mong22');
    });

    test('내 자리를 받고, 서버가 들고 있던 이름과 아이콘이 따라온다', () {
      // 기기를 바꿔도 그대로여야 한다 - IRC 는 아이콘을 각자 기기에 들고 있었다
      final f = Fake();
      f.session.handleIncoming({
        'type': 'auth_result',
        'ok': true,
        'id': 'mong22',
        'nick': '몽키',
        'avatar': 'AAAA',
      });
      expect(f.session.myId, 'mong22');
      expect(f.kinds<LoggedIn>().single.userId, 'mong22');
      expect(f.kinds<NicknameUpdated>().single.nickname, '몽키');
      expect(f.kinds<AvatarUpdated>().single.avatar, 'AAAA');
    });

    test('비밀번호가 틀리면 기다리는 쪽에 끝났다고 알린다', () {
      // 안 알리면 로그인 버튼이 **영원히 돌아간다** - 사람은 앱이 멈춘 줄 안다
      final f = Fake();
      f.session.handleIncoming(
          {'type': 'auth_result', 'ok': false, 'text': '아이디나 비밀번호가 다릅니다'});
      expect(f.kinds<ConnectionClosed>().single.text, contains('비밀번호'));
      expect(f.session.myId, isEmpty);
    });

    test('가입이 끝나면 **이어서 알아서 로그인한다**', () {
      // 사람이 비밀번호를 두 번 칠 일이 없어야 한다
      final f = Fake();
      f.session.register('비밀1234');
      expect(f.sent.single['cmd'], 'register');
      f.session.handleIncoming({'type': 'auth_result', 'ok': true, 'made': true});
      expect(f.sent.last['cmd'], 'login');
      expect(f.sent.last['pw'], '비밀1234');
      expect(f.kinds<LoggedIn>(), isEmpty, reason: '가입만으로 들어간 것은 아니다');
    });

    test('한글 채널 이름을 그대로 보낸다 (IRC 는 # 가 필요했고 한글은 안 됐다)', () {
      final f = Fake();
      f.session.joinChannel('한글방');
      expect(f.sent.single['cmd'], 'join');
      expect(f.sent.single['channel'], '한글방');
    });
  });

  group('입장 응답에 지난 기록과 참여자가 같이 온다', () {
    late Fake f;

    setUp(() {
      f = Fake();
      f.session.handleIncoming(
          {'type': 'auth_result', 'ok': true, 'id': 'mong22'});
      f.sent.clear();
      f.events.clear();
      f.session.handleIncoming({
        'type': 'channel_result',
        'ok': true,
        'channel': '일반',
        'history': [
          {'sender': 'duri', 'text': '어제 한 말', 'ts': 1.0},
          {'sender': 'mong22', 'text': '내가 한 말', 'ts': 2.0},
        ],
        'users': [
          {'id': 'mong22', 'nick': '몽키', 'avatar': 'AAAA'},
          {'id': 'duri', 'nick': '두리', 'avatar': 'BBBB'},
        ],
      });
    });

    test('채널에 들어간 것으로 본다', () {
      expect(f.kinds<ChannelJoined>().single.channel, '일반');
    });

    test('지난 이야기가 화면에 올라오고 내 것은 내 것으로 표시된다', () {
      final said = f.kinds<MessageReceived>();
      expect(said.map((m) => m.text), ['어제 한 말', '내가 한 말']);
      expect(said[0].mine, isFalse);
      expect(said[1].mine, isTrue);
    });

    test('참여자 아이콘과 이름이 **같이** 온다', () {
      // IRC 는 CTCP 로 따로 물어야 했고 아이콘은 300자씩 쪼개야 했다 -
      // 조각이 하나라도 빠지면 아무것도 안 떴다
      expect(f.kinds<UserlistUpdated>().single.users, ['mong22', 'duri']);
      final faces = {for (final e in f.kinds<AvatarUpdated>()) e.userId: e.avatar};
      expect(faces, {'mong22': 'AAAA', 'duri': 'BBBB'});
      final names = {
        for (final e in f.kinds<NicknameUpdated>()) e.userId: e.nickname
      };
      expect(names, {'mong22': '몽키', 'duri': '두리'});
    });

    test('**아무에게도 묻지 않는다**', () {
      expect(f.sent, isEmpty,
          reason: 'IRC 는 여기서 참여자 수만큼 CTCP 를 보내다 서버에 끊겼다');
    });
  });

  group('말하기', () {
    test('보낼 때는 화면에 안 올린다 (서버가 돌려준다)', () {
      // 로컬 에코를 하면 서버가 돌려줄 때 **두 번 보인다**
      final f = Fake()..getIn();
      f.session.sendChat('일반', '안녕');
      expect(f.kinds<MessageReceived>(), isEmpty);
      expect(f.sent.single, {'cmd': 'msg', 'channel': '일반', 'text': '안녕'});
    });

    test('서버가 돌려준 뒤에야 한 번 보인다', () {
      final f = Fake()..getIn();
      f.session.sendChat('일반', '안녕');
      f.session.handleIncoming({
        'type': 'chat',
        'channel': '일반',
        'sender': 'mong22',
        'text': '안녕',
      });
      final said = f.kinds<MessageReceived>();
      expect(said.length, 1);
      expect(said.single.mine, isTrue);
    });

    test('긴 글을 쪼개지 않는다 (IRC 는 512바이트에서 잘렸다)', () {
      final f = Fake()..getIn();
      final long = '가' * 1000;
      f.session.sendChat('일반', long);
      expect(f.sent.length, 1);
      expect(f.sent.single['text'], long);
    });

    test('큰 아이콘도 한 줄로 보낸다 (IRC 는 300자씩 나눴다)', () {
      final f = Fake()..getIn();
      f.session.setAvatar('A' * 5000);
      expect(f.sent.length, 1);
      expect((f.sent.single['avatar'] as String).length, 5000);
    });

    test('한글 이름을 그대로 보낸다 (IRC 서버는 거절했다)', () {
      final f = Fake()..getIn();
      f.session.setNickname('한글이름');
      expect(f.sent.single, {'cmd': 'set_nickname', 'nick': '한글이름'});
    });

    test('내 이름이 불리면 표시한다 - 아이디로도, 보이는 이름으로도', () {
      final f = Fake();
      f.session.handleIncoming({
        'type': 'auth_result',
        'ok': true,
        'id': 'mong22',
        'nick': '몽키',
      });
      f.events.clear();
      f.session.handleIncoming(
          {'type': 'chat', 'channel': '일반', 'sender': 'duri', 'text': '@mong22 야'});
      f.session.handleIncoming(
          {'type': 'chat', 'channel': '일반', 'sender': 'duri', 'text': '@몽키 야'});
      expect(f.kinds<MessageReceived>().map((m) => m.isMention), [true, true]);
    });
  });

  group('IRC 에서 못 하던 것', () {
    test('귓속말이 보고 있는 채널에 뜬다', () {
      final f = Fake()..getIn();
      f.session.handleIncoming({
        'type': 'whisper',
        'sender': 'duri',
        'to': 'mong22',
        'text': '둘만 아는 얘기',
      });
      final said = f.kinds<MessageReceived>().single;
      expect(said.sender, contains('귓속말'));
      expect(said.channel, '일반');
      expect(said.mine, isFalse);
    });

    test('내가 보낸 귓속말은 받는 사람 이름으로 남는다', () {
      final f = Fake()..getIn();
      f.session.handleIncoming({
        'type': 'whisper',
        'sender': 'mong22',
        'to': 'duri',
        'text': '나만 아는 얘기',
      });
      final said = f.kinds<MessageReceived>().single;
      expect(said.sender, startsWith('duri'));
      expect(said.mine, isTrue);
    });

    test('남이 이름이나 아이콘을 바꾸면 따라온다', () {
      final f = Fake()..getIn();
      f.session.handleIncoming(
          {'type': 'member_nickname', 'id': 'duri', 'nick': '두리새이름'});
      f.session.handleIncoming(
          {'type': 'member_avatar', 'id': 'duri', 'avatar': 'CCCC'});
      expect(f.kinds<NicknameUpdated>().single.nickname, '두리새이름');
      expect(f.kinds<AvatarUpdated>().single.avatar, 'CCCC');
    });
  });

  group('새면 안 되는 것', () {
    test('전투 방 알림이 글자로 안 보인다', () {
      // 우리끼리 쓰는 숨김 프레임이 채팅으로 새면 안 된다(CLAUDE.md 2-2).
      // 예전에 잘린 base64 가 채널에 쓰레기로 쏟아진 적이 있다
      final f = Fake()..getIn();
      final room = bp.newRoom();
      f.session.handleIncoming({
        'type': 'chat',
        'channel': '일반',
        'sender': 'duri',
        'text': bp.formatRoomNotice(room),
      });
      expect(f.kinds<MessageReceived>(), isEmpty);
      final opened = f.kinds<BattleRoomOpened>().single;
      expect(opened.room, room);
      expect(opened.host, 'duri');
    });

    test('내가 연 방은 나에게 다시 열리지 않는다', () {
      final f = Fake()..getIn();
      f.session.announceBattleRoom('일반', 'a1b2c3');
      expect(f.sent.single['cmd'], 'msg', reason: '채팅으로 보내되 글자로는 안 보인다');
      f.session.handleIncoming({
        'type': 'chat',
        'channel': '일반',
        'sender': 'mong22',
        'text': f.sent.single['text'] as String,
      });
      expect(f.kinds<BattleRoomOpened>(), isEmpty);
      expect(f.kinds<MessageReceived>(), isEmpty);
    });

    test('모르는 종류를 받아도 죽지 않는다', () {
      // 서버가 새 것을 보내도 옛 앱이 살아 있어야 한다
      final f = Fake()..getIn();
      f.session.handleIncoming({'type': '그런건없다', 'text': '뭐'});
      f.session.handleIncoming('줄 하나');
      f.session.handleIncoming(42);
      expect(f.events, isEmpty);
    });

    test('빈 아이콘은 "지웠다"로 읽는다', () {
      final f = Fake()..getIn();
      f.session.handleIncoming(
          {'type': 'member_avatar', 'id': 'duri', 'avatar': ''});
      expect(f.kinds<AvatarUpdated>().single.avatar, isEmpty);
    });
  });

  group('아이디·비밀번호를 보내기 전에 막는다', () {
    test('서버와 같은 규칙이다', () {
      // jsserv features/chat.py: 아이디 ^[A-Za-z0-9_.-]{2,24}$, 비밀번호 4~128
      expect(accountProblem('mong22', '비밀1234'), isEmpty);
      expect(accountProblem('a.b-c_d', '1234'), isEmpty);
      expect(accountProblem('', '1234'), contains('아이디'));
      expect(accountProblem('a', '1234'), contains('2~24'));
      expect(accountProblem('a' * 25, '1234'), contains('2~24'));
      expect(accountProblem('한글아이디', '1234'), contains('영문'));
      expect(accountProblem('mong22', '123'), contains('4자'));
      expect(accountProblem('mong22', 'a' * 129), contains('깁니다'));
    });
  });
}
