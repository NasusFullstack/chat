/// 전투 줄을 **파이썬과 똑같이 받아주고 똑같이 버리는가**.
///
/// 받은 줄은 전부 남이 정한 값이다. 한쪽이 더 헐겁게 받아주면 거기서만 이상한 값이
/// 들어와 배가 엉뚱한 자리로 가거나, 체력이 음수가 되거나, 남의 배를 대신 신고하는
/// 길이 열린다. 그래서 **같은 줄에 같은 답**이 나오는지 본다.
///
/// 답안지: `python tests/dump_battle_protocol_cases.py`
library;

import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

import 'package:chupchat/core/battle_protocol.dart' as bp;

Map<String, Object?> loadCases() {
  final file = File('test/battle_protocol_cases.json');
  if (!file.existsSync()) {
    fail('답안지가 없다. python tests/dump_battle_protocol_cases.py 로 먼저 뜰 것');
  }
  return jsonDecode(file.readAsStringSync()) as Map<String, Object?>;
}

/// 사전을 견주기 좋게 - 중첩된 목록까지 같은 모양으로 편다
Object? plain(Object? value) {
  if (value is Map) {
    final out = <String, Object?>{};
    for (final key in value.keys.map((k) => '$k').toList()..sort()) {
      out[key] = plain(value[key]);
    }
    return out;
  }
  if (value is List) return value.map(plain).toList();
  return value;
}

void main() {
  final data = loadCases();

  test('한도가 파이썬과 같다', () {
    final limits = data['limits'] as Map<String, Object?>;
    expect(bp.maxLineBytes, limits['MAX_LINE_BYTES']);
    expect(bp.maxHumans, limits['MAX_HUMANS']);
    expect(bp.maxBots, limits['MAX_BOTS']);
    expect(bp.maxPlayers, limits['MAX_PLAYERS']);
    expect(bp.minPlayers, limits['MIN_PLAYERS']);
    expect(bp.maxNickLen, limits['MAX_NICK_LEN']);
    expect(bp.colorCount, limits['COLOR_COUNT']);
    expect(bp.rainbowColor, limits['RAINBOW_COLOR']);
    expect(bp.maxTick, limits['MAX_TICK']);
    expect(bp.maxHpWire, limits['MAX_HP']);
    expect(bp.keyMask, limits['KEY_MASK']);
  });

  group('받은 줄', () {
    final cases = data['decode'] as List;
    for (var i = 0; i < cases.length; i++) {
      final one = cases[i] as Map<String, Object?>;
      final line = one['line'] as String;
      final want = one['want'];
      final label = line.isEmpty ? '(빈 줄)'
          : (line.length <= 60 ? line : '${line.substring(0, 60)}…');

      test('${want == null ? "버린다" : "받아준다"}: $label', () {
        final got = bp.decode(line);
        if (want == null) {
          expect(got, isNull, reason: '파이썬은 버리는데 우리는 받아줬다');
        } else {
          expect(got, isNotNull, reason: '파이썬은 받아주는데 우리는 버렸다');
          expect(plain(got), plain(want));
        }
      });
    }
  });

  group('보낼 줄', () {
    final cases = data['encode'] as List;
    for (final raw in cases) {
      final one = raw as Map<String, Object?>;
      final message = (one['message'] as Map).map((k, v) => MapEntry('$k', v));
      test('${message['t']}', () {
        // 글자가 똑같을 필요는 없지만(키 순서), **읽으면 같은 것**이어야 한다
        final line = bp.encode(message);
        expect(line, isNotEmpty);
        expect(plain(jsonDecode(line)), plain(jsonDecode(one['line'] as String)));
      });
    }
  });

  group('남이 보낸 이름을 다듬는다', () {
    final cases = data['nicks'] as List;
    for (final raw in cases) {
      final one = raw as Map<String, Object?>;
      final nick = one['raw'] as String;
      test('"${nick.length > 12 ? "${nick.substring(0, 12)}…" : nick}"', () {
        expect(bp.safeNick(nick), one['safe'],
            reason: '제어문자가 그대로 들어오면 화면이 깨진다(실제로 겪었다)');
      });
    }
  });

  test('방 번호를 가린다', () {
    for (final raw in data['rooms'] as List) {
      final one = raw as Map<String, Object?>;
      expect(bp.isRoomId(one['value']), one['ok'], reason: '${one['value']}');
    }
  });

  test('채팅에 올라온 방 알림을 알아본다', () {
    for (final raw in data['notices'] as List) {
      final one = raw as Map<String, Object?>;
      expect(bp.parseRoomNotice(one['text'] as String), one['room'],
          reason: '못 알아보면 전투에 아예 못 들어간다');
    }
  });

  test('너무 긴 줄은 아예 안 만든다', () {
    // IRC 와 같은 512바이트 상한. 넘으면 보내는 쪽에서 막는다
    final huge = {'t': bp.tJoin, 'room': 'a' * 8, 'nick': '가' * 500};
    expect(bp.encode(huge), isEmpty);
  });
}
