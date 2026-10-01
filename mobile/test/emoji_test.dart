/// 메시지 안의 이모티콘을 PC와 **같은 방식으로** 가르는가.
///
/// 짝이 안 맞는 표시를 한쪽만 다르게 다루면 그 사람 화면에서만 대화가 사라지거나
/// 이상한 글자가 뜬다. 답안지와 하나하나 맞춘다.
///
/// 답안지: `python tests/dump_emoji_cases.py`
library;

import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

import 'package:chupchat/core/emoji.dart';

void main() {
  final file = File('test/emoji_cases.json');
  if (!file.existsSync()) {
    throw StateError('답안지가 없습니다. `python tests/dump_emoji_cases.py` 를 돌리세요.');
  }
  final cases = jsonDecode(file.readAsStringSync()) as Map<String, dynamic>;

  test('표시 문자가 PC와 같다', () {
    expect(emojiOpen, cases['open']);
    expect(emojiClose, cases['close']);
  });

  test('보낼 때 감싸는 모양이 PC와 같다', () {
    final want = cases['format'] as String;
    final url = want.substring(1, want.length - 1);
    expect(formatEmoji(url), want);
  });

  group('가르는 결과가 PC와 같다', () {
    for (final raw in cases['split'] as List) {
      final c = raw as Map<String, dynamic>;
      final text = c['text'] as String;
      final want = (c['parts'] as List).cast<Map<String, dynamic>>();
      // 표시 문자는 눈에 안 보이므로 어떤 경우인지 알아볼 수 있게 이름을 붙인다
      final label = text
          .replaceAll(emojiOpen, '[열기]')
          .replaceAll(emojiClose, '[닫기]');
      test(label.isEmpty ? '(빈 글)' : (label.length > 46 ? '${label.substring(0, 46)}…' : label),
          () {
        final got = splitEmojiParts(text);
        expect(got.length, want.length,
            reason: '조각 수가 다르다: $got vs $want');
        for (var i = 0; i < want.length; i++) {
          expect(got[i].isEmoji, want[i]['kind'] == 'emoji',
              reason: '${i + 1}번째 조각의 종류가 다르다');
          expect(got[i].value, want[i]['value'],
              reason: '${i + 1}번째 조각의 내용이 다르다');
        }
      });
    }
  });

  test('짝이 안 맞아도 글자가 사라지지 않는다', () {
    // 잘린 표시가 와도 사람이 쓴 말은 남아야 한다
    const broken = '중요한 말$emojiOpen https://a.kr/x.png';
    final parts = splitEmojiParts(broken);
    expect(parts.map((p) => p.value).join(), contains('중요한 말'));
  });
}
