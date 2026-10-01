/// 중계 서버 자리 이름이 PC와 **한 글자도 안 틀리는가**.
///
/// 틀리면 오류가 안 나고 조용히 갈라진다 - 같은 채널인데 기록이 서로 다른 칸에 쌓이고,
/// 같은 사람인데 얼굴이 안 보이고, 이모티콘 목록이 따로 논다. "안 보인다"로만 나타나서
/// 원인을 찾기도 어렵다. 그래서 답안지와 하나하나 맞춘다.
///
/// 답안지: `python tests/dump_relay_cases.py`
library;

import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

import 'package:chupchat/core/relay.dart' as relay;

Map<String, dynamic> loadCases() {
  final file = File('test/relay_cases.json');
  if (!file.existsSync()) {
    throw StateError(
      '답안지가 없습니다. 저장소 뿌리에서 `python tests/dump_relay_cases.py` 를 돌리세요.',
    );
  }
  return jsonDecode(file.readAsStringSync()) as Map<String, dynamic>;
}

void main() {
  final cases = loadCases();

  test('서버 주소가 PC와 같다', () {
    final urls = cases['urls'] as Map<String, dynamic>;
    expect(relay.server, urls['server']);
    expect(relay.battleUrl, urls['battle']);
    expect(relay.filesUrl, urls['files']);
    expect(relay.logsUrl, urls['logs']);
    expect(relay.profilesUrl, urls['profiles']);
    expect(relay.idChars, cases['id_chars']);
  });

  test('채널 자리가 PC와 같다', () {
    for (final raw in cases['room'] as List) {
      final c = raw as Map<String, dynamic>;
      expect(
        relay.roomId(c['protocol'] as String, c['host'] as String,
            c['port'] as int, c['channel'] as String),
        c['id'],
        reason: '${c['host']}:${c['port']} ${c['channel']}',
      );
    }
  });

  test('사람 자리가 PC와 같다', () {
    for (final raw in cases['who'] as List) {
      final c = raw as Map<String, dynamic>;
      expect(
        relay.whoId(c['protocol'] as String, c['host'] as String,
            c['port'] as int, c['nick'] as String),
        c['id'],
        reason: '${c['host']}:${c['port']} ${c['nick']}',
      );
    }
  });

  test('이모티콘 무리가 PC와 같다', () {
    for (final raw in cases['group'] as List) {
      final c = raw as Map<String, dynamic>;
      expect(
        relay.groupId(
            c['protocol'] as String, c['host'] as String, c['port'] as int),
        c['id'],
        reason: '${c['host']}:${c['port']}',
      );
    }
  });

  test('파일 주소에서 id를 뽑는 것이 PC와 같다', () {
    for (final raw in cases['file_id'] as List) {
      final c = raw as Map<String, dynamic>;
      expect(relay.fileIdFrom(c['url'] as String), c['id'],
          reason: '입력: ${c['url']}');
    }
  });

  test('정보 물어보는 주소가 PC와 같다', () {
    expect(relay.metaUrl('aabbccddeeff00112233445c'), cases['meta_url']);
  });

  test('서버가 달라지면 자리도 달라진다', () {
    // 어느 IRC 서버에나 있는 #general 이 한 칸에 섞이면 안 된다
    final a = relay.roomId('irc', 'a.kr', 6697, '#general');
    final b = relay.roomId('irc', 'b.kr', 6697, '#general');
    expect(a, isNot(b));
    // 채널 이름이 그대로 서버에 나가지도 않는다
    expect(a.contains('general'), isFalse);
  });
}
