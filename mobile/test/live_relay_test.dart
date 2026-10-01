/// 중계 서버 네 기능이 **진짜로** 도는가 - 올리고, 받아오고, 얼굴까지.
///
/// 흉내가 아니라 실제 서버에 대고 한다. 여기서 보려는 것은 PC가 올린 것을 모바일이
/// 읽을 수 있는가인데, 그건 가짜 서버로는 확인할 수 없다.
///
/// 서버에 못 닿으면 **건너뛴다**(실패로 안 센다).
library;

import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;

import 'package:chupchat/core/relay.dart' as relay;
import 'package:chupchat/net/relay_api.dart';

/// 아무 데도 안 쓰이는 가짜 서버 이름 - 진짜 방 기록을 건드리지 않으려고.
String freshHost() => 'mobile-check-${DateTime.now().millisecondsSinceEpoch}.invalid';

Future<bool> reachable() async {
  try {
    final r = await http
        .get(Uri.parse(relay.logsUrl))
        .timeout(const Duration(seconds: 8));
    return r.statusCode == 200;
  } on Object {
    return false;
  }
}

/// 진짜 PNG 한 장(8x8 초록). 서버가 **내용을 보고** 그림인지 가리므로 그럴듯한
/// 바이트로는 안 된다 - 깨진 PNG를 넣었더니 서버가 제대로 거절했다.
Uint8List tinyPng() => base64Decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAgAAAAICAIAAABLbSncAAAAFElEQVR4nGOUWxXFgA0wYRUdtBIA'
    '5xgBMtM6Z3YAAAAASUVORK5CYII=');

void main() {
  late bool alive;

  setUpAll(() async {
    alive = await reachable();
  });

  test('놓친 대화를 올리고 도로 받아온다', () async {
    if (!alive) {
      markTestSkipped('서버에 닿지 않아 건너뜀');
      return;
    }
    final host = freshHost();
    final logs = ChatLogApi('irc', host, 6697);
    final now = DateTime.now().millisecondsSinceEpoch / 1000;

    logs.record('#방', '몽키', '아무도 없을 때 한 말', now - 60);
    logs.record('#방', '두리', '이것도', now - 50);
    await logs.flush();

    final missed = await logs.missed('#방', now - 3600);
    final texts = missed.map((line) => line['text']).toList();
    expect(texts, contains('아무도 없을 때 한 말'));
    expect(texts, contains('이것도'), reason: '내가 보낸 것도 기록에 남아야 한다');

    // 이미 다 본 뒤라면 아무것도 안 줘야 한다
    final nothing = await logs.missed('#방', now + 30);
    expect(nothing, isEmpty);

    // 남이 같은 대화를 올려도 겹쳐 보이면 안 된다
    final twin = ChatLogApi('irc', host, 6697);
    twin.record('#방', '몽키', '아무도 없을 때 한 말', now - 59.6);
    twin.record('#방', '두리', '이것도', now - 49.7);
    await twin.flush();
    final again = await logs.missed('#방', now - 3600);
    expect(again.length, 2, reason: '같은 줄이 두 번 쌓이면 안 된다');
  }, timeout: const Timeout(Duration(seconds: 90)));

  test('그 사람이 접속해 있지 않아도 얼굴을 받아온다', () async {
    if (!alive) {
      markTestSkipped('서버에 닿지 않아 건너뜀');
      return;
    }
    final host = freshHost();
    const face = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAA'
        'DUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==';

    final mine = ProfileApi('irc', host, 6697);
    final token = await mine.publish('몽키', face);
    expect(token, isNotNull);
    expect(token!.length, greaterThanOrEqualTo(16), reason: '표를 받아야 다음에 고칠 수 있다');

    // '남'이 - 같은 서버를 쓰는 다른 사람이 - 그 얼굴을 본다
    final mate = ProfileApi('irc', host, 6697);
    final found = await mate.lookup(['몽키', '없는사람']);
    expect(found['몽키'], face);
    expect(found.containsKey('없는사람'), isFalse);

    // 한 번 받아온 사람은 다시 안 묻는다
    expect(await mate.lookup(['몽키']), isEmpty);

    // 표 없이는 남의 얼굴을 못 바꾼다
    final who = relay.whoId('irc', host, 6697, '몽키');
    final stolen = await http.put(
      Uri.parse('${relay.profilesUrl}/$who'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'nick': '가짜', 'avatar': 'AAAA'}),
    );
    expect(stolen.statusCode, 403);
  }, timeout: const Timeout(Duration(seconds: 90)));

  test('사진을 올리면 주소가 오고 그림으로 알아본다', () async {
    if (!alive) {
      markTestSkipped('서버에 닿지 않아 건너뜀');
      return;
    }
    final files = FileApi();
    await files.refreshLimits();
    expect(files.maxBytes, greaterThan(0));

    // 이름이 거짓말을 해도 내용으로 가려야 한다
    final temp = await File('${Directory.systemTemp.path}/이름은아무거나.dat')
        .writeAsBytes(tinyPng());
    final result = await files.upload(temp);
    expect(result.ok, isTrue, reason: result.note);
    expect(result.url, startsWith(relay.server));
    expect(result.token, isNotEmpty, reason: '올린 사람만 내릴 수 있는 표');

    final info = await files.meta(relay.fileIdFrom(result.url));
    expect(info, isNotNull);
    expect(info!['image'], isTrue, reason: '.dat 여도 내용이 그림이면 그림이다');
    expect((info['expires'] as num) > 0, isTrue, reason: '언제까지 받을 수 있는지');

    await temp.delete();
  }, timeout: const Timeout(Duration(minutes: 3)));

  test('이모티콘은 같은 서버 사람끼리 같이 쓴다', () async {
    if (!alive) {
      markTestSkipped('서버에 닿지 않아 건너뜀');
      return;
    }
    final group = relay.groupId('irc', freshHost(), 6697);
    final files = FileApi(group: group);

    final temp = await File('${Directory.systemTemp.path}/짤.png')
        .writeAsBytes(tinyPng());
    final saved = await files.upload(temp, kind: 'emoji');
    expect(saved.ok, isTrue, reason: saved.note);

    // '남'이 목록에서 꺼내 쓸 수 있어야 한다
    final mate = FileApi(group: group);
    final shared = await mate.sharedEmoji();
    expect(shared, isNotEmpty);
    expect(shared.first['url'], startsWith(relay.server));
    expect(shared.first['name'], '짤', reason: '확장자는 떼고 보여준다');

    // 다른 서버 사람에게는 안 보인다
    final stranger = FileApi(group: relay.groupId('irc', freshHost(), 6697));
    expect(await stranger.sharedEmoji(), isEmpty);

    await temp.delete();
  }, timeout: const Timeout(Duration(minutes: 3)));

  test('사람이 읽는 말로 바꾼다', () {
    expect(readable(878900), '858.3KB');
    final now = DateTime.now();
    final at = now.millisecondsSinceEpoch / 1000;
    expect(remainingText(at + 3 * 3600, now: now), '3시간 뒤 사라짐');
    expect(remainingText(at + 300, now: now), '5분 뒤 사라짐');
    expect(remainingText(0), '', reason: '이모티콘은 기한이 없다');
    expect(remainingText(at - 10, now: now), contains('사라졌'));
  });
}
