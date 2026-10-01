/// 지난번 접속을 기억하는가 - 이름과 **들어가 있던 채널**.
///
/// 폰에서 글자를 치는 것은 번거로워서, 켤 때마다 이름과 채널을 다시 받으면 그것만으로
/// 안 쓰게 된다. 반대로 **끄기로 한 사람의 이름이 남아 있으면** 안 된다(둘이 번갈아
/// 쓰는 경우).
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:chupchat/app_state.dart';
import 'package:chupchat/core/events.dart';
import 'package:chupchat/login_store.dart';

const String host = 'home.pdlab.kr';
const int port = 6697;

void main() {
  setUp(() {
    TestWidgetsFlutterBinding.ensureInitialized();
    SharedPreferences.setMockInitialValues({});
  });

  test('처음 켜면 우리 서버가 적혀 있고 이름은 비어 있다', () async {
    final last = await loadLastLogin();
    expect(last.host, host);
    expect(last.port, port);
    expect(last.nick, isEmpty);
    expect(last.canAuto, isFalse, reason: '이름이 없으면 알아서 들어갈 수 없다');
  });

  test('기억하기를 켜면 이름이 남고 다음엔 알아서 들어간다', () async {
    await saveLastLogin(
        host: host, port: port, nick: 'mong22', secure: true, remember: true);
    final last = await loadLastLogin();
    expect(last.nick, 'mong22');
    expect(last.canAuto, isTrue);
  });

  test('기억하기를 끄면 이름을 지운다', () async {
    await saveLastLogin(
        host: host, port: port, nick: 'mong22', secure: true, remember: true);
    await saveLastLogin(
        host: host, port: port, nick: 'mong22', secure: true, remember: false);

    final last = await loadLastLogin();
    expect(last.nick, isEmpty, reason: '끈 사람의 이름이 남아 있으면 안 된다');
    expect(last.canAuto, isFalse);
  });

  test('알아서 들어가기를 끄면 이름은 남지만 자동은 아니다', () async {
    await saveLastLogin(
        host: host,
        port: port,
        nick: 'mong22',
        secure: true,
        remember: true,
        auto: false);
    final last = await loadLastLogin();
    expect(last.nick, 'mong22', reason: '이름은 다시 치지 않아도 되게 남는다');
    expect(last.canAuto, isFalse);
  });

  group('채널은 이름마다 따로 기억한다', () {
    test('같은 이름이면 그대로 돌려준다', () async {
      await saveRooms(host, port, 'mong22', ['#pdlab', '#일반']);
      expect(await loadRooms(host, port, 'mong22'), ['#pdlab', '#일반']);
    });

    test('다른 이름으로 켜면 남의 채널에 들어가지 않는다', () async {
      await saveRooms(host, port, 'mong22', ['#pdlab']);
      expect(await loadRooms(host, port, '두리'), isEmpty,
          reason: '같은 폰을 두 이름으로 쓸 수 있다');
    });

    test('다른 서버의 채널과도 섞이지 않는다', () async {
      await saveRooms(host, port, 'mong22', ['#pdlab']);
      expect(await loadRooms('irc.example.com', 6697, 'mong22'), isEmpty);
    });

    test('대소문자가 달라도 같은 사람으로 본다', () async {
      await saveRooms(host, port, 'Mong22', ['#pdlab']);
      expect(await loadRooms(host, port, 'mong22'), ['#pdlab'],
          reason: 'IRC 닉네임은 대소문자를 가리지 않는다');
    });
  });

  group('실제로 다시 들어가는가', () {
    test('기억해둔 채널에 들어간다', () async {
      await saveRooms(host, port, 'mong22', ['#pdlab', '#일반']);
      final asked = <String>[];
      final state = AppState()
        ..host = host
        ..port = port
        ..onJoinForTest = asked.add;
      state.handleEvent(const LoggedIn('mong22'));

      await state.rejoinSaved();
      expect(asked, ['#pdlab', '#일반']);
    });

    test('이미 들어가 있는 채널은 또 들어가지 않는다', () async {
      final asked = <String>[];
      final state = AppState()
        ..host = host
        ..port = port
        ..onJoinForTest = asked.add;
      state.handleEvent(const LoggedIn('mong22'));
      state.handleEvent(const ChannelJoined('#pdlab', '입장'));
      // 지난 실행에서 적어둔 목록(지금 상태를 적고 나서 들어온 것처럼)
      await state.roomsWritten;
      await saveRooms(host, port, 'mong22', ['#pdlab', '#일반']);

      await state.rejoinSaved();
      expect(asked, ['#일반'], reason: '같은 방에 두 번 들어가면 지난 기록이 두 번 쌓인다');
    });

    test('들어가고 나가면 기억이 따라 바뀐다', () async {
      final state = AppState()
        ..host = host
        ..port = port;
      state.handleEvent(const LoggedIn('mong22'));
      state.handleEvent(const ChannelJoined('#pdlab', '입장'));
      state.handleEvent(const ChannelJoined('#일반', '입장'));
      await state.roomsWritten;
      expect(await loadRooms(host, port, 'mong22'), ['#pdlab', '#일반']);

      state.handleEvent(const ChannelLeft('#일반'));
      await state.roomsWritten;
      expect(await loadRooms(host, port, 'mong22'), ['#pdlab'],
          reason: '나온 방에 다음에 또 들어가면 안 된다');
    });
  });
}
