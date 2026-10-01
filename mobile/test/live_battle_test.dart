/// 진짜 중계 서버에 **둘이 붙어서** 전투 한 판이 도는가.
///
/// 여기서만 확인되는 것들이다:
///  - 우리가 만든 줄을 서버가 받아주는가(규약 검사는 우리끼리 맞춘 것일 뿐이다)
///  - 자리 번호를 서버가 붙여주는가(우리는 안 적는다)
///  - 방을 연 사람만 시작할 수 있는가
///  - 남의 조작이 넘어오는가
///
/// 서버가 안 받아주면(점검 중·막힘) **실패가 아니라 건너뜀**으로 처리하고 그 사실을
/// 말한다 - 조용히 통과시키면 "전투가 안 되는데 검사는 초록"이 된다.
library;

import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;

import 'package:chupchat/core/battle_protocol.dart' as bp;
import 'package:chupchat/core/relay.dart' as relay;
import 'package:chupchat/net/battle_link.dart';

/// 서버가 살아 있고 전투 기능이 올라가 있는가.
Future<bool> battleAlive() async {
  try {
    final response =
        await http.get(Uri.parse(relay.server)).timeout(const Duration(seconds: 10));
    if (response.statusCode != 200) return false;
    return response.body.contains('"battle"');
  } on Object {
    return false;
  }
}

/// 이 신호가 올 때까지 기다린다. 안 오면 null.
Future<T?> waitFor<T extends BattleSignal>(Stream<BattleSignal> signals,
    {Duration limit = const Duration(seconds: 20)}) async {
  try {
    return await signals.where((s) => s is T).cast<T>().first.timeout(limit);
  } on Object {
    return null;
  }
}

void main() {
  late bool alive;

  setUpAll(() async {
    alive = await battleAlive();
  });

  test('둘이 들어가서 방장이 시작하고 조작이 오간다', () async {
    if (!alive) {
      markTestSkipped('중계 서버에 닿지 않아 건너뜀');
      return;
    }
    final room = bp.newRoom();

    final host = BattleLink();
    final guest = BattleLink();
    // 신호는 한 번만 흐르므로 미리 받아둔다(들어간 뒤에 듣기 시작하면 놓친다)
    final hostSignals = host.signals.asBroadcastStream();
    final guestSignals = guest.signals.asBroadcastStream();
    final hostJoined = waitFor<BattleJoined>(hostSignals);
    final sawGuest = waitFor<BattlePeerJoined>(hostSignals);

    addTearDown(() async {
      await host.leave();
      await guest.leave();
      host.dispose();
      guest.dispose();
    });

    await host.join(room, '방장');
    final mine = await hostJoined;
    if (mine == null) {
      markTestSkipped('서버가 자리를 안 줘서 건너뜀(점검 중일 수 있습니다)');
      return;
    }
    expect(mine.slot, isNonNegative, reason: '자리 번호는 **서버가** 붙인다');
    expect(host.mySlot, mine.slot);

    final guestJoined = waitFor<BattleJoined>(guestSignals);
    await guest.join(room, '손님');
    final theirs = await guestJoined;
    expect(theirs, isNotNull, reason: '같은 방 번호면 들어갈 수 있어야 한다');
    expect(theirs!.slot, isNot(mine.slot), reason: '자리가 겹치면 안 된다');

    // 방장 화면에도 손님이 들어온 것이 보여야 한다
    final seen = await sawGuest;
    expect(seen, isNotNull, reason: '들어온 사람이 안 보이면 시작할 수가 없다');
    expect(seen!.nick, '손님');

    // 시작은 방장만 - 손님이 눌러도 아무 일이 없어야 한다
    final startedForGuest = waitFor<BattleStarted>(guestSignals,
        limit: const Duration(seconds: 3));
    guest.startBattle();
    expect(await startedForGuest, isNull,
        reason: '손님이 시작할 수 있으면 방장이 준비하기 전에 판이 열린다');

    final startedHost = waitFor<BattleStarted>(hostSignals);
    final startedGuest = waitFor<BattleStarted>(guestSignals);
    host.startBattle();
    expect(await startedHost, isNotNull, reason: '방장이 눌렀으면 시작돼야 한다');
    expect(await startedGuest, isNotNull, reason: '손님에게도 시작이 가야 한다');

    // 조작이 넘어오는가 - 자리 번호는 우리가 안 적는데 서버가 붙여줘야 한다
    final heard = waitFor<BattlePeerInput>(hostSignals);
    guest.sendInput(1, bp.keyMask);
    final input = await heard;
    expect(input, isNotNull, reason: '조작이 안 넘어오면 상대 배가 멈춰 보인다');
    expect(input!.slot, theirs.slot, reason: '서버가 보낸 사람의 자리를 붙인다');
    expect(input.keys, bp.keyMask);
  }, timeout: const Timeout(Duration(seconds: 120)));
}
