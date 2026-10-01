/// 전투 중계 서버와 주고받는 줄 - 만들고, **전부 검사해서** 읽는다.
///
/// `battle_protocol.py`를 옮긴 것이다. 받은 줄은 전부 남이 정한 값이다(서버가 보낸
/// 것이라도 그 서버에 남이 붙어 있다). 한쪽이 더 헐겁게 받아주면 거기서만 이상한
/// 값이 들어와 배가 엉뚱한 자리로 가거나 체력이 음수가 된다.
///
/// 그래서 **표에 없는 종류는 버리고**, 숫자는 범위를 보고, 글자는 길이와 제어문자를
/// 본다. 받아줄 것과 버릴 것이 파이썬과 같은지는 `test/battle_protocol_test.dart`가
/// 답안지(`tests/dump_battle_protocol_cases.py`)와 대조한다.
///
/// ## 남의 배는 못 움직인다
/// 내 조작(`in`)과 내 피격(`hit`/`dead`)에는 **자리 번호를 안 적는다.** 중계 서버가
/// '어느 연결로 왔는가'를 보고 붙인다. 적어 보낼 수 있게 두면 남의 배를 움직이거나
/// 남이 죽었다고 대신 신고할 수 있다.
library;

import 'dart:convert';
import 'dart:math';

const int maxLineBytes = 512;
const int maxHumans = 6;
const int maxBots = 6;
const int maxPlayers = maxHumans + maxBots;
const int minPlayers = 2;
const int maxNickLen = 24;
const int colorCount = 21;
const int rainbowColor = colorCount - 1;
const int maxTick = 2000000;

/// 체력 상한 - **계산에 쓰는 값이 아니라 받아줄 수 있는 최대치**다.
/// battle_sim 의 maxHp(500)보다 넉넉하게 둔 쪽이 파이썬과 같다
const int maxHpWire = 5000;

const int keyMask = 1 | 2 | 4 | 8 | 16;

const String ctcpDelim = '\x01';
const String battleTag = 'CHUPBATTLE';

/// 줄의 종류. 표에 없는 것은 버린다
const String tJoin = 'join';
const String tWelcome = 'welcome';
const String tDeny = 'deny';
const String tJoined = 'joined';
const String tLeft = 'left';
const String tStart = 'start';
const String tStarted = 'started';
const String tInput = 'in';
const String tPeerInput = 'peer';
const String tBotInput = 'botin';
const String tBotHit = 'bothit';
const String tBotDead = 'botdead';
const String tHit = 'hit';
const String tPeerHit = 'peerhit';
const String tDead = 'dead';
const String tPeerDead = 'peerdead';
const String tBye = 'bye';

final RegExp _roomOk = RegExp(r'^[0-9a-f]{8,64}$');
final RegExp _controlChars = RegExp(r'[\x00-\x1f\x7f]');
final RegExp _roomNotice =
    RegExp(r'^CHUPBATTLE\s+ROOM\s+([0-9a-f]{8,64})$', caseSensitive: false);

/// 연습 상대(AI) 자리인가. 뒤쪽 자리가 AI 다
bool isBotSlot(int slot) => slot >= maxHumans;

/// 이 판에만 쓰는 방 번호(난수 24자). **이걸 모르면 방에 못 들어온다** -
/// 주소는 모두가 알지만 번호를 모르면 아무나 끼어들 수 없다.
String newRoom() {
  final random = Random.secure();
  final buffer = StringBuffer();
  for (var i = 0; i < 12; i++) {
    buffer.write(random.nextInt(256).toRadixString(16).padLeft(2, '0'));
  }
  return buffer.toString();
}

bool isRoomId(Object? value) =>
    value is String && _roomOk.hasMatch(value.toLowerCase());

/// 상대가 보낸 이름은 화면에 그리기만 한다 - 제어문자를 걷어내고 길이를 자른다.
///
/// IRC 색·굵게 제어문자가 그대로 들어오면 화면이 깨지고(실제로 겪었다), 긴 이름은
/// 전투 화면을 밀어낸다.
String safeNick(Object? nick) {
  final text = nick is String ? nick : '';
  final cleaned = text.replaceAll(_controlChars, '').trim();
  if (cleaned.isEmpty) return '손님';
  return cleaned.length <= maxNickLen ? cleaned : cleaned.substring(0, maxNickLen);
}

/// "이 방으로 와라" - 채널에 올리는 한 줄. **주소는 담기지 않는다**
String formatRoomNotice(String room) => '$ctcpDelim$battleTag ROOM $room$ctcpDelim';

/// 채널에서 받은 한 줄에서 방 번호를 꺼낸다. 우리 것이 아니면 빈 글자.
String parseRoomNotice(String text) {
  if (text.isEmpty || !text.startsWith(ctcpDelim) || !text.endsWith(ctcpDelim)) {
    return '';
  }
  final inner = text.substring(1, text.length - 1).trim();
  final match = _roomNotice.firstMatch(inner);
  return match == null ? '' : match.group(1)!.toLowerCase();
}

bool isBattleNotice(String text) =>
    text.isNotEmpty && text.startsWith('$ctcpDelim$battleTag ');

/// 정수이고 범위 안이면 그 값, 아니면 null.
///
/// **참/거짓과 소수는 받지 않는다.** 파이썬에서 True 는 정수 1로 통과해버려서
/// 거기서 따로 막는데, 받는 쪽이 한쪽만 헐거우면 그 틈으로만 이상한 값이 들어온다.
int? asInt(Object? value, int low, int high) {
  if (value is! int) return null;      // bool·double 은 여기서 걸린다
  return (low <= value && value <= high) ? value : null;
}

/// 한 줄로 만든다. 상한을 넘으면 빈 글자(보내는 쪽에서 막는다).
String encode(Map<String, Object?> message) {
  final line = jsonEncode(message);
  // 줄바꿈 한 글자까지 세서 상한을 본다(파이썬과 같다)
  if (utf8.encode(line).length + 1 > maxLineBytes) return '';
  return line;
}

/// 받은 한 줄을 해석하고 **전부 검사한다.** 조금이라도 이상하면 null.
Map<String, Object?>? decode(String line) {
  if (line.isEmpty || utf8.encode(line).length > maxLineBytes) return null;
  Object? parsed;
  try {
    parsed = jsonDecode(line);
  } on Object {
    return null;
  }
  if (parsed is! Map) return null;
  final message = parsed.map((k, v) => MapEntry('$k', v));
  final checker = _checkers[message['t']];
  return checker == null ? null : checker(message);
}

typedef _Checker = Map<String, Object?>? Function(Map<String, Object?>);

Map<String, Object?>? _player(Object? raw) {
  if (raw is! Map) return null;
  final entry = raw.map((k, v) => MapEntry('$k', v));
  final slot = asInt(entry['slot'], 0, maxPlayers - 1);
  final color = asInt(entry['color'], 0, colorCount - 1);
  if (slot == null) return null;
  return {'slot': slot, 'nick': safeNick(entry['nick']), 'color': color ?? 0};
}

Map<String, Object?>? _checkWelcome(Map<String, Object?> m) {
  final slot = asInt(m['slot'], 0, maxPlayers - 1);
  final tick = asInt(m['tick'], 0, maxTick);
  final cap = asInt(m['cap'], minPlayers, maxHumans);
  final color = asInt(m['color'], 0, colorCount - 1);
  final players = m['players'];
  if (slot == null || tick == null || cap == null || color == null) return null;
  if (players is! List || players.length > maxPlayers) return null;
  final cleaned = <Map<String, Object?>>[];
  for (final entry in players) {
    final one = _player(entry);
    if (one == null) return null;
    cleaned.add(one);
  }
  final bots = asInt(m['bots'], 0, maxBots);
  return {
    't': tWelcome,
    'slot': slot,
    'tick': tick,
    'cap': cap,
    'color': color,
    'players': cleaned,
    'bots': bots ?? 0,
    'started': m['started'] == true,
  };
}

Map<String, Object?>? _checkDeny(Map<String, Object?> m) {
  final why = m['why'];
  return {'t': tDeny, 'why': why is String ? safeNick(why) : '들어갈 수 없습니다'};
}

Map<String, Object?>? _checkJoined(Map<String, Object?> m) {
  final entry = _player(m);
  return entry == null ? null : {'t': tJoined, ...entry};
}

Map<String, Object?>? _checkLeft(Map<String, Object?> m) {
  final slot = asInt(m['slot'], 0, maxPlayers - 1);
  return slot == null ? null : {'t': tLeft, 'slot': slot};
}

Map<String, Object?>? _checkInput(Map<String, Object?> m) {
  final tick = asInt(m['tick'], 0, maxTick);
  final keys = asInt(m['keys'], 0, keyMask);
  if (tick == null || keys == null) return null;
  // 자리 번호는 **일부러 안 받는다** - 중계 서버가 어느 연결로 왔는지로 정한다
  return {'t': tInput, 'tick': tick, 'keys': keys};
}

Map<String, Object?>? _checkPeerInput(Map<String, Object?> m) {
  final slot = asInt(m['slot'], 0, maxPlayers - 1);
  final tick = asInt(m['tick'], 0, maxTick);
  final keys = asInt(m['keys'], 0, keyMask);
  if (slot == null || tick == null || keys == null) return null;
  return {'t': tPeerInput, 'slot': slot, 'tick': tick, 'keys': keys};
}

_Checker _ownReport(String kind) => (m) {
      final by = asInt(m['by'], 0, maxPlayers - 1);
      final hp = asInt(m['hp'], 0, maxHpWire);
      if (by == null || hp == null) return null;
      return {'t': kind, 'by': by, 'hp': hp};
    };

_Checker _relayedReport(String kind) => (m) {
      final slot = asInt(m['slot'], 0, maxPlayers - 1);
      final by = asInt(m['by'], 0, maxPlayers - 1);
      final hp = asInt(m['hp'], 0, maxHpWire);
      if (slot == null || by == null || hp == null) return null;
      return {'t': kind, 'slot': slot, 'by': by, 'hp': hp};
    };

_Checker _botReport(String kind, {required bool withKeys}) => (m) {
      final slot = asInt(m['slot'], 0, maxPlayers - 1);
      if (slot == null || !isBotSlot(slot)) return null;
      if (withKeys) {
        final tick = asInt(m['tick'], 0, maxTick);
        final keys = asInt(m['keys'], 0, keyMask);
        if (tick == null || keys == null) return null;
        return {'t': kind, 'slot': slot, 'tick': tick, 'keys': keys};
      }
      final by = asInt(m['by'], 0, maxPlayers - 1);
      final hp = asInt(m['hp'], 0, maxHpWire);
      if (by == null || hp == null) return null;
      return {'t': kind, 'slot': slot, 'by': by, 'hp': hp};
    };

Map<String, Object?>? _checkJoin(Map<String, Object?> m) {
  final room = m['room'];
  if (!isRoomId(room)) return null;
  final color = asInt(m['color'], 0, colorCount - 1);
  final cap = asInt(m['cap'], minPlayers, maxHumans);
  final bots = asInt(m['bots'], 0, maxBots);
  return {
    't': tJoin,
    'room': (room as String).toLowerCase(),
    'nick': safeNick(m['nick']),
    'color': color ?? 0,
    'cap': cap ?? maxHumans,
    'bots': bots ?? 0,
  };
}

final Map<Object?, _Checker> _checkers = {
  tJoin: _checkJoin,
  tWelcome: _checkWelcome,
  tDeny: _checkDeny,
  tJoined: _checkJoined,
  tLeft: _checkLeft,
  tStart: (_) => {'t': tStart},
  tStarted: (_) => {'t': tStarted},
  tInput: _checkInput,
  tPeerInput: _checkPeerInput,
  tBotInput: _botReport(tBotInput, withKeys: true),
  tBotHit: _botReport(tBotHit, withKeys: false),
  tBotDead: _botReport(tBotDead, withKeys: false),
  tHit: _ownReport(tHit),
  tPeerHit: _relayedReport(tPeerHit),
  tDead: _ownReport(tDead),
  tPeerDead: _relayedReport(tPeerDead),
  tBye: (_) => {'t': tBye},
};

// ---------------------------------------------------------------- 보낼 줄 만들기
/// 방에 들어가겠다. 정원과 연습 상대 수는 **방을 처음 연 사람만** 정할 수 있다
Map<String, Object?> joinMessage(String room, String nick,
        {int color = 0, int cap = maxHumans, int bots = 0}) =>
    {'t': tJoin, 'room': room, 'nick': nick, 'color': color, 'cap': cap, 'bots': bots};

Map<String, Object?> startMessage() => {'t': tStart};

/// 이 틱에 내가 누른 키. 자리 번호는 안 적는다(서버가 붙인다)
Map<String, Object?> inputMessage(int tick, int keys) =>
    {'t': tInput, 'tick': tick, 'keys': keys};

/// 내가 맞았다 - **남은 체력을 같이 보낸다.**
///
/// 처음에는 "맞았다"만 보냈더니 받는 쪽이 얼마나 깎을지 몰라 최대치를 깎았다.
/// 기를 모은 정도에 따라 70~260으로 달라지므로, 약하게 두 대 맞은 배가 남의 화면에서만
/// 죽어 **보이지도 맞지도 않는 유령**이 됐다. 남은 체력을 실어 보내면 받는 쪽은 그
/// 값으로 맞추기만 하면 되고, 한 줄을 놓쳐도 다음 보고에서 저절로 맞는다.
Map<String, Object?> hitMessage(int by, int hp) => {'t': tHit, 'by': by, 'hp': hp};

Map<String, Object?> deadMessage(int by, int hp) => {'t': tDead, 'by': by, 'hp': hp};

Map<String, Object?> byeMessage() => {'t': tBye};
