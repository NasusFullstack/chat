/// 전투 화면 - 판을 돌리고, 그리고, 손가락 조작을 받는다.
///
/// PC 의 `gui/battle/arena.py` 와 **같은 방식**이다:
///  - 각자 자기 틱을 돌리고, 남의 조작은 도착하는 대로 "지금 눌린 키"로 반영한다
///    (틱을 맞추는 lockstep 이 아니다 - 지연이 6ms 남짓이라 눈에 안 띈다)
///  - **자기 배만 판정한다.** 남의 체력은 그 사람이 "나 맞았다"며 보내온 값을 따른다.
///    둘 다 깎으면 두 배로 닳는다
///  - 조작은 **바뀔 때만** 보낸다. 매 틱 보내면 규약 상한(초당 30줄)에 걸려 시작하자마자
///    끊긴다(PC 에서 실제로 겪었다). 가끔 같은 값이라도 한 번 보내 늦게 들어온 사람이
///    어긋난 채 남지 않게 한다
///
/// 화면 좌표는 **고정된 전투장(1200x800)** 이고, 그릴 때만 비율을 지켜 늘린다.
/// 폰 화면 크기가 제각각이어도 모두가 같은 판을 본다.
library;

import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../core/battle_protocol.dart' as bp;
import '../core/battle_sim.dart' as sim;
import '../net/battle_link.dart';

/// 같은 키라도 이만큼 지나면 한 번 더 보낸다(한 줄을 놓친 사람이 영영 어긋나지 않게)
const int resendTicks = 30;

class BattlePage extends StatefulWidget {
  const BattlePage({
    super.key,
    required this.link,
    required this.mySlot,
    required this.slots,
    required this.names,
  });

  final BattleLink link;
  final int mySlot;

  /// 이 판에 있는 자리들
  final List<int> slots;

  /// 자리 번호 -> 이름
  final Map<int, String> names;

  @override
  State<BattlePage> createState() => _BattlePageState();
}

class _BattlePageState extends State<BattlePage> {
  late final sim.Battle _battle;
  Timer? _timer;
  StreamSubscription<BattleSignal>? _sub;

  int _tick = 0;
  int _lastSentKeys = -1;
  int _lastSentTick = 0;

  /// 남이 지금 누르고 있는 키
  final Map<int, int> _peerKeys = {};

  /// 손가락 조작
  Offset _stick = Offset.zero;
  bool _firing = false;

  String _notice = '';

  @override
  void initState() {
    super.initState();
    // **내 배만 판정한다** - 남의 배는 그 사람이 알려줄 때만 깎인다
    _battle = sim.Battle(widget.slots, judged: {widget.mySlot});
    _sub = widget.link.signals.listen(_onSignal);
    _timer = Timer.periodic(const Duration(milliseconds: sim.tickMs), (_) => _advance());

    // 판이 가로로 긴 3:2 다. 세로로 들면 폭에 맞추느라 배가 너무 작아진다 -
    // 가로로 돌리면 같은 화면에서 훨씬 크게 보이고, 남는 좌우 여백에 조작을 둘 수 있어
    // **손가락이 전투장을 안 가린다**
    SystemChrome.setPreferredOrientations([
      DeviceOrientation.landscapeLeft,
      DeviceOrientation.landscapeRight,
    ]);
    // 상태줄·탐색바도 치운다(전투 중에 잘못 누르면 그대로 죽는다)
    SystemChrome.setEnabledSystemUIMode(SystemUiMode.immersiveSticky);
  }

  @override
  void dispose() {
    _timer?.cancel();
    _sub?.cancel();
    // 어떻게 나가든(뒤로가기 포함) 연결은 확실히 닫는다. 안 닫으면 서버는 내가
    // 아직 그 방에 있다고 보고, 남들 화면에는 **움직이지 않는 배**가 남는다
    widget.link.leave();
    widget.link.dispose();
    // 채팅으로 돌아가면 세로로 되돌린다 - 안 되돌리면 채팅이 가로로 남는다
    SystemChrome.setPreferredOrientations(DeviceOrientation.values);
    SystemChrome.setEnabledSystemUIMode(SystemUiMode.edgeToEdge);
    super.dispose();
  }

  void _onSignal(BattleSignal signal) {
    switch (signal) {
      case BattlePeerInput(:final slot, :final keys):
        // 도착하는 대로 반영한다(틱은 안 본다 - PC 와 같다)
        if (slot != widget.mySlot) _peerKeys[slot] = keys & bp.keyMask;
      case BattlePeerHurt(:final slot, :final by, :final hp, :final dead):
        _applyPeerHurt(slot, by, hp, dead);
      case BattlePeerLeft(:final slot):
        // 계산에서는 즉시 뺀다 - 나간 순간이 사람마다 달라서, 남아 있으면 누구
        // 화면에선 맞고 누구 화면에선 안 맞는다
        _battle.remove(slot);
        _peerKeys.remove(slot);
      case BattleFailed(:final why):
        setState(() => _notice = why);
      case BattleRefused(:final why):
        setState(() => _notice = why);
      default:
        break;
    }
  }

  void _applyPeerHurt(int slot, int by, int hp, bool dead) {
    if (slot == widget.mySlot) return;
    final ship = _battle.ships[slot];
    if (ship == null) return;
    if (dead) {
      ship.hp = 0;
      ship.deaths += 1;
      ship.respawnLeft = sim.respawnTicks;
      _battle.ships[by]?.kills += 1;
    } else {
      // **남은 체력을 그대로 따른다.** 최대 데미지를 깎으면 약하게 맞은 배가 내
      // 화면에서만 죽어 "보이지도 맞지도 않는 유령"이 된다
      ship.hp = hp.clamp(0, sim.maxHp);
    }
  }

  void _advance() {
    _tick += 1;
    final keys = _keysFromTouch();

    // 바뀔 때만 보낸다(매 틱 보내면 초당 30줄 상한에 걸려 끊긴다)
    if (keys != _lastSentKeys || _tick - _lastSentTick >= resendTicks) {
      _lastSentKeys = keys;
      _lastSentTick = _tick;
      widget.link.sendInput(_tick, keys);
    }

    final all = Map<int, int>.of(_peerKeys);
    all[widget.mySlot] = keys;

    for (final event in _battle.advance(all)) {
      // 계산이 내주는 건 **내 배**에 대한 것뿐이다(judged). 그 결과를 알려야
      // 남들 화면에서도 내 체력이 같아진다
      if (event.slot != widget.mySlot) continue;
      if (event.kind == 'hit') {
        widget.link.sendHit(event.by, _battle.ships[widget.mySlot]?.hp ?? 0);
      } else {
        widget.link.sendDead(event.by);
      }
    }
    // 한 틱 돌았으니 다시 그린다
    if (mounted) setState(() {});
  }

  /// 손가락 위치를 키 비트로. 조이스틱은 **네 방향으로 끊는다** - 배가 32방향으로
  /// 움직이는 건 속도에서 나오므로, 키는 PC 의 방향키와 같은 다섯 개면 된다
  int _keysFromTouch() {
    var keys = _firing ? sim.keyFire : 0;
    const dead = 0.25;      // 이보다 조금 밀린 건 안 민 것으로 본다(손 떨림)
    if (_stick.dx < -dead) keys |= sim.keyLeft;
    if (_stick.dx > dead) keys |= sim.keyRight;
    if (_stick.dy < -dead) keys |= sim.keyUp;
    if (_stick.dy > dead) keys |= sim.keyDown;
    return keys;
  }

  @override
  Widget build(BuildContext context) {
    final me = _battle.ships[widget.mySlot];
    return PopScope(
      // 뒤로가기로 바로 나가면 "그만두려던 게 아닌데" 가 된다 - 한 번 물어본다
      canPop: false,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) _askLeave();
      },
      child: Scaffold(
      backgroundColor: const Color(0xFF070910),
      body: SafeArea(
        child: LayoutBuilder(
          builder: (context, box) {
            // 그리는 쪽과 **같은 식**으로 전투장 자리를 잡는다 - 여기서 다르게 재면
            // 조작이 전투장 위에 걸친다
            final scale = math.min(
                box.maxWidth / sim.fieldWidth, box.maxHeight / sim.fieldHeight);
            final margin = (box.maxWidth - sim.fieldWidth * scale) / 2;

            // 폰마다 비율이 다르다. 좌우 여백에 조작을 넣으면 손가락이 전투장을
            // 안 가린다 - 다만 **딱 들어맞을 필요는 없다.** 바깥 가장자리에 붙이면
            // 조금 걸치는 정도는 가장자리라 배가 거의 안 다닌다.
            //
            // 실측: 갤S23+ 를 가로로 들면(851x393) 여백이 130.8px 인데 조이스틱이
            // 132px 다. 딱 맞아야 한다고 보면 '좁다'로 판정되어 화면 한가운데 쪽으로
            // 얹히는데, 가장자리에 붙이면 1.2px 만 걸친다
            const allowedOverlap = 20.0;
            final roomy = margin >= _Joystick.size - allowedOverlap;

            return Stack(
              children: [
                Positioned.fill(
                  child: CustomPaint(
                    painter: _ArenaPainter(
                      battle: _battle,
                      mySlot: widget.mySlot,
                      names: widget.names,
                      tick: _tick,
                    ),
                  ),
                ),
                Positioned(
                  left: 12,
                  top: 8,
                  child: _MyStatus(ship: me, notice: _notice),
                ),
                Positioned(
                  right: 4,
                  top: 0,
                  child: IconButton(
                    onPressed: _askLeave,
                    icon: const Icon(Icons.close, color: Colors.white70),
                    tooltip: '전투 그만두기',
                  ),
                ),
                // 왼쪽 방향키
                Positioned(
                  // 여백 가운데에 두되 **바깥으로는 안 나간다**(0 아래로 안 간다)
                  left: roomy
                      ? math.max(0, (margin - _Joystick.size) / 2)
                      : 20,
                  bottom: roomy ? (box.maxHeight - _Joystick.size) / 2 : 16,
                  child: Opacity(
                    opacity: roomy ? 1.0 : 0.45,
                    child: _Joystick(onMove: (v) => _stick = v),
                  ),
                ),
                // 오른쪽 발사 - **누르고 있으면 기가 찬다**
                Positioned(
                  right: roomy
                      ? math.max(0, (margin - _FireButton.size) / 2)
                      : 20,
                  bottom: roomy ? (box.maxHeight - _FireButton.size) / 2 : 16,
                  child: Opacity(
                    opacity: roomy ? 1.0 : 0.45,
                    child: _FireButton(
                      charge: (me?.charge ?? 0) / sim.chargeFullTicks,
                      reloading: (me?.reloadLeft ?? 0) > 0,
                      onDown: () => _firing = true,
                      onUp: () => _firing = false,
                    ),
                  ),
                ),
              ],
            );
          },
        ),
      ),
      ),
    );
  }

  Future<void> _askLeave() async {
    final yes = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('전투를 그만둘까요?'),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx, false), child: const Text('계속')),
          FilledButton(
              onPressed: () => Navigator.pop(ctx, true), child: const Text('그만두기')),
        ],
      ),
    );
    if (yes != true || !mounted) return;
    // 닫는 일은 dispose 가 한다 - 여기서도 닫으면 두 번이 된다
    Navigator.pop(context);
  }
}

/// 내 체력과 전적.
class _MyStatus extends StatelessWidget {
  const _MyStatus({required this.ship, required this.notice});

  final sim.Ship? ship;
  final String notice;

  @override
  Widget build(BuildContext context) {
    final hp = ship?.hp ?? 0;
    final down = (ship?.respawnLeft ?? 0) > 0;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SizedBox(
          width: 160,
          child: ClipRRect(
            borderRadius: BorderRadius.circular(3),
            child: LinearProgressIndicator(
              value: hp / sim.maxHp,
              minHeight: 8,
              backgroundColor: Colors.white24,
              valueColor: AlwaysStoppedAnimation(
                  hp > sim.maxHp ~/ 3 ? const Color(0xFF6BE675) : Colors.redAccent),
            ),
          ),
        ),
        const SizedBox(height: 4),
        Text(
          down
              ? '격추됨 - ${((ship!.respawnLeft * sim.tickMs) / 1000).ceil()}초 뒤 부활'
              : '격추 ${ship?.kills ?? 0} · 당함 ${ship?.deaths ?? 0}',
          style: const TextStyle(color: Colors.white70, fontSize: 12),
        ),
        if (notice.isNotEmpty)
          Text(notice, style: const TextStyle(color: Colors.orangeAccent, fontSize: 12)),
      ],
    );
  }
}

/// 왼쪽 엄지로 미는 조이스틱.
class _Joystick extends StatefulWidget {
  const _Joystick({required this.onMove});

  /// 바깥(배치하는 쪽)도 알아야 여백 가운데에 놓을 수 있다
  static const double size = 132;

  /// -1..1 범위의 밀린 정도
  final void Function(Offset) onMove;

  @override
  State<_Joystick> createState() => _JoystickState();
}

class _JoystickState extends State<_Joystick> {
  Offset _knob = Offset.zero;

  void _update(Offset local) {
    const center = Offset(_Joystick.size / 2, _Joystick.size / 2);
    var delta = local - center;
    final limit = _Joystick.size / 2 - 18;
    if (delta.distance > limit) delta = delta / delta.distance * limit;
    setState(() => _knob = delta);
    widget.onMove(Offset(delta.dx / limit, delta.dy / limit));
  }

  void _release() {
    setState(() => _knob = Offset.zero);
    widget.onMove(Offset.zero);
  }

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onPanStart: (d) => _update(d.localPosition),
      onPanUpdate: (d) => _update(d.localPosition),
      onPanEnd: (_) => _release(),
      onPanCancel: _release,
      child: Container(
        width: _Joystick.size,
        height: _Joystick.size,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          color: Colors.white.withValues(alpha: 0.06),
          border: Border.all(color: Colors.white24),
        ),
        child: Center(
          child: Transform.translate(
            offset: _knob,
            child: Container(
              width: 52,
              height: 52,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: Colors.white.withValues(alpha: 0.22),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// 오른쪽 발사 단추 - 누르고 있으면 기가 찬다.
class _FireButton extends StatelessWidget {
  /// 바깥(배치하는 쪽)도 알아야 여백 가운데에 놓을 수 있다
  static const double size = 108;

  const _FireButton({
    required this.charge,
    required this.reloading,
    required this.onDown,
    required this.onUp,
  });

  final double charge;
  final bool reloading;
  final VoidCallback onDown;
  final VoidCallback onUp;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTapDown: (_) => onDown(),
      onTapUp: (_) => onUp(),
      onTapCancel: onUp,
      child: SizedBox(
        width: size,
        height: size,
        child: Stack(
          alignment: Alignment.center,
          children: [
            // 모은 정도를 테두리로 보여준다 - 꽉 차면 세고 빠르게 나간다
            SizedBox(
              width: size,
              height: size,
              child: CircularProgressIndicator(
                value: charge.clamp(0.0, 1.0),
                strokeWidth: 6,
                backgroundColor: Colors.white12,
                valueColor: AlwaysStoppedAnimation(
                    charge >= 1 ? const Color(0xFFFFD36B) : Colors.white54),
              ),
            ),
            Container(
              width: 84,
              height: 84,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: reloading
                    ? Colors.white10
                    : Colors.redAccent.withValues(alpha: 0.75),
              ),
              child: const Center(
                child: Text('발사',
                    style: TextStyle(
                        color: Colors.white, fontWeight: FontWeight.bold)),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// 전투장을 그린다 - 고정 좌표(1200x800)를 화면에 **비율을 지켜** 얹는다.
///
/// 늘려 찌그러뜨리면 맞음 판정과 눈이 어긋난다. 남는 쪽에는 여백을 둔다.
class _ArenaPainter extends CustomPainter {
  _ArenaPainter({
    required this.battle,
    required this.mySlot,
    required this.names,
    required this.tick,
  });

  final sim.Battle battle;
  final int mySlot;
  final Map<int, String> names;
  final int tick;

  @override
  void paint(Canvas canvas, Size size) {
    final scale = math.min(size.width / sim.fieldWidth, size.height / sim.fieldHeight);
    final offset = Offset(
      (size.width - sim.fieldWidth * scale) / 2,
      (size.height - sim.fieldHeight * scale) / 2,
    );

    Offset place(double fx, double fy) =>
        Offset(offset.dx + fx * scale, offset.dy + fy * scale);

    // 전투장 테두리
    final field = Rect.fromLTWH(offset.dx, offset.dy,
        sim.fieldWidth * scale, sim.fieldHeight * scale);
    canvas.drawRect(field, Paint()..color = const Color(0xFF0D1020));
    canvas.drawRect(
        field,
        Paint()
          ..style = PaintingStyle.stroke
          ..strokeWidth = 1
          ..color = Colors.white12);

    // 포탄
    for (final shell in battle.shells) {
      final power = shell.power / 100;
      canvas.drawCircle(
        place(shell.px, shell.py),
        (3 + 4 * power) * scale,
        Paint()
          ..color = Color.lerp(
              const Color(0xFFBFD4FF), const Color(0xFFFFD36B), power)!,
      );
    }

    // 배
    for (final slot in battle.ships.keys.toList()..sort()) {
      final ship = battle.ships[slot]!;
      if (!ship.alive) continue;
      _drawShip(canvas, place(ship.px, ship.py), scale, ship, slot == mySlot);
    }
  }

  void _drawShip(
      Canvas canvas, Offset at, double scale, sim.Ship ship, bool mine) {
    // 32방향을 각도로. 위쪽이 0도이고 시계방향이다(계산 쪽과 같은 기준)
    final angle = ship.facing * (2 * math.pi / sim.directions);
    canvas.save();
    canvas.translate(at.dx, at.dy);
    canvas.rotate(angle);

    final body = Path()
      ..moveTo(0, -26 * scale)
      ..lineTo(15 * scale, 16 * scale)
      ..lineTo(0, 9 * scale)
      ..lineTo(-15 * scale, 16 * scale)
      ..close();
    canvas.drawPath(
        body,
        Paint()
          ..color = mine ? const Color(0xFF8FE3A0) : const Color(0xFFE38F9E));
    canvas.restore();

    // 체력 막대 - 남의 배는 이것만 보고 판단하게 된다
    final width = 36 * scale;
    final top = at.dy - 36 * scale;
    canvas.drawRect(
        Rect.fromLTWH(at.dx - width / 2, top, width, 4 * scale),
        Paint()..color = Colors.white24);
    canvas.drawRect(
        Rect.fromLTWH(at.dx - width / 2, top,
            width * (ship.hp / sim.maxHp).clamp(0.0, 1.0), 4 * scale),
        Paint()
          ..color = ship.hp > sim.maxHp ~/ 3
              ? const Color(0xFF6BE675)
              : Colors.redAccent);

    final name = names[ship.slot] ?? '';
    if (name.isNotEmpty) {
      final painter = TextPainter(
        text: TextSpan(
            text: name,
            style: TextStyle(color: Colors.white70, fontSize: 11 * scale)),
        textDirection: TextDirection.ltr,
      )..layout();
      painter.paint(canvas, Offset(at.dx - painter.width / 2, top - 14 * scale));
    }
  }

  @override
  bool shouldRepaint(covariant _ArenaPainter old) => true;
}
