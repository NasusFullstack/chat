/// 끊기면 **다시 붙는가**, 그리고 일부러 끊었을 때는 **안 붙는가**.
///
/// 폰은 신호가 끊기는 자리가 PC 보다 훨씬 많다(지하철·엘리베이터). 다시 안 붙으면
/// 사람은 죽은 채팅 화면을 보게 되고 앱을 끄고 다시 켜는 수밖에 없다.
///
/// 반대쪽도 못 박아 둔다: **로그아웃했는데 다시 들어가면 안 된다.** PC 에서 실제로
/// 겪은 사고다(CLAUDE.md 10번 - 로그아웃하자마자 방금 나온 계정으로 다시 들어갔다).
library;

import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

import 'package:chupchat/net/reconnect.dart';

void main() {
  test('듣는 사람은 한 번만 붙인다', () {
    // 다시 붙을 때마다 listen 을 또 하면 듣는 사람이 하나씩 늘어나서 **같은 줄을
    // 두 번, 세 번 해석한다**(메시지가 두 번 보인다). 인증서를 믿고 다시 붙는
    // 경우에 바로 겪는 일이라, 소스에서 못 박아 둔다.
    //
    // 소켓 없이 확인할 방법이 이것뿐이다 - 진짜 서버를 띄워야 재현되는 종류라
    // 평소 검사에서는 안 걸린다.
    //
    // **통로가 둘이 된 뒤로 더 중요해졌다**(IRC / 서버 채팅). 한쪽을 거는 코드를
    // 복사해 다른 쪽을 걸면 손이 미끄러지기 쉬운 자리다
    final source = File('lib/app_state.dart').readAsStringSync();
    final listens = RegExp(r'\.(state|incoming|lines)\.listen')
        .allMatches(source)
        .toList();
    expect(listens.length, 2,
        reason: '듣는 곳은 상태 스트림과 받은 것 스트림 하나씩이다'
            ' (통로별로 또 쓰지 말고 _listenTo 하나를 쓴다)');

    final connectAt = source.indexOf('Future<bool> connect(');
    expect(connectAt, greaterThan(0));
    for (final found in listens) {
      expect(found.start, lessThan(connectAt),
          reason: 'connect() 안에서 듣기 시작하면 다시 붙을 때마다 하나씩 늘어난다');
    }

    // **두 통로 다 걸려 있어야 한다.** 한쪽을 빼먹으면 그 모드에서만 아무 말도
    // 안 들어오는데, 다른 모드는 멀쩡해서 "서버가 이상하다"로 오해하게 된다
    final calls =
        RegExp(r'_listenTo\(ChatKind\.(irc|server),').allMatches(source).toList();
    expect(calls.map((m) => m.group(1)).toSet(), {'irc', 'server'},
        reason: '통로 둘 다 한 번씩 듣기 시작해야 한다');
    // 걸어두는 일 자체도 **connect() 밖**이어야 한다. 안에서 부르면 위 `.listen`
    // 개수는 그대로여서 눈에 안 띄는데 듣는 사람은 접속마다 늘어난다
    for (final call in calls) {
      expect(call.start, lessThan(connectAt),
          reason: '_listenTo 를 connect() 안에서 부르면 다시 붙을 때마다 늘어난다');
    }
  });

  group('언제 다시 붙나', () {
    test('시도할수록 간격이 늘어난다', () {
      expect(reconnectDelay(1), const Duration(seconds: 3));
      expect(reconnectDelay(2), const Duration(seconds: 6));
      expect(reconnectDelay(3), const Duration(seconds: 9));
    });

    test('아무리 늘어도 상한을 넘지 않는다', () {
      expect(reconnectDelay(100), reconnectMax,
          reason: '죽은 서버를 같은 속도로 계속 두드리지 않되, 영영 안 하면 안 된다');
    });

    test('PC 와 같은 숫자다', () {
      // 한쪽만 금방 포기하면 "폰만 자꾸 끊긴다"가 된다.
      // gui/theme.py: RECONNECT_BASE_MS=3000 / MAX_MS=30000 / MAX_ATTEMPTS=10
      expect(reconnectBase, const Duration(milliseconds: 3000));
      expect(reconnectMax, const Duration(milliseconds: 30000));
      expect(reconnectMaxAttempts, 10);
    });
  });

  group('정책대로 움직이는가', () {
    test('끊기면 시작하고 돌아갈 방을 기억한다', () {
      final said = <String>[];
      var tries = 0;
      final policy = ReconnectPolicy(
        connectNow: () async {
          tries += 1;
          return false;
        },
        notify: said.add,
      );

      expect(policy.start(['#pdlab', '#일반']), isTrue);
      expect(policy.active, isTrue);
      expect(policy.pendingRooms, ['#pdlab', '#일반']);
      expect(said.first.contains('끊어졌습니다'), isTrue,
          reason: '조용히 재시도하면 먹통으로 보인다');
      expect(tries, 0, reason: '예약만 걸고 바로 두드리지는 않는다');
      policy.cancel();
    });

    test('이미 하고 있으면 또 시작하지 않는다', () {
      final policy = ReconnectPolicy(
          connectNow: () async => false, notify: (_) {});
      expect(policy.start(['#a']), isTrue);
      expect(policy.start(['#b']), isFalse);
      expect(policy.pendingRooms, ['#a'], reason: '처음 기억한 방을 지켜야 한다');
      policy.cancel();
    });

    test('한도를 넘으면 포기하고 사람에게 알린다', () {
      final said = <String>[];
      final policy = ReconnectPolicy(
          connectNow: () async => false, notify: said.add);
      policy.start(['#a']);
      for (var i = 0; i < reconnectMaxAttempts + 2; i++) {
        policy.schedule();
      }
      expect(policy.active, isFalse);
      expect(said.last.contains('다시 연결하지 못했습니다'), isTrue);
      policy.cancel();
    });

    test('다시 붙으면 돌아갈 방을 돌려주고 끝난다', () {
      final said = <String>[];
      final policy = ReconnectPolicy(
          connectNow: () async => true, notify: said.add);
      policy.start(['#pdlab']);

      expect(policy.succeeded(), ['#pdlab']);
      expect(policy.active, isFalse);
      expect(policy.attempt, 0);
      expect(policy.pendingRooms, isEmpty, reason: '다 돌아갔으면 비워야 한다');
      expect(said.last, '다시 연결되었습니다.');
    });

    test('일부러 끊으면 다시 붙지 않는다', () {
      var tries = 0;
      final policy = ReconnectPolicy(
        connectNow: () async {
          tries += 1;
          return false;
        },
        notify: (_) {},
      );
      policy.start(['#a']);
      policy.cancel();

      policy.tryNow();      // 앱으로 돌아와도
      expect(tries, 0, reason: '로그아웃했는데 방금 나온 이름으로 다시 들어가면 안 된다');
      expect(policy.active, isFalse);
      expect(policy.pendingRooms, isEmpty);
    });

    test('앱으로 돌아오면 기다리지 않고 바로 해본다', () {
      var tries = 0;
      final policy = ReconnectPolicy(
        connectNow: () async {
          tries += 1;
          return false;
        },
        notify: (_) {},
      );
      policy.start(['#a']);
      policy.tryNow();
      expect(tries, 1, reason: '30초짜리 예약을 기다리면 그동안 먹통처럼 보인다');
      policy.cancel();
    });
  });
}
