/// IRC 한 줄을 뜯고 만드는 규칙 - 순수 함수만. 소켓도 화면도 모른다.
///
/// PC 앱의 `irc_protocol.py`를 **명세서로 읽고 옮긴 것**이다. 양쪽이 같은 서버에 붙어
/// 같은 사람들과 이야기하므로, 한쪽만 다르게 해석하면 그 사람에게만 글자가 깨져 보인다.
/// 그래서 `test/irc_protocol_test.dart`가 파이썬이 내놓은 답과 하나하나 대조한다.
///
/// 옮기지 않은 것: 아이콘 CTCP 조각내기. 아이콘은 이제 서버(`/profiles`)에 있으므로
/// 모바일은 512바이트 쪼개기를 만들 필요가 없다.
library;

import 'dart:convert';

const String rplWelcome = '001';
const String errErroneusNickname = '432';
const String errNicknameInUse = '433';
const String errNickCollision = '436';
const String rplNamReply = '353';
const String rplEndOfNames = '366';

const Set<String> nickCollisionNumerics = {
  errErroneusNickname,
  errNicknameInUse,
  errNickCollision,
};

const Set<String> channelJoinErrorNumerics = {
  '403', '405', '471', '473', '474', '475',
};

const int maxNickRetries = 3;

/// 우리끼리 쓰는 숨김 프레임의 경계 문자. 아이콘·프로그램 확인이 이걸로 오간다.
const String ctcpDelim = '\x01';

/// IRC 한 줄은 CR-LF 포함 512바이트를 못 넘는다(RFC 1459). 서버가 붙이는 프리픽스
/// 길이를 우리가 모르므로 보수적으로 잡은 값 - PC 앱과 **같은 숫자여야** 한다.
/// 다르면 같은 글이 한쪽에서만 잘린다.
const int maxMessageBytes = 380;

/// IRC 메시지 한 줄.
class IrcMessage {
  const IrcMessage({
    required this.prefix,
    required this.command,
    required this.params,
    required this.raw,
  });

  final String? prefix;
  final String command;
  final List<String> params;
  final String raw;

  /// 보낸 사람의 닉네임. 프리픽스는 `nick!user@host` 모양이다.
  String get sourceNick {
    final p = prefix;
    if (p == null || p.isEmpty) return '';
    final bang = p.indexOf('!');
    return bang >= 0 ? p.substring(0, bang) : p;
  }

  /// 마지막 칸(보통 사람이 쓴 글).
  String get trailing => params.isEmpty ? '' : params.last;

  @override
  String toString() => 'IrcMessage($command, $params)';
}

/// 받은 한 줄을 뜯는다.
IrcMessage parseLine(String line) {
  final raw = line;
  var rest = line.replaceAll(RegExp(r'[\r\n]+$'), '');
  rest = rest.replaceAll(RegExp(r'^[\r\n]+'), '');

  // IRCv3 메시지 태그(@key=value;...)는 협상하지 않으므로 건너뛴다
  if (rest.startsWith('@')) {
    final space = rest.indexOf(' ');
    rest = space < 0 ? '' : rest.substring(space + 1);
  }

  String? prefix;
  if (rest.startsWith(':')) {
    final space = rest.indexOf(' ');
    if (space < 0) {
      prefix = rest.substring(1);
      rest = '';
    } else {
      prefix = rest.substring(1, space);
      rest = rest.substring(space + 1);
    }
  }

  List<String> params;
  final mark = rest.indexOf(' :');
  if (mark >= 0) {
    final head = rest.substring(0, mark);
    final trailing = rest.substring(mark + 2);
    params = [..._words(head), trailing];
  } else if (rest.startsWith(':')) {
    params = [rest.substring(1)];
  } else {
    params = _words(rest);
  }

  final command = params.isEmpty ? '' : params.first;
  return IrcMessage(
    prefix: prefix,
    command: command,
    params: params.isEmpty ? const [] : params.sublist(1),
    raw: raw,
  );
}

/// 파이썬 `str.split()`과 같게 - 빈 칸은 버리고 연속 공백도 하나로 본다.
List<String> _words(String text) =>
    text.split(RegExp(r'\s+')).where((w) => w.isNotEmpty).toList();

/// 보낼 한 줄을 바이트로. IRC는 줄 끝이 CR-LF다.
List<int> encodeLine(String text) => utf8.encode('$text\r\n');

String formatPass(String password) => 'PASS $password';

String formatNick(String nick) => 'NICK $nick';

String formatUser(String username, String realname) =>
    'USER $username 0 * :$realname';

String formatJoin(String channel, [String? key]) =>
    (key == null || key.isEmpty) ? 'JOIN $channel' : 'JOIN $channel $key';

String formatPrivmsg(String target, String text) => 'PRIVMSG $target :$text';

String formatNotice(String target, String text) => 'NOTICE $target :$text';

String formatPart(String channel, [String? reason]) =>
    (reason == null || reason.isEmpty) ? 'PART $channel' : 'PART $channel :$reason';

String formatQuit([String? reason]) =>
    (reason == null || reason.isEmpty) ? 'QUIT' : 'QUIT :$reason';

String formatPong(String token) => 'PONG :$token';

String formatPing(String token) => 'PING :$token';

String formatNames(String channel) => 'NAMES $channel';

/// 긴 글을 IRC 한 줄에 들어갈 크기로 나눈다.
///
/// - **글자 중간을 자르지 않는다.** 한글은 한 글자가 3바이트라 바이트로 자르면 깨진다
/// - 가능하면 띄어쓰기에서 자른다(단어가 두 줄로 쪼개지면 읽기 나쁘다)
/// - 띄어쓰기가 없으면(한글은 흔하다) 들어가는 만큼 자른다
List<String> splitMessage(String text, {int limit = maxMessageBytes}) {
  if (text.isEmpty) return const [];
  final pieces = <String>[];
  var rest = text;
  while (rest.isNotEmpty) {
    if (_bytes(rest) <= limit) {
      pieces.add(rest);
      break;
    }
    // 들어갈 수 있는 **글자 수**를 찾는다(바이트 수가 아니다)
    var cut = rest.length;
    while (_bytes(_take(rest, cut)) > limit) {
      cut = (cut * limit / _bytes(_take(rest, cut))).floor();
      if (cut < 1) cut = 1;
      while (cut < rest.length && _bytes(_take(rest, cut + 1)) <= limit) {
        cut += 1;
      }
    }
    final space = rest.substring(0, cut + 1 > rest.length ? rest.length : cut + 1)
        .lastIndexOf(' ', cut);
    if (space > 0 && space > cut ~/ 2) {
      cut = space;
    }
    pieces.add(_take(rest, cut).replaceAll(RegExp(r'\s+$'), ''));
    rest = rest.substring(cut).replaceAll(RegExp(r'^\s+'), '');
  }
  return pieces.where((p) => p.isNotEmpty).toList();
}

int _bytes(String text) => utf8.encode(text).length;

String _take(String text, int count) =>
    text.substring(0, count > text.length ? text.length : count);

/// `353 NAMES` 응답에서 사람 이름만 뽑는다. 앞에 붙는 권한 기호(@ + 등)는 뗀다.
List<String> parseNamesReply(IrcMessage msg) {
  final names = msg.trailing.split(RegExp(r'\s+')).where((n) => n.isNotEmpty);
  return names
      .map((n) => n.replaceAll(RegExp(r'^[~&@%+]+'), ''))
      .where((n) => n.isNotEmpty)
      .toList();
}

/// 사람이 친 이름을 채널 이름으로. `#`을 안 붙여도 붙여준다.
String normalizeChannel(String name) {
  var trimmed = name.trim();
  if (trimmed.isNotEmpty && !'#&+!'.contains(trimmed[0])) {
    trimmed = '#$trimmed';
  }
  return trimmed;
}

/// 우리끼리 쓰는 숨김 프레임인가.
///
/// **잘려서 해석에 실패해도 채팅으로 새면 안 된다.** 그래서 '완성된 프레임인가'가
/// 아니라 '프레임처럼 생겼는가'로 판단한다. PC 앱에서 잘린 base64 483자가 채팅에
/// 그대로 쏟아진 적이 있다.
bool isCtcpFrame(String text) => text.startsWith(ctcpDelim);

/// 이 이름으로 접속할 수 있는가. 안 되면 이유를 돌려준다(되면 빈 값).
///
/// **IRC 닉네임에는 한글을 못 쓴다.** RFC가 영문·숫자·몇몇 기호만 허용하고, 실제
/// 서버(UnrealIRCd)도 거절한다. 그냥 보내면 서버가 432로 막는데, 앱은 그걸 "이름이
/// 사용 중"으로 보고 `_`를 붙여 다시 시도하다가 몇 번 만에 조용히 포기한다 -
/// 사람 눈에는 "들어가기를 눌렀는데 아무 일도 안 일어남"으로만 보인다.
String nickProblem(String nick) {
  if (nick.isEmpty) return '쓸 이름을 적어주세요.';
  if (nick.length > 30) return '이름이 너무 깁니다.';
  if (RegExp(r'^[0-9]').hasMatch(nick)) return '이름은 숫자로 시작할 수 없습니다.';
  if (!RegExp(r'^[A-Za-z0-9\[\]\`_^{|}-]+$').hasMatch(nick)) {
    return '이름에는 영문·숫자만 쓸 수 있습니다(한글은 안 됩니다).';
  }
  return '';
}
