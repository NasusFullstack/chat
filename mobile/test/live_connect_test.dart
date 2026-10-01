/// 진짜 서버에 붙는가 - TLS, 줄 쪼개짐, 로그인 절차까지 한 번에.
///
/// 화면을 눌러보는 것으로는 이걸 확인할 수 없다. 여기서 보는 것은 **네트워크 길**이다:
/// 암호화 연결이 되는가, 서버가 한 번에 보낸 여러 줄을 제대로 갈라내는가, 001 응답에서
/// 확정된 이름을 읽는가.
///
/// 서버에 못 닿으면 **건너뛴다**(실패로 안 센다). 인터넷 없는 곳에서 검사를 돌릴 수도 있다.
///
/// 채널에는 **일부러 안 들어간다.** 들어가면 그 방 사람들에게 입장 알림이 뜬다 -
/// 확인하자고 남들을 성가시게 할 이유가 없다.
library;

import 'dart:async';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

import 'package:chupchat/core/events.dart';
import 'package:chupchat/core/session.dart';
import 'package:chupchat/net/irc_client.dart';

const String host = 'home.pdlab.kr';
const int port = 6697;

Future<bool> reachable() async {
  try {
    final socket = await Socket.connect(host, port,
        timeout: const Duration(seconds: 6));
    await socket.close();
    return true;
  } on Object {
    return false;
  }
}

void main() {
  test('진짜 서버에 붙어서 로그인까지 된다', () async {
    if (!await reachable()) {
      markTestSkipped('서버에 닿지 않아 건너뜀 ($host:$port)');
      return;
    }

    final client = IrcClient();
    final got = <ChatEvent>[];
    final loggedIn = Completer<String>();

    ChatSession? session;
    client.lines.listen((line) => session?.handleLine(line));

    // 자체 서명 인증서를 쓰는 개인 서버다 - PC 앱도 같은 이유로 넘어가는 길이 있다
    final ok = await client.connect(
      host: host,
      port: port,
      secure: true,
      allowBadCertificate: true,
    );
    expect(ok, isTrue, reason: '연결 실패: ${client.lastError}');

    session = ChatSession(
      send: client.send,
      emit: (event) {
        got.add(event);
        if (event is LoggedIn && !loggedIn.isCompleted) {
          loggedIn.complete(event.userId);
        }
      },
      wantedNick: 'chup_dart_${DateTime.now().millisecondsSinceEpoch % 10000}',
    );
    session.login(realname: 'ChupChat mobile check');

    final name = await loggedIn.future.timeout(
      const Duration(seconds: 30),
      onTimeout: () => '',
    );

    // 채널에는 안 들어가고 바로 나간다
    session.quit('확인 완료');
    await client.close();
    client.dispose();

    expect(name, isNotEmpty,
        reason: '로그인(001)이 안 왔다. 받은 것: '
            '${got.map((e) => e.type).toList()}');
    // 서버가 확정해준 이름을 써야 한다 - 우리가 보낸 것과 다를 수 있다
    expect(session.myId, name);
  }, timeout: const Timeout(Duration(seconds: 60)));
}
