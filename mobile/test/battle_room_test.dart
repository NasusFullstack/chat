/// 채널에 열린 전투 방을 알아듣고 기억하는가.
///
/// 이걸 못 알아들으면 폰에서는 전투에 **아예 못 들어간다** - 방 번호는 채팅 통로로만
/// 오고, CTCP 프레임은 평소에 전부 버리고 있기 때문이다.
///
/// 문구는 PC 와 같아야 한다(chat_core/constants.py). 다르면 PC 에서 연 방에 폰이
/// 못 들어가는데, 양쪽 다 "아무 일도 안 일어남"으로만 보여서 원인을 찾기 어렵다.
library;

import 'package:flutter_test/flutter_test.dart';

import 'package:chupchat/app_state.dart';
import 'package:chupchat/core/battle_protocol.dart' as bp;
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
  test('방 번호를 만든다 - 모양이 서버가 받아주는 것이어야 한다', () {
    final room = bp.newRoom();
    expect(bp.isRoomId(room), isTrue);
    expect(room.length, 24);
    // 난수라야 한다 - 같은 번호가 나오면 남의 방에 끼어든다
    expect(bp.newRoom(), isNot(room));
  });

  test('채널에 올라온 방 알림을 알아본다', () {
    final room = bp.newRoom();
    final notice = bp.formatRoomNotice(room);
    expect(bp.parseRoomNotice(notice), room);
    // 주소는 안 실린다 - 번호만 간다
    expect(notice.contains('jsserv'), isFalse);
    expect(notice.contains('wss'), isFalse);
  });

  test('방이 열리면 기억하고 채팅에 한 줄 남긴다', () {
    final state = joined();
    final room = bp.newRoom();
    state.handleEvent(BattleRoomOpened('#일반', '두리', room));

    expect(state.openRoom('#일반')?.$1, room);
    expect(state.openRoom('#일반')?.$2, '두리');
    final said = state.lines['#일반']!.last;
    expect(said.isSystem, isTrue);
    expect(said.text.contains('두리'), isTrue);
    expect(said.text.contains('전투 참가'), isTrue,
        reason: '어떻게 들어가는지 알려줘야 한다');
  });

  test('열린 방이 없으면 null', () {
    expect(joined().openRoom('#일반'), isNull);
  });

  test('오래된 방 알림은 잊는다', () {
    final state = joined();
    final room = bp.newRoom();
    // 아침에 열린 방에 저녁에 들어가려다 "이미 끝난 방"을 만나는 것보다,
    // "열린 방이 없다"고 말해주는 편이 낫다
    state.knownRooms['#일반'] =
        (room, '두리', DateTime.now().subtract(AppState.roomMemory * 2));

    expect(state.openRoom('#일반'), isNull);
    expect(state.knownRooms.containsKey('#일반'), isFalse, reason: '잊었으면 지운다');
  });

  test('다른 채널의 방에는 안 들어간다', () {
    final state = joined();
    state.handleEvent(BattleRoomOpened('#pdlab', '두리', bp.newRoom()));
    expect(state.openRoom('#일반'), isNull);
  });
}
