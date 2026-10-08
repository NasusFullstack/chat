/// 당분간 막아둔 것들이 **폰에서도** 막혔는가.
///
/// PC 와 같은 표를 쓴다(`gui/availability.py`) - 한쪽만 고치면 둘이 다르게 막는다.
/// 둘이 같은지는 `tests/test_availability.py` 가 대조한다.
library;

import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

import 'package:chupchat/app_state.dart';
import 'package:chupchat/core/availability.dart';
import 'package:chupchat/core/chat_port.dart';
import 'package:chupchat/core/events.dart';

void main() {
  group('고를 수 있는 쪽', () {
    test('IRC 만 고를 수 있다', () {
      expect(kindEnabled(ChatKind.irc), isTrue);
      expect(kindEnabled(ChatKind.server), isFalse,
          reason: 'jsserv 에서 꺼둔 쪽이다 - 고르면 "눌렀는데 안 붙는다"가 된다');
    });

    test('막힌 쪽도 탭에는 **보인다**(흐리게)', () {
      // 빼버리면 "그 기능 없어졌나" 한다
      final source = File('lib/ui/login_page.dart').readAsStringSync();
      expect(source.contains('ChatKind.server, ChatKind.irc'), isTrue);
      expect(source.contains('disabledColor'), isTrue);
      expect(source.contains('kindBlockedText'), isTrue,
          reason: '막힌 탭을 누르면 왜인지 말해야 한다');
    });
  });

  group('사진·파일 올리기', () {
    test('pdlab IRC 의 #pdlab 에서만 된다', () {
      expect(uploadAllowed('irc', 'home.pdlab.kr', '#pdlab'), isTrue);
      expect(uploadAllowed('irc', 'home.pdlab.kr', '#general'), isFalse);
      expect(uploadAllowed('irc', 'irc.libera.chat', '#pdlab'), isFalse,
          reason: '이름만 같은 남의 방');
      expect(uploadAllowed('server', 'chupchat', 'pdlab'), isFalse);
    });

    test('대소문자를 안 가린다 - IRC 는 채널 이름도 주소도 안 가린다', () {
      expect(uploadAllowed('irc', 'HOME.pdlab.kr', '#PDLab'), isTrue);
    });

    test('상태가 지금 보는 방에 맞춰 답한다', () {
      final state = AppState()
        ..host = 'home.pdlab.kr'
        ..chatKind = ChatKind.irc;
      state.handleEvent(const ChannelJoined('#general', '입장'));
      state.showChannel('#general');
      expect(state.canUploadHere, isFalse);
      state.handleEvent(const ChannelJoined('#pdlab', '입장'));
      state.showChannel('#pdlab');
      expect(state.canUploadHere, isTrue);
    });

    test('채팅 화면은 **왜 막혔는지** 말한다', () {
      final source = File('lib/ui/chat_page.dart').readAsStringSync();
      expect(source.contains('canUploadHere'), isTrue);
      expect(source.contains('uploadBlockedText'), isTrue);
      // 화면은 여전히 프로토콜을 모른다
      expect(source.contains('ChatKind'), isFalse);
    });
  });
}
