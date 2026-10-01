/// 전투 중계 서버와의 연결 하나 - 전투 중에만 붙는다.
///
/// **평소에는 아무 연결도 없다.** '배틀크루저 전투'를 친 순간에 붙었다가 판이 끝나면
/// 끊는다. PC 의 `gui/battle/net.py` 와 같은 일을 한다.
///
/// ## 받은 줄은 그대로 믿지 않는다
/// 서버가 보낸 것이라도 그 서버에는 남이 붙어 있다. 전부
/// `battle_protocol.decode()` 를 거치고, 거기서 걸러진 것은 조용히 버린다.
///
/// ## 인증서는 보통대로 검사한다
/// IRC 서버에 쓰는 지문 고정(trusted_certs.dart)을 여기 갖다 쓰면 안 된다 - 중계
/// 서버는 정식 인증서라 그럴 이유가 없고, 가로채는 환경에서는 지문이 사람마다 달라
/// 전부 막힌다(PC 쪽에 같은 설명이 있다).
library;

import 'dart:async';
import 'dart:convert';

import 'package:web_socket_channel/web_socket_channel.dart';

import '../core/battle_protocol.dart' as bp;
import '../core/relay.dart' as relay;

/// 이 안에 못 붙으면 포기한다. 방화벽이 조용히 버리면 성공도 실패도 안 오고 매달린다
const Duration connectTimeout = Duration(seconds: 12);

/// 대기방에 보이는 사람 하나.
class BattlePlayer {
  const BattlePlayer(this.slot, this.nick, this.color);

  final int slot;
  final String nick;
  final int color;
}

/// 전투 중에 일어나는 일들. 화면은 이것만 본다
sealed class BattleSignal {
  const BattleSignal();
}

/// 자리를 받았다(대기방에 들어갔다).
class BattleJoined extends BattleSignal {
  const BattleJoined(this.slot, this.color, this.cap, this.players, this.bots);

  final int slot;
  final int color;
  final int cap;
  final List<BattlePlayer> players;
  final int bots;
}

class BattlePeerJoined extends BattleSignal {
  const BattlePeerJoined(this.slot, this.nick, this.color);

  final int slot;
  final String nick;
  final int color;
}

class BattlePeerLeft extends BattleSignal {
  const BattlePeerLeft(this.slot);

  final int slot;
}

/// 판이 시작됐다.
class BattleStarted extends BattleSignal {
  const BattleStarted();
}

/// 남이 누른 키가 왔다.
class BattlePeerInput extends BattleSignal {
  const BattlePeerInput(this.slot, this.tick, this.keys);

  final int slot;
  final int tick;
  final int keys;
}

/// 남이 "나 맞았다"고 알려왔다. **남은 체력을 그대로 따른다** - 받는 쪽이 얼마나
/// 깎을지 몰라도 되고, 한 줄을 놓쳐도 다음 보고에서 저절로 맞는다
class BattlePeerHurt extends BattleSignal {
  const BattlePeerHurt(this.slot, this.by, this.hp, {required this.dead});

  final int slot;
  final int by;
  final int hp;
  final bool dead;
}

/// 서버가 안 받아줬다(정원이 찼거나 이미 시작했거나).
class BattleRefused extends BattleSignal {
  const BattleRefused(this.why);

  final String why;
}

/// 못 붙었거나 끊겼다. 조용히 실패하면 사람이 이유를 모른다
class BattleFailed extends BattleSignal {
  const BattleFailed(this.why);

  final String why;
}

class BattleLink {
  WebSocketChannel? _socket;
  StreamSubscription<Object?>? _sub;
  Timer? _timer;

  final _signals = StreamController<BattleSignal>.broadcast();

  /// 일어나는 일들. 화면이 여기만 듣는다
  Stream<BattleSignal> get signals => _signals.stream;

  String room = '';

  /// 이 판에서 쓰는 내 이름. 자리를 다시 잡을 때 그대로 쓴다
  String nick = '';
  int _color = 0;
  int _cap = bp.maxHumans;
  int _bots = 0;

  /// 내 자리 번호. 아직 못 들어갔으면 -1
  int mySlot = -1;

  /// 일부러 닫는 중인가(나가기). 그때의 끊김은 사고가 아니다
  bool _closing = false;

  bool get isOpen => _socket != null;

  /// 방에 들어간다. **여기서 비로소 연결이 생긴다.**
  Future<void> join(String room, String nick,
      {int color = 0, int cap = bp.maxHumans, int bots = 0}) async {
    this.room = room;
    this.nick = nick;
    _color = color;
    _cap = cap;
    _bots = bots;
    _closing = false;
    mySlot = -1;

    try {
      final socket = WebSocketChannel.connect(Uri.parse(relay.battleUrl));
      _socket = socket;
      // 붙을 때까지 기다린다 - 방화벽이 조용히 버리면 여기서 걸린다
      _timer?.cancel();
      _timer = Timer(connectTimeout, () {
        if (mySlot < 0) {
          _fail('전투 서버에 연결하지 못했습니다. 잠시 뒤 다시 시도해 주세요.');
          _closeQuietly();
        }
      });
      _sub = socket.stream.listen(
        _onText,
        onError: (Object error) => _fail('전투 서버 연결에 실패했습니다: $error'),
        onDone: () {
          // 일부러 닫은 것은 사고가 아니다
          if (!_closing) _fail('전투 서버와의 연결이 끊겼습니다.');
          _socket = null;
        },
        cancelOnError: true,
      );
      await socket.ready;
      _send(bp.joinMessage(room, nick, color: color, cap: cap, bots: bots));
    } on Object catch (error) {
      _fail('전투 서버에 연결하지 못했습니다: $error');
      _closeQuietly();
    }
  }

  /// 자리를 다시 잡는다(색이나 정원을 바꿀 때).
  ///
  /// **끊김을 사고로 보지 않는다** - 닫고 바로 다시 붙으면 뒤늦게 오는 '끊겼다'가
  /// 새 연결의 사고로 읽혀 전투가 통째로 취소된다(PC 에서 실제로 그랬다).
  Future<void> rejoin(String room, String nick,
      {int color = 0, int cap = bp.maxHumans, int bots = 0}) async {
    _closing = true;
    await _closeQuietly();
    await join(room, nick, color: color, cap: cap, bots: bots);
  }

  /// 판이 끝났다 - 확실히 닫는다(열어둔 채 잊히지 않게).
  Future<void> leave() async {
    _closing = true;
    _timer?.cancel();
    if (isOpen) _send(bp.byeMessage());
    await _closeQuietly();
    mySlot = -1;
  }

  void dispose() {
    _timer?.cancel();
    _sub?.cancel();
    _socket?.sink.close();
    _signals.close();
  }

  // ---------------------------------------------------------------- 보내기
  /// 시작하자(방을 연 사람만 먹힌다 - 서버가 판단한다).
  void startBattle() => _send(bp.startMessage());

  /// 누른 키. **자리 번호는 안 보낸다** - 서버가 어느 연결로 왔는지 보고 붙인다
  void sendInput(int tick, int keys) =>
      _send(bp.inputMessage(tick, keys & bp.keyMask));

  /// 맞았다 - 남은 체력을 같이 보낸다
  void sendHit(int by, int hp) => _send(bp.hitMessage(by, hp < 0 ? 0 : hp));

  void sendDead(int by) => _send(bp.deadMessage(by, 0));

  void _send(Map<String, Object?> message) {
    final socket = _socket;
    if (socket == null) return;
    final line = bp.encode(message);
    if (line.isEmpty) return;      // 너무 긴 줄은 아예 안 보낸다
    try {
      socket.sink.add(line);
    } on Object {
      // 이미 닫힌 연결에 쓰는 건 사고가 아니다
    }
  }

  // ---------------------------------------------------------------- 받기
  void _onText(Object? raw) {
    final text = raw is String ? raw : (raw is List<int> ? utf8.decode(raw) : '');
    final message = bp.decode(text);
    if (message == null) return;   // 모르는 값은 조용히 버린다
    final handler = _handlers[message['t']];
    if (handler != null) handler(this, message);
  }

  void _fail(String why) {
    if (_signals.isClosed) return;
    _signals.add(BattleFailed(why));
  }

  Future<void> _closeQuietly() async {
    _timer?.cancel();
    await _sub?.cancel();
    _sub = null;
    try {
      await _socket?.sink.close();
    } on Object {
      // 이미 닫혔을 수 있다
    }
    _socket = null;
  }

  /// 새 종류가 생기면 여기 한 줄만 추가한다(if/elif 사슬을 만들지 않는다)
  static final Map<Object?, void Function(BattleLink, Map<String, Object?>)>
      _handlers = {
    bp.tWelcome: (link, m) {
      link._timer?.cancel();
      link.mySlot = m['slot']! as int;
      link._color = m['color']! as int;
      link._cap = m['cap']! as int;
      link._bots = (m['bots'] ?? 0) as int;
      final players = [
        for (final raw in m['players']! as List)
          BattlePlayer((raw as Map)['slot']! as int, '${raw['nick']}',
              raw['color']! as int)
      ];
      link._signals.add(BattleJoined(
          link.mySlot, link._color, link._cap, players, link._bots));
      if (m['started'] == true) link._signals.add(const BattleStarted());
    },
    bp.tDeny: (link, m) {
      link._closing = true;
      link._signals.add(BattleRefused('${m['why']}'));
      link._closeQuietly();
    },
    bp.tJoined: (link, m) => link._signals.add(
        BattlePeerJoined(m['slot']! as int, '${m['nick']}', m['color']! as int)),
    bp.tLeft: (link, m) =>
        link._signals.add(BattlePeerLeft(m['slot']! as int)),
    bp.tStarted: (link, _) => link._signals.add(const BattleStarted()),
    bp.tPeerInput: (link, m) => link._signals.add(BattlePeerInput(
        m['slot']! as int, m['tick']! as int, m['keys']! as int)),
    bp.tPeerHit: (link, m) => link._signals.add(BattlePeerHurt(
        m['slot']! as int, m['by']! as int, m['hp']! as int,
        dead: false)),
    bp.tPeerDead: (link, m) => link._signals.add(BattlePeerHurt(
        m['slot']! as int, m['by']! as int, m['hp']! as int,
        dead: true)),
  };
}
