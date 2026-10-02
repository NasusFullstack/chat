/// 지난 대화를 **실제로 받아오는가**.
///
/// "모바일이 이전 채팅을 못 불러온다"는 신고의 원인이 여기 있었다. 채널에 들어가면
/// "입장 완료"를 먼저 화면에 올리고 나서 못 본 대화를 받아오는데, 받아올 기준을
/// "화면에 있는 가장 최근 줄의 시각"으로 잡고 있었다. 방금 올린 **안내가 지금 시각**
/// 이라 서버에 "지금 이후 것만 달라"고 묻게 되고, 그러면 언제나 0줄이 온다.
///
/// 서버에는 멀쩡히 쌓여 있었다(실측: #pdlab 38줄). 조용히 틀리는 종류라 검사로 못 박는다.
library;

import 'package:flutter_test/flutter_test.dart';

import 'package:chupchat/app_state.dart';
import 'package:chupchat/core/events.dart';
import 'package:chupchat/net/relay_api.dart';

/// 가짜 기록 창구 - **무엇을 물었는지** 적어둔다.
///
/// 규칙을 검사에 베껴 쓰지 않는다. 베껴 쓰면 코드가 바뀔 때 검사는 안 바뀌어서
/// 같은 버그를 또 못 잡는다(CLAUDE.md 11-5)
class FakeLogs extends ChatLogApi {
  FakeLogs() : super('irc', 'home.pdlab.kr', 6697);

  final List<({String channel, double since})> asked = [];
  List<Map<String, Object?>> answer = const [];

  @override
  Future<List<Map<String, Object?>>> missed(String channel, double since) async {
    asked.add((channel: channel, since: since));
    return answer;
  }

  @override
  Future<void> flush() async {}
}

/// 실제 코드가 "언제 이후 것"을 물었는지.
Future<double> askedSince(AppState state, String channel) async {
  final logs = FakeLogs();
  state.logsForTest = logs;
  await state.fetchMissed(channel);
  return logs.asked.isEmpty ? -1 : logs.asked.last.since;
}

ChatLine systemAt(DateTime at) => ChatLine.system(text: '입장 완료', at: at);

ChatLine saidAt(DateTime at) => ChatLine.message(
    sender: '두리', text: '안녕', mine: false, isMention: false, at: at);

AppState joined(String channel) {
  final state = AppState();
  state.handleEvent(const LoggedIn('나'));
  state.handleEvent(ChannelJoined(channel, '$channel 입장 완료'));
  return state;
}

void main() {
  test('들어간 직후에는 **하루치를 다 받아온다**', () async {
    // 여기가 이 버그의 자리였다. 화면에는 방금 올린 "입장 완료"뿐인데 그걸 기준으로
    // 삼아서 "지금 이후"를 묻고 있었고, 그래서 언제나 0줄이 왔다
    final state = joined('#pdlab');
    final since = await askedSince(state, '#pdlab');

    final day = DateTime.now().millisecondsSinceEpoch / 1000 - 24 * 3600;
    expect(since, closeTo(day, 5),
        reason: '안내를 기준으로 삼으면 지난 대화를 영영 못 받는다');
  });

  test('이미 본 대화가 있으면 그 뒤부터 받는다', () async {
    final state = joined('#pdlab');
    final older = DateTime.now().subtract(const Duration(hours: 2));
    state.lines['#pdlab']!.add(ChatLine.message(
        sender: '두리', text: '안녕', mine: false, isMention: false, at: older));

    final since = await askedSince(state, '#pdlab');
    expect(since, closeTo(older.millisecondsSinceEpoch / 1000, 0.01),
        reason: '겹치지 않게 본 데까지만 건너뛴다');
  });

  test('안내가 대화보다 뒤에 쌓여도 대화 쪽을 본다', () async {
    final state = joined('#pdlab');
    final said = DateTime.now().subtract(const Duration(hours: 3));
    state.lines['#pdlab']!.add(ChatLine.message(
        sender: '두리', text: '안녕', mine: false, isMention: false, at: said));
    // 끊겼다 돌아오면 안내가 더 쌓인다
    state.handleEvent(const SystemNotice('#pdlab', '연결이 끊겼습니다'));
    state.handleEvent(const ChannelJoined('#pdlab', '입장'));

    final since = await askedSince(state, '#pdlab');
    expect(since, closeTo(said.millisecondsSinceEpoch / 1000, 0.01));
  });

  test('받아온 줄이 화면에 올라간다', () async {
    final state = joined('#pdlab');
    final logs = FakeLogs()
      ..answer = [
        {'ts': 1.0, 'sender': '두리', 'text': '어제 한 말'},
        {'ts': 2.0, 'sender': '나', 'text': '내가 한 말'},
      ];
    state.logsForTest = logs;
    await state.fetchMissed('#pdlab');

    final texts = state.lines['#pdlab']!.map((l) => l.text).toList();
    expect(texts.contains('어제 한 말'), isTrue, reason: texts.toString());
    expect(texts.contains('내가 한 말'), isTrue);
    final mine = state.lines['#pdlab']!.firstWhere((l) => l.text == '내가 한 말');
    expect(mine.mine, isTrue, reason: '내가 한 말은 내 것으로 보여야 한다');
  });

  test('받아온 것이 없으면 화면을 건드리지 않는다', () async {
    final state = joined('#pdlab');
    final before = state.lines['#pdlab']!.length;
    state.logsForTest = FakeLogs();
    await state.fetchMissed('#pdlab');
    expect(state.lines['#pdlab']!.length, before,
        reason: '"0줄 받아왔다" 같은 안내가 쌓이면 지저분하다');
  });
}
