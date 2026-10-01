/// 같은 이름으로 **다른 기기에서** 들어오면 배지가 따라 바뀌는가.
///
/// 어제는 폰, 오늘은 PC 일 수 있다. 한 번 받은 답을 그대로 믿으면 PC 로 들어온
/// 사람에게 폰 표시가 며칠씩 붙어 있게 된다 - 알아채기도 어렵다(틀린 줄 모르고 본다).
///
/// 그래서 **접속할 때마다 새로 올리고**(publishClient), 보는 쪽은 **새로 들어온
/// 사람을 다시 묻는다**(forget). 이 검사는 뒤쪽을 본다.
library;

import 'package:flutter_test/flutter_test.dart';

import 'package:chupchat/app_state.dart';
import 'package:chupchat/core/client_badge.dart';
import 'package:chupchat/core/events.dart';

AppState joined() {
  final state = AppState()
    ..holdConnection = (() async => true)
    ..releaseConnection = (() async {});
  state.handleEvent(const LoggedIn('나'));
  state.handleEvent(const ChannelJoined('#일반', '입장'));
  return state;
}

void main() {
  test('처음 받은 목록은 그대로 쓴다', () {
    final state = joined();
    state.clients['두리'] = const ClientInfo(
        app: 'ChupChat', version: '2.6.6', platform: 'pc');
    state.handleEvent(const UserlistUpdated('#일반', ['나', '두리']));

    expect(state.clients['두리']?.platform, 'pc',
        reason: '처음 목록에는 "새로 들어온 사람"이 없다 - 서버 것을 그대로 쓴다');
  });

  test('나갔다 다시 들어온 사람은 다시 묻는다', () {
    final state = joined();
    state.handleEvent(const UserlistUpdated('#일반', ['나', '두리']));
    state.clients['두리'] = const ClientInfo(
        app: 'ChupChat', version: '2.6.6', platform: 'mobile');

    // 나갔다가
    state.handleEvent(const UserlistUpdated('#일반', ['나']));
    // 다시 들어왔다 - 이번엔 PC 일 수 있다
    state.handleEvent(const UserlistUpdated('#일반', ['나', '두리']));

    expect(state.clients.containsKey('두리'), isFalse,
        reason: '옛 답을 지워야 서버에 다시 묻는다');
  });

  test('계속 있던 사람은 괜히 다시 묻지 않는다', () {
    final state = joined();
    state.handleEvent(const UserlistUpdated('#일반', ['나', '두리']));
    state.clients['두리'] = const ClientInfo(
        app: 'ChupChat', version: '2.6.6', platform: 'pc');

    // 다른 사람이 하나 들어왔을 뿐이다
    state.handleEvent(const UserlistUpdated('#일반', ['나', '두리', '몽키']));

    expect(state.clients['두리']?.platform, 'pc',
        reason: '남이 들어올 때마다 전원에게 다시 물으면 요청이 쏟아진다');
  });

  test('채널에서 나가면 기억도 지운다', () {
    final state = joined();
    state.handleEvent(const UserlistUpdated('#일반', ['나', '두리']));
    state.handleEvent(const ChannelLeft('#일반'));
    state.handleEvent(const ChannelJoined('#일반', '입장'));
    state.clients['두리'] = const ClientInfo(
        app: 'ChupChat', version: '2.6.6', platform: 'pc');
    state.handleEvent(const UserlistUpdated('#일반', ['나', '두리']));

    expect(state.clients['두리']?.platform, 'pc',
        reason: '다시 들어가면 그때 받은 목록이 처음 목록이다');
  });
}
