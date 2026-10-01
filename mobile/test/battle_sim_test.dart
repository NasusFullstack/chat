/// 전투 계산이 파이썬과 **한 칸도 안 틀리는가**.
///
/// 조작(누른 키)만 주고받고 배와 포탄은 각자 계산한다. 계산이 조금이라도 갈리면 내
/// 화면에선 맞았는데 상대 화면에선 안 맞은 게 된다 - 오류도 안 나고 "쟤는 안 죽었다는데?"
/// 로만 나타나므로, 사람이 알아채기 전에 여기서 잡아야 한다.
///
/// 답안지는 파이썬이 뜬다: `python tests/dump_battle_cases.py`
/// 계산을 고치면 **답안지도 다시 뜨고** 둘 다 커밋할 것.
///
/// 특히 보는 것: **왼쪽·위로 날아가는 경우.** 파이썬의 `//` 는 아래로 내리고 Dart 의
/// `~/` 는 0 쪽으로 자르기 때문에 음수에서 답이 갈린다(`-7 // 2 == -4` vs `-7 ~/ 2 == -3`).
library;

import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

import 'package:chupchat/core/battle_sim.dart';

Map<String, Object?> loadCases() {
  final file = File('test/battle_cases.json');
  if (!file.existsSync()) {
    fail('답안지가 없다. python tests/dump_battle_cases.py 로 먼저 뜰 것');
  }
  return jsonDecode(file.readAsStringSync()) as Map<String, Object?>;
}

void main() {
  final data = loadCases();
  final constants = data['constants'] as Map<String, Object?>;

  group('상수가 파이썬과 같은가', () {
    // 하나만 달라도 전부 어긋난다. 그런데 어긋난 결과만 보면 어디가 원인인지
    // 알기 어려워서, 상수부터 따로 못 박아 둔다
    test('움직임과 전투장', () {
      expect(scale, constants['SCALE']);
      expect(fieldWidth, constants['FIELD_WIDTH']);
      expect(fieldHeight, constants['FIELD_HEIGHT']);
      expect(tickMs, constants['TICK_MS']);
      expect(accel, constants['ACCEL']);
      expect(maxSpeed, constants['MAX_SPEED']);
      expect(dragNum, constants['DRAG_NUM']);
      expect(dragDen, constants['DRAG_DEN']);
      expect(stopBelow, constants['STOP_BELOW']);
      expect(diag, constants['DIAG']);
      expect(directions, constants['DIRECTIONS']);
      expect(maxPlayers, constants['MAX_PLAYERS']);
    });

    test('야마토포와 체력', () {
      expect(chargeFullTicks, constants['CHARGE_FULL_TICKS']);
      expect(chargeMin, constants['CHARGE_MIN']);
      expect(shellSpeedMin, constants['SHELL_SPEED_MIN']);
      expect(shellSpeedMax, constants['SHELL_SPEED_MAX']);
      expect(shellLifeTicks, constants['SHELL_LIFE_TICKS']);
      expect(reloadTicks, constants['RELOAD_TICKS']);
      expect(shellRadius, constants['SHELL_RADIUS']);
      expect(shipRadius, constants['SHIP_RADIUS']);
      expect(maxHp, constants['MAX_HP']);
      expect(hpSegments, constants['HP_SEGMENTS']);
      expect(shellDamageMin, constants['SHELL_DAMAGE_MIN']);
      expect(shellDamageMax, constants['SHELL_DAMAGE_MAX']);
      expect(respawnTicks, constants['RESPAWN_TICKS']);
    });

    test('누른 키 비트', () {
      expect(keyLeft, constants['KEY_LEFT']);
      expect(keyRight, constants['KEY_RIGHT']);
      expect(keyUp, constants['KEY_UP']);
      expect(keyDown, constants['KEY_DOWN']);
      expect(keyFire, constants['KEY_FIRE']);
    });
  });

  test('32방향 표가 파이썬과 똑같다', () {
    // 여기가 1 만 달라도 그 방향으로 가는 배가 전부 어긋난다. sin/cos 는 플랫폼마다
    // 마지막 자리가 흔들릴 수 있어서 **표로 굳힌 값**을 대조한다
    final want = (data['directions'] as List)
        .map((pair) => (pair as List).map((v) => v as int).toList())
        .toList();
    expect(directionTable.length, want.length);
    for (var i = 0; i < want.length; i++) {
      expect(directionTable[i], want[i], reason: '$i번 방향이 다르다');
    }
  });

  group('나눗셈이 파이썬과 같은가', () {
    // 이 파일에서 가장 조용히 틀리는 자리다. Dart 의 ~/ 로 쓰면 음수에서 갈린다
    test('아래로 내린다(음수에서 ~/ 와 다르다)', () {
      expect(floorDiv(-7, 2), -4, reason: 'Dart 의 -7 ~/ 2 는 -3 이다');
      expect(floorDiv(7, 2), 3);
      expect(floorDiv(-8, 2), -4, reason: '딱 떨어지면 같다');
      expect(floorDiv(-1, 256), -1);
      expect(floorDiv(-255, 256), -1);
      expect(floorDiv(255, 256), 0);
    });

    test('정수 제곱근', () {
      expect(isqrt(0), 0);
      expect(isqrt(1), 1);
      expect(isqrt(8), 2);
      expect(isqrt(9), 3);
      expect(isqrt(10), 3);
      expect(isqrt(1600 * 1600 * 2), 2262, reason: '속도 상한 언저리');
      for (var n = 0; n < 2000; n++) {
        final r = isqrt(n);
        expect(r * r <= n && (r + 1) * (r + 1) > n, isTrue, reason: '$n');
      }
    });
  });

  group('판을 돌려서 대조한다', () {
    final cases = data['cases'] as List;
    for (final raw in cases) {
      final one = raw as Map<String, Object?>;
      final name = one['name'] as String;

      test(name, () {
        final slots = (one['slots'] as List).map((v) => v as int).toList();
        final ticks = one['ticks'] as int;
        final keys = (one['keys'] as List)
            .map((m) => (m as Map).map(
                (k, v) => MapEntry(int.parse(k as String), v as int)))
            .toList();
        final wantFrames = one['frames'] as List;
        final wantEvents = one['events'] as List;

        final battle = Battle(slots);
        final gotFrames = <Map<String, Object?>>[];
        final gotEvents = <Map<String, Object?>>[];

        for (var tick = 0; tick < ticks; tick++) {
          final happened = battle.advance(keys[tick]);
          for (final event in happened) {
            gotEvents.add({
              'tick': tick + 1,
              't': event.kind,
              'slot': event.slot,
              'by': event.by,
            });
          }
          if (tick < 5 || tick % 5 == 0 || tick >= ticks - 3) {
            gotFrames.add(battle.snapshot());
          }
        }

        expect(gotFrames.length, wantFrames.length);
        for (var i = 0; i < wantFrames.length; i++) {
          final want = wantFrames[i] as Map<String, Object?>;
          final got = gotFrames[i];
          expect(got['tick'], want['tick']);
          // 배를 한 척씩 견준다 - 통째로 비교하면 어디가 틀렸는지 안 보인다
          final wantShips = want['ships'] as List;
          final gotShips = got['ships'] as List;
          expect(gotShips.length, wantShips.length, reason: '${want['tick']}틱 배 수');
          for (var k = 0; k < wantShips.length; k++) {
            expect(gotShips[k], wantShips[k],
                reason: '${want['tick']}틱, $k번째 배\n'
                    '(자리, x, y, vx, vy, 방향, 체력, 재장전, 부활, 격추, 죽음)');
          }
          final wantShells = want['shells'] as List;
          final gotShells = got['shells'] as List;
          expect(gotShells.length, wantShells.length,
              reason: '${want['tick']}틱 포탄 수');
          for (var k = 0; k < wantShells.length; k++) {
            expect(gotShells[k], wantShells[k],
                reason: '${want['tick']}틱, $k번째 포탄 (쏜이, x, y, vx, vy, 수명)');
          }
        }

        expect(gotEvents.length, wantEvents.length,
            reason: '맞음·격추가 일어난 횟수가 다르다\n우리: $gotEvents\n파이썬: $wantEvents');
        for (var i = 0; i < wantEvents.length; i++) {
          final want = wantEvents[i] as Map<String, Object?>;
          expect(gotEvents[i]['tick'], want['tick'], reason: '$i번째가 다른 틱이다');
          expect(gotEvents[i]['t'], want['t']);
          expect(gotEvents[i]['slot'], want['slot']);
          expect(gotEvents[i]['by'], want['by']);
        }
      });
    }
  });
}
