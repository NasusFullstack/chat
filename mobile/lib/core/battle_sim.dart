/// 전투 한 판의 계산 - 화면도 소켓도 모르는 순수 코드.
///
/// `battle_sim.py`를 그대로 옮긴 것이다. **답이 한 칸이라도 달라지면 안 된다** -
/// 조작(누른 키)만 주고받고 배와 포탄은 각자 계산하기 때문에, 계산이 갈리면 내
/// 화면에선 맞았는데 상대 화면에선 안 맞은 게 된다. 오류도 안 나고 "쟤는 안 죽었다는데?"
/// 로만 나타난다.
///
/// 그래서 파이썬이 매 틱의 상태를 적어둔 답안지와 대조한다
/// (`tests/dump_battle_cases.py` → `test/battle_cases.json` → `test/battle_sim_test.dart`).
///
/// ## 옮길 때 가장 위험했던 것: 나눗셈
/// 파이썬의 `//` 는 **아래로 내림**이고 Dart 의 `~/` 는 **0 쪽으로 자른다.**
/// 음수에서 답이 갈린다: `-7 // 2 == -4` 인데 `-7 ~/ 2 == -3`.
///
/// 전투 계산에는 음수가 널렸다 - 왼쪽·위로 가면 속도가 음수이고, 방향표의 성분도
/// 절반이 음수다. 그래서 이 파일에서는 `~/` 를 **쓰지 않고** [floorDiv]만 쓴다.
/// 하나라도 빠뜨리면 왼쪽 위로 날아가는 배만 조금씩 어긋나다가 한참 뒤에 포탄이
/// 빗나간다 - 재현하기도 어려운 종류다.
library;

/// 1칸 = 256. 좌표와 속도는 전부 이 단위의 정수다
const int scale = 256;

/// 전투장 크기는 **모두에게 똑같이 고정**한다. 화면 크기를 쓰면 창이 다른 사람끼리
/// 배 위치가 갈린다 - 그리는 쪽에서 자기 화면에 맞춰 비율대로 늘려 그린다
const int fieldWidth = 1200;
const int fieldHeight = 800;

/// 약 30fps. 아래 움직임 값은 전부 '틱당'이라 이 길이를 바꾸면 같이 환산해야 한다
const int tickMs = 33;

const int accel = 111;
const int maxSpeed = 1600;
const int dragNum = 9185;
const int dragDen = 10000;
const int stopBelow = 10;

/// 대각선이 더 빨라지지 않게 나눌 값. sqrt(2) 를 1/256 단위로
const int diag = 362;

const double turnStepDeg = 11.25;
const int directions = 32;

/// 야마토포 - 기를 모아 쏜다
const int chargeFullTicks = 30;
const int chargeMin = 6;
const int shellSpeedMin = 2200;
const int shellSpeedMax = 6600;
const int shellLifeTicks = 43;
const int reloadTicks = 12;
const int shellRadius = 6 * scale;
const int shipRadius = 26 * scale;

const int maxHp = 500;
const int hpSegments = 10;
const int shellDamageMin = 70;
const int shellDamageMax = 260;
const int respawnTicks = 86;

/// 한 판에 들어갈 수 있는 최대 인원(사람 6 + 연습 상대 6). battle_protocol.py 와 같다
const int maxPlayers = 12;

/// 누른 키 비트. battle_protocol.py 와 **같은 값이어야 한다**
const int keyLeft = 1;
const int keyRight = 2;
const int keyUp = 4;
const int keyDown = 8;
const int keyFire = 16;
const int keyMask = keyLeft | keyRight | keyUp | keyDown | keyFire;

/// 파이썬의 `//` 와 **같은** 나눗셈(아래로 내림).
///
/// Dart 의 `~/` 는 0 쪽으로 자르기 때문에 음수에서 답이 다르다. 이 파일에서는
/// 나눗셈을 전부 이걸로 한다 - 하나만 빠뜨려도 한쪽으로 날아가는 배가 어긋난다.
int floorDiv(int a, int b) {
  final q = a ~/ b;
  // 부호가 다르고 딱 떨어지지 않으면 한 칸 더 내린다
  if ((a % b != 0) && ((a < 0) != (b < 0))) return q - 1;
  return q;
}

/// 정확한 정수 제곱근(파이썬 `math.isqrt` 와 같다).
///
/// `sqrt()` 로 하면 부동소수가 끼어들어 큰 값에서 1 차이가 날 수 있다 - 그 1이
/// 속도 상한을 가르고, 그러면 그때부터 좌표가 통째로 갈린다.
int isqrt(int n) {
  if (n < 0) throw ArgumentError('음수의 제곱근은 없다: $n');
  if (n < 2) return n;
  // 뉴턴법 - 정수로만 돈다
  var x = n;
  var y = (x + 1) >> 1;
  while (y < x) {
    x = y;
    y = (x + n ~/ x) >> 1;
  }
  return x;
}

/// 32방향 단위벡터를 1/256 단위 정수로.
///
/// **여기서만 sin/cos 를 쓴다.** 한 번 계산해 표로 굳히므로 그 뒤의 계산에는
/// 부동소수가 끼어들지 않는다. 파이썬이 만든 표와 같은지는 검사가 대조한다.
List<List<int>> _buildDirectionTable() {
  const twoPi = 6.283185307179586;
  final table = <List<int>>[];
  for (var step = 0; step < directions; step++) {
    final radians = step * turnStepDeg * twoPi / 360.0;
    // 화면과 같은 기준: 위쪽(-y)이 0도, 시계방향으로 증가
    table.add([_round(_sin(radians) * scale), _round(-_cos(radians) * scale)]);
  }
  return table;
}

double _sin(double x) => _cos(x - 1.5707963267948966);

/// cos 를 급수로 직접 센다.
///
/// `dart:math` 의 cos 를 그냥 쓰지 않는 이유: 플랫폼마다 libm 구현이 달라 마지막
/// 자리가 흔들릴 수 있다. 표로 굳히기 전 한 번뿐이지만, 그 한 번이 틀리면 배가
/// 영영 다른 쪽으로 날아간다. 여기 쓰는 각도(0~2π)에서는 이 급수로 충분하다.
double _cos(double x) {
  const twoPi = 6.283185307179586;
  var a = x % twoPi;
  if (a > 3.141592653589793) a -= twoPi;
  if (a < -3.141592653589793) a += twoPi;
  var term = 1.0;
  var sum = 1.0;
  for (var n = 1; n <= 12; n++) {
    term *= -a * a / ((2 * n - 1) * (2 * n));
    sum += term;
  }
  return sum;
}

/// 파이썬 `round()` 와 같게 - 0.5 는 짝수 쪽으로.
///
/// Dart 의 `.round()` 는 0.5 를 바깥쪽으로 올린다. 방향표에 0.5 가 딱 떨어지는
/// 값은 없지만, 다르면 표 하나가 1 차이 나고 그 방향으로 가는 배가 전부 어긋난다
int _round(double value) {
  final floor = value.floor();
  final rest = value - floor;
  if (rest > 0.5) return floor + 1;
  if (rest < 0.5) return floor;
  return floor.isEven ? floor : floor + 1;
}

final List<List<int>> directionTable = _buildDirectionTable();

/// 배 한 척. 좌표와 속도는 전부 1/256 픽셀 단위 정수다.
class Ship {
  Ship(this.slot, this.x, this.y, [this.facing = 0]);

  final int slot;
  int x;
  int y;
  int vx = 0;
  int vy = 0;
  int facing;
  int hp = maxHp;
  int reloadLeft = 0;

  /// 기를 모은 정도(스페이스를 누르고 있는 틱 수)
  int charge = 0;
  int respawnLeft = 0;
  int kills = 0;
  int deaths = 0;

  bool get alive => hp > 0;

  /// 화면에 그릴 좌표(픽셀). **계산에는 절대 쓰지 말 것** - 부동소수다
  double get px => x / scale;
  double get py => y / scale;
}

/// 야마토포 포탄 하나.
class Shell {
  Shell(this.owner, this.x, this.y, this.vx, this.vy);

  final int owner;
  int x;
  int y;
  int vx;
  int vy;
  int life = shellLifeTicks;

  /// 얼마나 모아서 쏜 것인가(0~100)
  int power = 100;

  double get px => x / scale;
  double get py => y / scale;
}

/// 이번 틱에 일어난 일.
class BattleEvent {
  const BattleEvent(this.kind, this.slot, this.by);

  /// 'hit'(맞음) 또는 'dead'(격추)
  final String kind;
  final int slot;
  final int by;

  @override
  String toString() => '$kind(slot=$slot, by=$by)';
}

/// 움직이는 방향에 가장 가까운 32방향 번호. 안 움직이면 보던 쪽 그대로.
///
/// 표에서 가장 가까운 것을 고르므로 atan2 가 필요 없다(정수 비교만 한다).
int facingFrom(int dx, int dy, int current) {
  if (dx == 0 && dy == 0) return current;
  var best = current;
  int? bestScore;
  for (var index = 0; index < directionTable.length; index++) {
    final ux = directionTable[index][0];
    final uy = directionTable[index][1];
    final score = dx * ux + dy * uy;
    // 같은 점수면 **먼저 나온 것**을 쓴다(파이썬과 같게)
    if (bestScore == null || score > bestScore) {
      best = index;
      bestScore = score;
    }
  }
  return best;
}

/// 한 판. [advance]를 틱마다 부르면 그때 일어난 일을 돌려준다.
class Battle {
  Battle(
    Iterable<int> slots, {
    int width = fieldWidth,
    int height = fieldHeight,
    int seedFacing = 0,
    Iterable<int>? judged,
  })  : width = width * scale,
        height = height * scale {
    final sorted = slots.toList()..sort();
    for (final slot in sorted) {
      final start = _startPosition(slot);
      ships[slot] = Ship(slot, start[0], start[1], seedFacing);
    }
    // **내가 맞았는지 판정할 배들.** 안 나누면 같은 피격이 두 번 깎인다 - 내 화면에서
    // 한 번, 그 사람이 "나 맞았다"고 알려와서 또 한 번. 아무것도 안 주면 전부 판정한다
    this.judged = judged == null ? ships.keys.toSet() : judged.toSet();
  }

  final int width;
  final int height;
  int tick = 0;
  final Map<int, Ship> ships = {};
  List<Shell> shells = [];
  late final Set<int> judged;

  List<int> _startPosition(int slot) {
    // 자리 번호로 정해지는 시작 자리 - 모두에게 같아야 하므로 계산으로 정한다.
    // 전투장 한가운데를 중심으로 원을 그리며 늘어놓는다
    final step = directions ~/ maxPlayers;
    final dir = directionTable[(slot * step) % directions];
    final radiusX = floorDiv(width * 7, 20);
    final radiusY = floorDiv(height * 7, 20);
    return [
      floorDiv(width, 2) + floorDiv(dir[0] * radiusX, scale),
      floorDiv(height, 2) + floorDiv(dir[1] * radiusY, scale),
    ];
  }

  /// 한 틱 진행한다. [keysBySlot]은 {자리번호: 누른 키 비트}.
  ///
  /// **자리 번호 순서대로 처리한다.** 조작이 도착하는 순서는 사람마다 다른데,
  /// 그 순서에 따라 결과가 달라지면 안 되기 때문이다.
  List<BattleEvent> advance(Map<int, int> keysBySlot) {
    tick += 1;
    final events = <BattleEvent>[];
    final order = ships.keys.toList()..sort();

    for (final slot in order) {
      final keys = (keysBySlot[slot] ?? 0) & keyMask;
      _move(ships[slot]!, keys);
    }
    for (final slot in order) {
      final keys = (keysBySlot[slot] ?? 0) & keyMask;
      _maybeFire(ships[slot]!, keys);
    }
    events.addAll(_moveShells());
    return events;
  }

  void _move(Ship ship, int keys) {
    if (!ship.alive) {
      if (ship.respawnLeft > 0) {
        ship.respawnLeft -= 1;
        if (ship.respawnLeft == 0) _revive(ship);
      }
      return;
    }

    if (ship.reloadLeft > 0) ship.reloadLeft -= 1;

    final dx = ((keys & keyRight) != 0 ? 1 : 0) - ((keys & keyLeft) != 0 ? 1 : 0);
    final dy = ((keys & keyDown) != 0 ? 1 : 0) - ((keys & keyUp) != 0 ? 1 : 0);

    if (dx != 0 || dy != 0) {
      if (dx != 0 && dy != 0) {
        // 대각선이 더 빨라지지 않게 나눈다
        ship.vx += floorDiv(accel * dx * scale, diag);
        ship.vy += floorDiv(accel * dy * scale, diag);
      } else {
        ship.vx += accel * dx;
        ship.vy += accel * dy;
      }
      final speed = isqrt(ship.vx * ship.vx + ship.vy * ship.vy);
      if (speed > maxSpeed) {
        ship.vx = floorDiv(ship.vx * maxSpeed, speed);
        ship.vy = floorDiv(ship.vy * maxSpeed, speed);
      }
      ship.facing = facingFrom(ship.vx, ship.vy, ship.facing);
    } else {
      ship.vx = floorDiv(ship.vx * dragNum, dragDen);
      ship.vy = floorDiv(ship.vy * dragNum, dragDen);
      if (-stopBelow < ship.vx && ship.vx < stopBelow) ship.vx = 0;
      if (-stopBelow < ship.vy && ship.vy < stopBelow) ship.vy = 0;
    }

    ship.x += ship.vx;
    ship.y += ship.vy;
    // 전투장 밖으로는 못 나간다. 벽에 닿으면 그쪽 속도를 죽인다(튕기면 조종이 어렵다)
    if (ship.x < 0) {
      ship.x = 0;
      ship.vx = 0;
    } else if (ship.x > width) {
      ship.x = width;
      ship.vx = 0;
    }
    if (ship.y < 0) {
      ship.y = 0;
      ship.vy = 0;
    } else if (ship.y > height) {
      ship.y = height;
      ship.vy = 0;
    }
  }

  /// 기를 모으고, 손을 떼면 쏜다.
  void _maybeFire(Ship ship, int keys) {
    if (!ship.alive) {
      ship.charge = 0;
      return;
    }
    final holding = (keys & keyFire) != 0;
    if (holding) {
      if (ship.reloadLeft == 0 && ship.charge < chargeFullTicks) ship.charge += 1;
      return;
    }
    if (ship.charge == 0) return;
    final charge = ship.charge;
    ship.charge = 0;
    if (charge < chargeMin) return;  // 스친 정도 - 안 쏜다

    final power = (() {
      final value = floorDiv(charge * 100, chargeFullTicks);
      return value < 100 ? value : 100;
    })();
    final speed =
        shellSpeedMin + floorDiv((shellSpeedMax - shellSpeedMin) * power, 100);
    final dir = directionTable[ship.facing];
    final shell = Shell(
      ship.slot,
      ship.x + floorDiv(floorDiv(dir[0] * shipRadius, scale), scale) * scale,
      ship.y + floorDiv(floorDiv(dir[1] * shipRadius, scale), scale) * scale,
      floorDiv(dir[0] * speed, scale),
      floorDiv(dir[1] * speed, scale),
    );
    shell.power = power;
    shells.add(shell);
    ship.reloadLeft = reloadTicks;
  }

  List<BattleEvent> _moveShells() {
    final events = <BattleEvent>[];
    final alive = <Shell>[];
    final hitRadius = shipRadius + shellRadius;
    final order = ships.keys.toList()..sort();

    for (final shell in shells) {
      shell.x += shell.vx;
      shell.y += shell.vy;
      shell.life -= 1;
      if (shell.life <= 0 ||
          !(0 <= shell.x && shell.x <= width && 0 <= shell.y && shell.y <= height)) {
        continue;  // 수명이 다했거나 전투장 밖 - 사라진다
      }

      Ship? struck;
      for (final slot in order) {
        final ship = ships[slot]!;
        if (slot == shell.owner || !ship.alive) continue;
        final dx = ship.x - shell.x;
        final dy = ship.y - shell.y;
        if (dx * dx + dy * dy <= hitRadius * hitRadius) {
          struck = ship;
          break;
        }
      }
      if (struck == null) {
        alive.add(shell);
        continue;
      }

      // 포탄은 어느 배에 닿든 여기서 사라진다(관통하는 것처럼 안 보이게). 다만
      // **체력을 깎는 건 내가 판정하는 배뿐이다** - 남의 배는 그 사람이 알려줄 때만
      if (!judged.contains(struck.slot)) continue;

      final damage =
          shellDamageMin + floorDiv((shellDamageMax - shellDamageMin) * shell.power, 100);
      struck.hp -= damage;
      if (struck.hp > 0) {
        events.add(BattleEvent('hit', struck.slot, shell.owner));
      } else {
        struck.hp = 0;
        struck.deaths += 1;
        struck.respawnLeft = respawnTicks;
        final shooter = ships[shell.owner];
        if (shooter != null) shooter.kills += 1;
        events.add(BattleEvent('dead', struck.slot, shell.owner));
      }
    }
    shells = alive;
    return events;
  }

  /// 전투에서 빠진다(그만뒀거나 연결이 끊겼거나).
  ///
  /// **바로 없앤다.** 추락 연출은 화면이 따로 그린다 - 나간 순간이 사람마다 몇 ms씩
  /// 다른데 그동안 배가 남아 있으면 누구 화면에선 맞고 누구 화면에선 안 맞는다.
  /// 떠난 사람이 쏴둔 포탄은 그대로 날아간다(이미 나간 것이라 없애면 더 갈린다).
  bool remove(int slot) => ships.remove(slot) != null;

  void _revive(Ship ship) {
    ship.hp = maxHp;
    ship.vx = 0;
    ship.vy = 0;
    final start = _startPosition(ship.slot);
    ship.x = start[0];
    ship.y = start[1];
  }

  /// 지금 상태를 견줘보기 좋은 모양으로. 파이썬의 `snapshot()` 과 같은 순서다
  Map<String, Object?> snapshot() {
    final order = ships.keys.toList()..sort();
    return {
      'tick': tick,
      'ships': [
        for (final slot in order)
          [
            ships[slot]!.slot,
            ships[slot]!.x,
            ships[slot]!.y,
            ships[slot]!.vx,
            ships[slot]!.vy,
            ships[slot]!.facing,
            ships[slot]!.hp,
            ships[slot]!.reloadLeft,
            ships[slot]!.respawnLeft,
            ships[slot]!.kills,
            ships[slot]!.deaths,
          ]
      ],
      'shells': [
        for (final s in shells) [s.owner, s.x, s.y, s.vx, s.vy, s.life]
      ],
    };
  }
}
