/// 중계 서버에 말 걸기 - 프로필·놓친 대화·파일·이모티콘.
///
/// 이 넷은 PC 앱이 이미 서버 창구로 빼놓은 것들이라, 모바일은 **부르기만** 하면 된다.
/// 자리 이름 계산은 `core/relay.dart`가 하고(PC와 답을 맞춰뒀다) 여기는 통신만 한다.
///
/// ## 한도는 서버에서 받아온다
/// `/files`, `/logs`, `/profiles`는 자기 한도(`limits`)를 알려준다. 숫자를 코드에 박으면
/// 서버가 바뀔 때 조용히 어긋나므로, 못 받아왔을 때 쓸 **기본값**만 두고 받아오면 그 값을 쓴다.
///
/// ## 안 되면 조용히 넘어간다
/// 중계 서버는 있으면 좋은 것이지 없으면 안 되는 것이 아니다. 실패해도 채팅은 그대로
/// 돌아가야 한다 - 서버가 잠깐 닫혔다고 채팅창이 경고로 덮이면 안 된다.
library;

import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;

import '../core/client_badge.dart';
import '../core/relay.dart' as relay;

const Duration _timeout = Duration(seconds: 15);

/// 올릴 수 있는 파일 크기의 기본값(서버가 알려주기 전까지).
const int fallbackMaxBytes = 1024 * 1024 * 1024;

/// 서버가 한 번에 받아주는 줄 수·사람 수. 받아온 값으로 바뀐다.
const int fallbackPostLines = 200;
const int fallbackLookup = 60;

/// 서버가 같은 줄로 보는 시간 차이(PC의 `SAME_LINE_SECONDS`와 같은 값).
const double sameLineSeconds = 5.0;

Map<String, dynamic>? _json(http.Response response) {
  if (response.statusCode != 200) return null;
  try {
    final body = jsonDecode(utf8.decode(response.bodyBytes));
    return body is Map<String, dynamic> ? body : null;
  } on Object {
    return null;
  }
}

/// ---------------------------------------------------------------- 프로필
class ProfileApi {
  ProfileApi(this.protocol, this.host, this.port);

  final String protocol;
  final String host;
  final int port;

  /// 이미 물어본 사람 - 다시 안 묻는다(PC가 CTCP를 아껴 묻는 것과 같은 이유).
  final Set<String> _asked = {};

  /// 내 프로필을 올린다. 처음이면 서버가 주는 표를 돌려준다(다음에 고칠 때 쓴다).
  ///
  /// 표가 없으면 서버가 안 고쳐준다 - 그래야 **남이 내 얼굴을 못 바꾼다.** 계정이 없는
  /// 서버라 채팅 통로로 주고받을 때 IRC 서버가 해주던 보호가 사라지기 때문이다.
  ///
  /// [avatar]나 [client]를 **안 주면 그 칸은 건드리지 않는다.** 모바일은 아이콘
  /// 편집기가 없어서 "나는 춥채팅 모바일"만 올리는데, 빈 아이콘을 같이 보내면 그
  /// 사람이 PC에서 정해둔 얼굴이 서버에서 지워진다(같은 닉네임이면 같은 자리다).
  Future<String?> publish(String nick,
      {String? avatar, ClientInfo? client, String token = ''}) async {
    if (nick.isEmpty) return null;
    final who = relay.whoId(protocol, host, port, nick);
    try {
      final response = await http
          .put(
            Uri.parse('${relay.profilesUrl}/$who'),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({
              'nick': nick,
              'token': token,
              // 값이 없으면 그 칸 자체를 안 보낸다(? 표시). 안 보낸 칸은 서버가
              // 그대로 둔다(features/profiles.py) - 빈 값으로 덮어쓰면 안 된다
              'avatar': ?avatar,
              'client': ?client?.toJson(),
            }),
          )
          .timeout(_timeout);
      return _json(response)?['token'] as String?;
    } on Object {
      return null;
    }
  }

  /// 이 사람들 얼굴을 받아온다. 이미 물어본 사람은 알아서 건너뛴다.
  Future<Map<String, Who>> lookup(Iterable<String> nicks) async {
    final fresh = nicks.where((n) => n.isNotEmpty && !_asked.contains(n)).toList();
    if (fresh.isEmpty) return const {};
    final batch = fresh.take(fallbackLookup).toList();
    _asked.addAll(batch);

    final byId = {
      for (final nick in batch) relay.whoId(protocol, host, port, nick): nick
    };
    try {
      final response = await http
          .post(
            Uri.parse('${relay.profilesUrl}/lookup'),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({'who': byId.keys.toList()}),
          )
          .timeout(_timeout);
      final found = _json(response)?['profiles'];
      if (found is! Map) return const {};
      final out = <String, Who>{};
      found.forEach((who, profile) {
        final nick = byId[who];
        if (nick == null || profile is! Map) return;
        final avatar = profile['avatar'];
        out[nick] = Who(
          avatar: avatar is String ? avatar : '',
          client: ClientInfo.fromJson(profile['client']),
        );
      });
      return out;
    } on Object {
      return const {};
    }
  }

  /// 그 사람을 다시 물어보게 한다(프로필이 바뀐 걸 알았을 때).
  void forget(String nick) => _asked.remove(nick);
}

/// 서버가 아는 그 사람 - 얼굴과 쓰는 프로그램.
///
/// 둘을 같이 돌려주는 이유: 어차피 같은 조회 한 번에 온다. 따로 물으면 참여자 수만큼
/// 요청이 두 배가 된다.
class Who {
  const Who({this.avatar = '', this.client = const ClientInfo()});

  final String avatar;
  final ClientInfo client;
}

/// ------------------------------------------------------------ 놓친 대화
class ChatLogApi {
  ChatLogApi(this.protocol, this.host, this.port);

  final String protocol;
  final String host;
  final int port;

  final Map<String, List<Map<String, Object?>>> _queued = {};
  final Map<String, List<Map<String, Object?>>> _recent = {};

  /// 받아본 줄을 올릴 목록에 넣는다.
  ///
  /// 내가 보낸 것도 넣는다 - 빠지면 남이 받아갈 기록에 구멍이 생긴다("쟤 혼자
  /// 떠들었네"처럼 보인다).
  void record(String channel, String sender, String text, double ts) {
    if (channel.isEmpty || sender.isEmpty || text.isEmpty) return;
    _queued.putIfAbsent(channel, () => []).add({
      'ts': ts,
      'sender': sender,
      'text': text,
      'seq': _seqFor(channel, sender, text, ts),
    });
  }

  /// 창 안에서 몇 번째로 본 같은 말인가.
  ///
  /// 서버가 짧은 시간 안의 같은 말을 한 줄로 보기 때문에 필요하다(사람마다 받은 시각이
  /// 다르므로 시각으로는 못 가른다). "ㅋㅋ"를 두 번 치면 한 줄로 뭉치는 것을 막는다.
  int _seqFor(String channel, String sender, String text, double ts) {
    final recent = _recent.putIfAbsent(channel, () => []);
    recent.removeWhere((line) => (line['ts'] as double) < ts - sameLineSeconds);
    final seq = recent
        .where((line) => line['sender'] == sender && line['text'] == text)
        .length;
    recent.add({'ts': ts, 'sender': sender, 'text': text});
    return seq > 99 ? 99 : seq;
  }

  /// 모아둔 것을 보낸다. 실패해도 아무 말 안 한다(사람이 할 수 있는 일이 없다).
  Future<void> flush() async {
    for (final entry in _queued.entries.toList()) {
      final lines = entry.value;
      if (lines.isEmpty) continue;
      final batch = lines.take(fallbackPostLines).toList();
      lines.removeRange(0, batch.length);
      final room = relay.roomId(protocol, host, port, entry.key);
      try {
        await http
            .post(
              Uri.parse('${relay.logsUrl}/$room'),
              headers: {'Content-Type': 'application/json'},
              body: jsonEncode({'lines': batch}),
            )
            .timeout(_timeout);
      } on Object {
        // 못 올렸다. 다시 넣으면 끝없이 쌓이므로 그냥 흘려보낸다
      }
    }
  }

  /// 마지막으로 본 시각 뒤에 오간 이야기를 받아온다.
  Future<List<Map<String, Object?>>> missed(String channel, double since) async {
    final room = relay.roomId(protocol, host, port, channel);
    try {
      final response = await http
          .get(Uri.parse('${relay.logsUrl}/$room?since=${since.toStringAsFixed(3)}'))
          .timeout(_timeout);
      final lines = _json(response)?['lines'];
      if (lines is! List) return const [];
      final out = lines
          .whereType<Map<String, dynamic>>()
          .where((line) => (line['text'] as String?)?.isNotEmpty ?? false)
          .toList();
      out.sort((a, b) =>
          ((a['ts'] as num?) ?? 0).compareTo((b['ts'] as num?) ?? 0));
      return out;
    } on Object {
      return const [];
    }
  }
}

/// --------------------------------------------------------------- 파일·사진
class UploadResult {
  const UploadResult({required this.url, required this.note, this.id = '', this.token = ''});

  final String url;
  final String note;
  final String id;

  /// 올린 사람만 내릴 수 있는 표.
  final String token;

  bool get ok => url.isNotEmpty;
}

class FileApi {
  FileApi({this.group = ''});

  /// 이모티콘을 같이 쓰는 무리. 비어 있으면 올려도 목록에 안 뜬다(나만 쓴다).
  String group;

  int maxBytes = fallbackMaxBytes;

  /// 서버가 정한 한도를 받아온다(실패해도 기본값으로 동작한다).
  Future<void> refreshLimits() async {
    try {
      final response =
          await http.get(Uri.parse(relay.filesUrl)).timeout(_timeout);
      final limits = _json(response)?['limits'];
      if (limits is Map && limits['file_bytes'] is num) {
        maxBytes = (limits['file_bytes'] as num).toInt();
      }
    } on Object {
      // 못 받아왔으면 기본값 그대로
    }
  }

  /// 파일 하나를 올린다. [kind]가 `emoji`면 서버가 이모티콘 크기로 줄여 보관한다.
  Future<UploadResult> upload(File file, {String kind = 'file'}) async {
    final int size;
    try {
      size = await file.length();
    } on Object catch (error) {
      return UploadResult(url: '', note: '파일을 읽을 수 없습니다: $error');
    }
    if (size == 0) return const UploadResult(url: '', note: '빈 파일은 올릴 수 없습니다.');
    if (kind == 'file' && size > maxBytes) {
      return UploadResult(
          url: '', note: '파일이 너무 큽니다(${readable(size)}). '
              '${readable(maxBytes)}까지 올릴 수 있습니다.');
    }

    final name = file.uri.pathSegments.last;
    final headers = <String, String>{
      'Content-Type': 'application/octet-stream',
      // **이름은 부호화해서 싣는다.** HTTP 헤더는 ASCII만 실을 수 있어서 한글 이름을
      // 그대로 넣으면 아예 안 올라간다
      'X-File-Name': Uri.encodeComponent(name),
      'X-File-Kind': kind,
    };
    if (kind == 'emoji' && group.isNotEmpty) {
      // 이모티콘은 같이 쓰는 것이다 - 무리를 알려주면 그 서버 사람들 목록에 같이 오른다
      headers['X-Emoji-Group'] = group;
    }

    try {
      final response = await http
          .post(Uri.parse(relay.filesUrl),
              headers: headers, body: await file.readAsBytes())
          .timeout(const Duration(minutes: 10));
      final answer = _json(response);
      if (answer == null) {
        // 서버가 왜 거절했는지 그대로 보여준다 - "실패했습니다"만 뜨면 무엇을 고쳐야
        // 할지 알 수 없다
        String reason = '올리지 못했습니다. 잠시 뒤 다시 시도해 주세요.';
        try {
          final body = jsonDecode(utf8.decode(response.bodyBytes));
          if (body is Map && body['error'] is String) reason = body['error'] as String;
        } on Object {
          // 본문도 못 읽으면 기본 안내
        }
        return UploadResult(url: '', note: reason);
      }
      final path = answer['url'] as String? ?? '';
      if (path.isEmpty) {
        return const UploadResult(url: '', note: '서버가 주소를 돌려주지 않았습니다.');
      }
      return UploadResult(
        url: relay.server + path,
        note: '${answer['name'] ?? '파일'} 올렸습니다.',
        id: answer['id'] as String? ?? '',
        token: answer['token'] as String? ?? '',
      );
    } on Object catch (error) {
      return UploadResult(url: '', note: '올리지 못했습니다: $error');
    }
  }

  /// 그 파일이 아직 있는지, 언제까지 받을 수 있는지.
  Future<Map<String, dynamic>?> meta(String fileId) async {
    try {
      final response =
          await http.get(Uri.parse(relay.metaUrl(fileId))).timeout(_timeout);
      final info = _json(response);
      if (info == null || info['name'] == null) return null;
      return info;
    } on Object {
      return null;
    }
  }

  /// 다 같이 쓰는 이모티콘 목록.
  Future<List<Map<String, String>>> sharedEmoji() async {
    if (group.isEmpty) return const [];
    try {
      final response = await http
          .get(Uri.parse('${relay.filesUrl}/emoji?group=$group&limit=300'))
          .timeout(_timeout);
      final list = _json(response)?['emoji'];
      if (list is! List) return const [];
      return list
          .whereType<Map<String, dynamic>>()
          .where((e) => e['url'] is String)
          .map((e) => {
                'url': relay.server + (e['url'] as String),
                'name': _short(e['name'] as String? ?? ''),
              })
          .toList();
    } on Object {
      return const [];
    }
  }
}

/// 보여줄 이름. 확장자는 떼어낸다(칸이 좁아서 이름이 잘린다).
String _short(String name) {
  for (final suffix in const ['.png', '.gif', '.jpg', '.jpeg', '.webp']) {
    if (name.toLowerCase().endsWith(suffix)) {
      return name.substring(0, name.length - suffix.length);
    }
  }
  return name;
}

/// 사람이 읽는 크기. 바이트 숫자를 그대로 보여주면 감이 안 온다.
String readable(int size) {
  const units = [('GB', 1024 * 1024 * 1024), ('MB', 1024 * 1024), ('KB', 1024)];
  for (final (name, step) in units) {
    if (size >= step) return '${(size / step).toStringAsFixed(1)}$name';
  }
  return '${size}B';
}

/// 언제까지 받을 수 있는지를 사람 말로.
///
/// 남은 시각을 그대로 보여주면 얼마나 급한지 감이 안 온다.
/// '3시간 뒤 사라짐'이면 지금 받아야 하는지 바로 안다.
String remainingText(double expires, {DateTime? now}) {
  if (expires == 0) return '';   // 이모티콘처럼 기한이 없는 것
  final at = (now ?? DateTime.now()).millisecondsSinceEpoch / 1000;
  final left = expires - at;
  if (left <= 0) return '기간이 지나 사라졌습니다';
  if (left < 3600) return '${(left ~/ 60).clamp(1, 59)}분 뒤 사라짐';
  if (left < 86400) return '${left ~/ 3600}시간 뒤 사라짐';
  return '${left ~/ 86400}일 뒤 사라짐';
}
