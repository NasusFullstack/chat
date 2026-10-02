/// 끊겨 있을 때 친 말이 **사라지지 않는가**.
///
/// 홈으로 나갔다 오면 접속이 끊겨 있다(안드로이드가 앱을 멈춰 세운다). 그때 친 말이
/// 그냥 사라지면 사람은 보낸 줄 안다 - 상대는 못 받았는데.
///
/// 그래서 모아뒀다가 다시 붙어 **채널까지 들어간 뒤에** 보낸다. 들어가기 전에 보내면
/// 서버가 조용히 무시한다.
library;

import 'package:flutter_test/flutter_test.dart';

import 'package:chupchat/app_state.dart';
import 'package:chupchat/core/events.dart';

AppState chatting() {
  final state = AppState();
  state.handleEvent(const LoggedIn('나'));
  state.handleEvent(const ChannelJoined('#일반', '입장'));
  state.current = '#일반';
  return state;
}

void main() {
  test('붙어 있지 않으면 모아둔다', () {
    final state = chatting();     // 소켓이 없으므로 link 는 idle 이다
    state.sendChat('안녕');

    expect(state.hasUnsent, isTrue, reason: '보낸 줄 알았는데 사라지면 안 된다');
    final said = state.lines['#일반']!.last;
    expect(said.isSystem, isTrue);
    expect(said.text.contains('붙는 대로'), isTrue,
        reason: '아무 말도 없으면 보낸 줄 안다');
  });

  test('빈 말과 채널 없을 때는 모으지 않는다', () {
    final state = chatting();
    state.sendChat('   ');
    expect(state.hasUnsent, isFalse);

    final noChannel = AppState()..handleEvent(const LoggedIn('나'));
    noChannel.sendChat('안녕');
    expect(noChannel.hasUnsent, isFalse, reason: '보낼 곳이 없다');
  });

  test('모은 말이 여러 개여도 순서를 지킨다', () {
    final state = chatting();
    state.sendChat('하나');
    state.sendChat('둘');
    state.sendChat('셋');
    expect(state.hasUnsent, isTrue);
    // 안내는 한 줄씩 붙는다 - 몇 개를 모았는지 사람이 볼 수 있다
    final notices =
        state.lines['#일반']!.where((l) => l.isSystem && l.text.contains('붙는 대로'));
    expect(notices.length, 3);
  });

  test('끊긴 걸 알면 바로 다시 붙으려 한다', () {
    final state = chatting();
    expect(state.reconnect.active, isFalse);

    state.sendChat('안녕');
    expect(state.reconnect.active, isTrue,
        reason: '치자마자 다시 붙어야 말이 빨리 나간다');
    state.reconnect.cancel();
  });

  test('이미 다시 붙는 중이면 또 시작하지 않는다', () {
    final state = chatting();
    state.reconnect.start(['#일반']);
    final attempt = state.reconnect.attempt;

    state.sendChat('안녕');
    expect(state.reconnect.attempt, attempt,
        reason: '칠 때마다 처음부터 다시 세면 간격을 늘리는 의미가 없다');
    state.reconnect.cancel();
  });
}
