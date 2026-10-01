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
/// 서버에 못 닿으면 건너뛴다.
library;

import 'dart:async';
import 'dart:io';
import 'dart:math';

import 'package:flutter_test/flutter_test.dart';

import 'package:chupchat/core/emoji.dart';
import 'package:chupchat/core/events.dart';
import 'package:chupchat/core/session.dart';
import 'package:chupchat/net/irc_client.dart';
import 'package:chupchat/net/relay_api.dart';
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
  test('방에 들어가서 한마디 하고 나온다', () async {
    if (!await reachable()) {
      markTestSkipped('서버에 닿지 않아 건너뜀');
      return;
    }

    final client = IrcClient();
    final joined = Completer<void>();
    final members = Completer<List<String>>();
    final mine = <String>[];
    ChatSession? session;

    final raw = <String>[];
    client.lines.listen((line) {
      raw.add(line);
      session?.handleLine(line);
    });
    final ok = await client.connect(
      host: host,
      port: port,
      secure: true,
      allowBadCertificate: true,
    );
    expect(ok, isTrue, reason: client.lastError);

    session = ChatSession(
      send: client.send,
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
    );
    session.login(realname: 'ChupChat mobile');

    await joined.future.timeout(const Duration(seconds: 30),
        onTimeout: () => fail('채널에 못 들어갔다. 서버가 보낸 것:\n'
            '${raw.take(25).join("\n")}'));

    final people = await members.future
        .timeout(const Duration(seconds: 20), onTimeout: () => const <String>[]);
    expect(people, isNotEmpty, reason: '참여자 목록(353/366)을 못 받았다');
    expect(people, contains(session.myId), reason: '내가 목록에 있어야 한다');

    session.sendChat(channel, '빵길허접');
    // 서버가 내 말을 되돌려주지 않으므로, 화면에 올리는 건 우리가 해야 한다
    expect(mine, ['빵길허접'], reason: '내가 보낸 말이 내 화면에 안 올라왔다');

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

    await Future<void>.delayed(const Duration(seconds: 2));
    session.quit('확인 완료');
    await client.close();
    client.dispose();
  }, timeout: const Timeout(Duration(seconds: 90)));
}
