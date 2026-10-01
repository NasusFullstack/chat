/// 진짜 방에 들어가서 한마디 하고 나온다 - 네트워크 길을 끝까지 확인.
///
/// 한 번에 다 본다: 암호화 연결(TLS), 서버가 한 번에 보낸 여러 줄을 갈라내는 것,
/// 로그인(001)에서 확정된 이름 읽기, 채널 입장, 참여자 목록(353/366), 말 보내기,
/// 그리고 **내가 보낸 말이 내 화면에 올라오는가**(IRC 서버는 내 말을 나에게
/// 되돌려주지 않는다).
///
/// **IRC에 붙는 검사는 이 파일 하나뿐이다.** 검사 파일은 동시에 돌기 때문에, 여러
/// 파일이 같이 붙으면 서버가 보호 장치로 연결을 끊는다(실제로 그래서 깨졌다).
///
/// ## 건너뛰는 경우
/// 서버에 못 닿을 때, 그리고 **서버가 우리를 거부할 때**.
///
/// 깃허브에서 돌리면 서버가 막는다 - 클라우드 IP 가 공개 차단 목록에 올라 있어서
/// "Proxy/Drone detected" 로 끊긴다. 우리 코드 문제가 아니므로 실패로 세면 안 된다.
/// 이 길은 개발하는 컴퓨터에서 확인하고, 깃허브에서는 나머지만 본다.
library;

import 'dart:async';
import 'dart:io';
import 'dart:math';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:chupchat/core/emoji.dart';
import 'package:chupchat/core/events.dart';
import 'package:chupchat/core/session.dart';
import 'package:chupchat/net/irc_client.dart';
import 'package:chupchat/net/relay_api.dart';
import 'package:chupchat/net/trusted_certs.dart' as certs;
import 'package:chupchat/core/relay.dart' as relay;

const String host = 'home.pdlab.kr';
const int port = 6697;
const String channel = '#pdlab';

Future<bool> reachable() async {
  try {
    final socket =
        await Socket.connect(host, port, timeout: const Duration(seconds: 6));
    await socket.close();
    return true;
  } on Object {
    return false;
  }
}

void main() {
  // 믿기로 한 인증서는 기기에 적어둔다. 검사에서는 빈 상태로 시작한다
  TestWidgetsFlutterBinding.ensureInitialized();
  SharedPreferences.setMockInitialValues({});

  test('방에 들어가서 한마디 하고 나온다', () async {
    if (!await reachable()) {
      markTestSkipped('서버에 닿지 않아 건너뜀');
      return;
    }

    final sentLines = <String>[];
    final client = IrcClient();
    final joined = Completer<void>();
    final refused = Completer<String>();
    final members = Completer<List<String>>();
    final mine = <String>[];
    ChatSession? session;

    final raw = <String>[];
    client.lines.listen((line) {
      raw.add(line);
      // 서버가 아예 안 받아주는 경우(차단 목록·접속 제한 등). 465 는 '넌 여기 못 온다',
      // ERROR 는 서버가 끊는다는 뜻이다
      if (!refused.isCompleted &&
          (line.contains(' 465 ') || line.startsWith('ERROR'))) {
        refused.complete(line);
      }
      session?.handleLine(line);
    });
    // 처음에는 모르는 인증서라 안 붙는다. 사람이 하는 것처럼 지문을 보고 믿은 뒤
    // 다시 붙는다 - 앱이 실제로 타는 길 그대로다
    var ok = await client.connect(host: host, port: port, secure: true);
    if (!ok && client.pendingFingerprint.isNotEmpty) {
      await certs.trust(host, port, client.pendingFingerprint);
      ok = await client.connect(host: host, port: port, secure: true);
    }
    expect(ok, isTrue, reason: client.lastError);

    session = ChatSession(
      send: (line) {
        sentLines.add(line);
        client.send(line);
      },
      emit: (event) {
        switch (event) {
          case LoggedIn():
            session!.joinChannel(channel);
          case ChannelJoined() when !joined.isCompleted:
            joined.complete();
          case UserlistUpdated(:final users) when !members.isCompleted:
            members.complete(users);
          case MessageReceived(mine: true, :final text):
            mine.add(text);
          default:
            break;
        }
      },
      wantedNick: 'chupphone${Random().nextInt(900) + 100}',
      appVersion: '2.6.4',
    );
    session.login(realname: 'ChupChat mobile');

    final outcome = await Future.any([
      joined.future.then((_) => ''),
      refused.future,
    ]).timeout(const Duration(seconds: 30), onTimeout: () => '시간 초과');

    if (outcome.isNotEmpty) {
      await client.close();
      client.dispose();
      if (outcome == '시간 초과' && raw.isEmpty) {
        // 서버가 한 줄도 안 보냈다. 우리가 로그인은 보냈으니 서버가 조용히 버린
        // 것이다 - 실제로 접속 제한에 걸리면 이렇게 된다(ERROR 조차 안 올 때가 있다).
        // 우리 코드에 대해 아무것도 말해주지 않으므로 실패로 세지 않는다
        markTestSkipped('서버가 아무 답도 없어 건너뜀. 보낸 것:\n'
            '${sentLines.join("\n")}');
        return;
      }
      if (outcome == '시간 초과') {
        fail('채널에 못 들어갔다. 서버가 보낸 것:\n${raw.take(25).join("\n")}');
      }
      // 서버가 우리를 안 받아줬다 - 우리 코드 문제가 아니다
      markTestSkipped('서버가 접속을 거부해 건너뜀: $outcome');
      return;
    }

    final people = await members.future
        .timeout(const Duration(seconds: 20), onTimeout: () => const <String>[]);
    expect(people, isNotEmpty, reason: '참여자 목록(353/366)을 못 받았다');
    expect(people, contains(session.myId), reason: '내가 목록에 있어야 한다');

    session.sendChat(channel, '폰에서 보냅니다. 참여자 목록에 폰 표시 보이나요?');
    // 서버가 내 말을 되돌려주지 않으므로, 화면에 올리는 건 우리가 해야 한다
    expect(mine.length, 1, reason: '내가 보낸 말이 내 화면에 안 올라왔다');

    // 서버에 등록된 이모티콘을 하나 집어서 보낸다 - 받는 쪽은 그림으로 본다
    final files = FileApi(group: relay.groupId('irc', host, port));
    final emoji = await files.sharedEmoji();
    expect(emoji, isNotEmpty, reason: '서버에 등록된 이모티콘이 없다');
    final pick = emoji.first['url']!;
    session.sendChat(channel, formatEmoji(pick));

    // 보낸 그대로 이모티콘으로 읽혀야 한다(주소 글자로 보이면 안 된다)
    final parts = splitEmojiParts(mine.last);
    expect(parts.length, 1);
    expect(parts.first.isEmoji, isTrue, reason: '이모티콘으로 안 읽힌다: ${mine.last}');
    expect(parts.first.value, pick);

    // 누가 "무슨 프로그램 쓰세요?"라고 물으면 답해야 한다 - 그래야 상대 화면에
    // 춥채팅 배지와 폰 표시가 같이 뜬다
    final before = sentLines.length;
    session.handleLine(':누군가!u@h PRIVMSG ${session.myId} :VERSION');
    final answered = sentLines.skip(before).where((l) => l.contains('VERSION')).toList();
    expect(answered, isNotEmpty, reason: '프로그램을 물었는데 답을 안 했다');
    expect(answered.first, startsWith('NOTICE'),
        reason: 'PRIVMSG 로 답하면 서로 되받아치며 무한 반복될 수 있다');
    expect(answered.first, contains('ChupChat Mobile'),
        reason: 'Mobile 이 들어가야 PC에서 폰 표시가 붙는다');

    await Future<void>.delayed(const Duration(seconds: 2));
    session.quit('확인 완료');
    await client.close();
    client.dispose();
  }, timeout: const Timeout(Duration(seconds: 90)));
}
