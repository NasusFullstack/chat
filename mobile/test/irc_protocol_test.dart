/// IRC 해석이 PC 앱과 **똑같은가**를 본다.
///
/// 여기서 보는 것은 "Dart 코드가 그럴듯한가"가 아니라 **"파이썬과 답이 같은가"**다.
/// 두 앱이 같은 서버에 붙어 같은 사람들과 이야기하므로, 한쪽만 다르게 해석하면 그
/// 사람에게만 글자가 깨지거나 명령이 안 먹는다. 양쪽을 따로 시험하면 그걸 못 잡는다.
///
/// 답안지는 `python tests/dump_irc_cases.py` 가 떠놓은 `irc_cases.json`이다.
/// 파이썬 쪽 규칙을 고치면 답안지가 바뀌고, 그러면 이 검사가 깨지면서 "모바일도
/// 같이 고쳐야 한다"고 알려준다.
library;

import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

import 'package:chupchat/core/irc_protocol.dart';

Map<String, dynamic> loadCases() {
  final file = File('test/irc_cases.json');
  if (!file.existsSync()) {
    throw StateError(
      '답안지가 없습니다. 먼저 저장소 뿌리에서 '
      '`python tests/dump_irc_cases.py` 를 돌리세요.',
    );
  }
  return jsonDecode(file.readAsStringSync()) as Map<String, dynamic>;
}

void main() {
  final cases = loadCases();

  group('받은 줄 해석이 PC와 같은가', () {
    for (final raw in cases['parse'] as List) {
      final c = raw as Map<String, dynamic>;
      final line = c['line'] as String;
      test('줄: ${line.length > 48 ? '${line.substring(0, 48)}…' : line}', () {
        final msg = parseLine(line);
        expect(msg.prefix, c['prefix'], reason: '프리픽스');
        expect(msg.command, c['command'], reason: '명령');
        expect(msg.params, (c['params'] as List).cast<String>(), reason: '칸');
        expect(msg.sourceNick, c['source_nick'], reason: '보낸 사람');
        expect(msg.trailing, c['trailing'], reason: '마지막 칸');
      });
    }
  });

  group('긴 글 나누기가 PC와 같은가', () {
    // 한글은 한 글자가 3바이트라 바이트로 자르면 글자가 깨진다. 어디서 자르는지가
    // 양쪽에서 같아야 같은 글이 같은 모양으로 간다
    var index = 0;
    for (final raw in cases['split'] as List) {
      final c = raw as Map<String, dynamic>;
      final text = c['text'] as String;
      final want = (c['pieces'] as List).cast<String>();
      test('${index++}번 글(${text.length}자) -> ${want.length}조각', () {
        expect(splitMessage(text), want);
        for (final piece in splitMessage(text)) {
          expect(utf8.encode(piece).length, lessThanOrEqualTo(maxMessageBytes),
              reason: '한 조각이 상한을 넘으면 서버가 잘라버린다');
        }
      });
    }
  });

  test('채널 이름 다듬기가 PC와 같다', () {
    for (final raw in cases['normalize_channel'] as List) {
      final c = raw as Map<String, dynamic>;
      expect(normalizeChannel(c['name'] as String), c['out'],
          reason: '입력: "${c['name']}"');
    }
  });

  test('숨김 프레임 판별이 PC와 같다', () {
    // 잘려서 해석에 실패해도 채팅으로 새면 안 된다 - PC에서 잘린 base64가 채팅에
    // 그대로 쏟아진 사고가 있었다
    for (final raw in cases['is_ctcp_frame'] as List) {
      final c = raw as Map<String, dynamic>;
      expect(isCtcpFrame(c['text'] as String), c['out'],
          reason: '입력: ${jsonEncode(c['text'])}');
    }
  });

  test('참여자 목록 읽기가 PC와 같다', () {
    for (final raw in cases['names_reply'] as List) {
      final c = raw as Map<String, dynamic>;
      final msg = parseLine(c['line'] as String);
      expect(parseNamesReply(msg), (c['names'] as List).cast<String>());
    }
  });

  test('보내는 줄 모양이 PC와 같다', () {
    final f = cases['format'] as Map<String, dynamic>;
    expect(formatPass('비밀'), f['pass']);
    expect(formatNick('몽키'), f['nick']);
    expect(formatUser('mong', '몽키 님'), f['user']);
    expect(formatJoin('#일반'), f['join']);
    expect(formatJoin('#비밀', '열쇠'), f['join_key']);
    expect(formatPrivmsg('#일반', '안녕'), f['privmsg']);
    expect(formatNotice('몽키', '알림'), f['notice']);
    expect(formatPart('#일반'), f['part']);
    expect(formatPart('#일반', '간다'), f['part_reason']);
    expect(formatQuit(), f['quit']);
    expect(formatQuit('종료'), f['quit_reason']);
    expect(formatPong('1234'), f['pong']);
    expect(formatPing('1234'), f['ping']);
    expect(formatNames('#일반'), f['names']);
  });

  test('숫자 규약이 PC와 같다', () {
    final k = cases['constants'] as Map<String, dynamic>;
    expect(maxMessageBytes, k['MAX_MESSAGE_BYTES'],
        reason: '다르면 같은 글이 한쪽에서만 잘린다');
    expect(maxNickRetries, k['MAX_NICK_RETRIES']);
    expect(nickCollisionNumerics.toList()..sort(),
        (k['NICK_COLLISION_NUMERICS'] as List).cast<String>());
    expect(channelJoinErrorNumerics.toList()..sort(),
        (k['CHANNEL_JOIN_ERROR_NUMERICS'] as List).cast<String>());
  });

  test('보낼 줄은 CR-LF로 끝난다', () {
    final bytes = encodeLine('PING :1');
    expect(bytes.sublist(bytes.length - 2), [13, 10]);
  });
}
