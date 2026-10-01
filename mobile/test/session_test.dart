/// 받은 줄을 보고 **무슨 일이라고 판단하는지**가 PC와 같은가.
///
/// 이벤트의 **종류·내용·순서**를 전부 맞춰본다. 순서까지 보는 이유는 화면에 뜨는 차례가
/// 그대로 달라지기 때문이다 - 예를 들어 파이썬은 참여자 목록 변경을 먼저 알리고 안내문을
/// 뒤에 낸다. 실제로 이 검사가 그 차이를 잡아서 Dart 쪽을 고쳤다.
///
/// 답안지: `python tests/dump_session_cases.py`
library;

import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

import 'package:chupchat/core/session.dart';

Map<String, dynamic> loadCases() {
  final file = File('test/session_cases.json');
  if (!file.existsSync()) {
    throw StateError(
      '답안지가 없습니다. 저장소 뿌리에서 `python tests/dump_session_cases.py` 를 돌리세요.',
    );
  }
  return jsonDecode(file.readAsStringSync()) as Map<String, dynamic>;
}

void main() {
  final data = loadCases();
  final me = data['me'] as String;

  for (final raw in data['cases'] as List) {
    final c = raw as Map<String, dynamic>;
    test(c['name'] as String, () {
      final sent = <String>[];
      final got = <Map<String, Object?>>[];
      final session = ChatSession(
        send: sent.add,
        emit: (event) => got.add(event.toMap()),
        wantedNick: me,
      );
      for (final line in (c['lines'] as List).cast<String>()) {
        session.handleLine(line);
      }

      final want = (c['events'] as List)
          .cast<Map<String, dynamic>>()
          .map((m) => m.map((k, v) => MapEntry(k, v is List ? v.cast<String>() : v)))
          .toList();

      // 하나씩 비교해야 어디서 갈라졌는지 바로 보인다
      for (var i = 0; i < want.length && i < got.length; i++) {
        expect(got[i], want[i], reason: '${i + 1}번째 이벤트가 다르다');
      }
      expect(got.length, want.length,
          reason: '이벤트 개수가 다르다\nPC: ${want.map((e) => e['type']).toList()}\n'
              '모바일: ${got.map((e) => e['type']).toList()}');
    });
  }

  test('내가 보낸 말은 내가 화면에 올린다', () {
    // IRC 서버는 내가 보낸 말을 나에게 되돌려주지 않는다. 여기서 올리지 않으면
    // 내 말만 화면에 안 보인다
    final sent = <String>[];
    final got = <Map<String, Object?>>[];
    final session = ChatSession(
      send: sent.add,
      emit: (event) => got.add(event.toMap()),
      wantedNick: me,
    );
    session.handleLine(':irc.test 001 $me :Welcome');
    got.clear();
    sent.clear();

    session.sendChat('#일반', '안녕');
    expect(sent, ['PRIVMSG #일반 :안녕']);
    expect(got.length, 1);
    expect(got.first['type'], 'MessageReceived');
    expect(got.first['mine'], true);
    expect(got.first['sender'], me);
  });

  test('긴 글은 나눠 보내고 나눈 만큼 화면에 올린다', () {
    final sent = <String>[];
    final got = <Map<String, Object?>>[];
    final session = ChatSession(
      send: sent.add,
      emit: (event) => got.add(event.toMap()),
      wantedNick: me,
    );
    session.handleLine(':irc.test 001 $me :Welcome');
    got.clear();
    sent.clear();

    session.sendChat('#일반', '가' * 400);
    expect(sent.length, greaterThan(1), reason: '한 줄에 다 안 들어간다');
    expect(got.length, sent.length, reason: '보낸 조각마다 화면에도 올라가야 한다');
  });

  test('PING 에는 PONG 으로 답한다', () {
    // 답을 안 하면 서버가 끊는다
    final sent = <String>[];
    final session = ChatSession(send: sent.add, emit: (_) {}, wantedNick: me);
    session.handleLine('PING :abc123');
    expect(sent, ['PONG :abc123']);
  });
}
