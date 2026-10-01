/// 백그라운드에서 들어온 말을 알림으로 띄우는 일.
///
/// ## 알림은 **한 자리**뿐이다
/// 말이 오는 대로 쌓으면 수다 한 번에 알림이 수십 개가 된다. 사람이 보고 싶은 건
/// "새 말이 왔다"와 "마지막이 뭐였나"뿐이다. 그래서 알림 번호를 하나로 고정해서
/// 새 말이 오면 그 자리를 **갈아치운다**(안드로이드는 같은 번호면 덮어쓴다).
///
/// ## 판단은 순수 함수로 떼어둔다
/// "띄울까 말까"와 "무슨 글자를 보일까"는 플러그인 없이 시험할 수 있어야 한다.
/// 알림은 눈으로 확인하기가 번거로워서, 조건이 틀리면 조용히 안 뜨거나 내 말에도
/// 뜨는 식으로 오래 묻힌다.
library;

import 'package:flutter/foundation.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';

import '../core/emoji.dart';
import '../core/relay.dart' as relay;

/// 알림 자리 번호. **바꾸지 말 것** - 같은 번호라서 최신 하나만 보인다
const int notificationId = 1;

/// 안드로이드 알림 통로. 사람이 설정에서 소리/중요도를 따로 만질 수 있는 단위다
const String channelId = 'chupchat_messages';
const String channelName = '채팅 알림';

/// 미리보기에 보일 글자 수 상한. 알림 줄은 어차피 잘리고, 길면 가려야 할 내용이
/// 잠금화면에 그만큼 더 드러난다
const int previewLimit = 80;

/// 사진으로 볼 확장자. 그 외는 전부 파일로 본다
const Set<String> imageKinds = {
  'png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'heic', 'heif',
};

/// 알림에 보일 제목과 내용.
@immutable
class NotificationText {
  const NotificationText(this.title, this.body);

  final String title;
  final String body;

  @override
  bool operator ==(Object other) =>
      other is NotificationText && other.title == title && other.body == body;

  @override
  int get hashCode => Object.hash(title, body);

  @override
  String toString() => 'NotificationText($title / $body)';
}

/// 이 줄을 알림으로 띄워야 하는가.
///
/// - 내 말에는 안 띄운다(내가 방금 친 것이다)
/// - 입장/퇴장 같은 안내에는 안 띄운다. 사람이 드나들 때마다 울리면 끄게 된다
/// - 앱을 보고 있으면 안 띄운다. 눈앞에 이미 보인다
bool shouldNotify({
  required bool mine,
  required bool isSystem,
  required bool inForeground,
  required bool enabled,
}) =>
    enabled && !inForeground && !mine && !isSystem;

/// 알림 한 줄에 쓸 글자로 다듬는다.
///
/// 주소를 그대로 보이면 안 된다 - 파일을 하나 올리면 알림이 긴 주소로 가득 찬다.
/// 이모티콘도 표시 문자라서 그대로 두면 빈칸처럼 보인다.
String previewText(String text) {
  final out = StringBuffer();
  for (final part in splitEmojiParts(text)) {
    if (part.isEmoji) {
      out.write('(이모티콘)');
      continue;
    }
    out.write(_withoutLinks(part.value));
  }
  final flat = out.toString().replaceAll(RegExp(r'\s+'), ' ').trim();
  if (flat.length <= previewLimit) return flat;
  return '${flat.substring(0, previewLimit)}…';
}

/// 알림에 보일 제목과 내용을 만든다.
///
/// [detail]이 꺼져 있으면 **누가 말했는지만** 알린다(PC 앱의 '사람만 표시'와 같다).
/// 남이 내 폰을 볼 수 있는 자리에서는 내용이 잠금화면에 뜨는 것이 곤란하다.
NotificationText previewFor({
  required String channel,
  required String sender,
  required String text,
  required bool detail,
}) {
  if (!detail) return NotificationText(channel, '$sender 님이 말했습니다');
  final body = previewText(text);
  return NotificationText(channel, body.isEmpty ? sender : '$sender: $body');
}

/// 우리 서버에 올린 파일 주소를 사람이 읽을 말로 바꾼다.
String _withoutLinks(String text) {
  if (!text.contains(relay.server)) return text;
  return text.replaceAllMapped(RegExp(r'\S+'), (match) {
    final word = match[0]!;
    if (!word.startsWith(relay.server)) return word;
    // 주소를 되돌려 읽지 않는다 - 한글 이름이 섞이면 Uri.decodeComponent 가
    // "Illegal percent encoding"으로 터지고, 그러면 알림이 통째로 안 뜬다.
    // 우리는 확장자만 알면 된다
    final name = word.split('?').first.split('/').last;
    final dot = name.lastIndexOf('.');
    final kind = dot < 0 ? '' : name.substring(dot + 1).toLowerCase();
    return imageKinds.contains(kind) ? '(사진)' : '(파일)';
  });
}

// ---------------------------------------------------------------------------
/// 알림을 띄우는 쪽. 화면과 상태는 이 약속만 알고, 진짜 플러그인은 아래에 있다.
///
/// 떼어둔 이유: 검사에서 알림 플러그인을 띄울 수 없다. 가짜를 끼워 "언제 띄우고
/// 언제 안 띄우는가"를 그대로 확인한다.
abstract class Notifier {
  /// 쓸 수 있게 준비한다(통로 만들기, 권한 묻기). 안 되면 false.
  Future<bool> prepare();

  /// 알림 자리를 이 내용으로 **갈아치운다**.
  Future<void> show(NotificationText what);

  /// 알림을 치운다. 앱을 다시 보면 읽은 것이므로 남겨둘 이유가 없다
  Future<void> clear();
}

/// 진짜 알림.
class LocalNotifier implements Notifier {
  final FlutterLocalNotificationsPlugin _plugin =
      FlutterLocalNotificationsPlugin();
  bool _ready = false;

  @override
  Future<bool> prepare() async {
    if (_ready) return true;
    try {
      // 22 버전부터 이름 있는 인자다. 자리로 넘기면 컴파일이 안 된다
      await _plugin.initialize(
        settings: const InitializationSettings(
          android: AndroidInitializationSettings('@mipmap/ic_launcher'),
        ),
      );
      // 안드로이드 13부터는 사람이 허락해야 알림이 보인다. 거절하면 조용히 안 뜨므로
      // 설정 화면에서 그 사실을 알려줄 수 있어야 한다
      final android = _plugin.resolvePlatformSpecificImplementation<
          AndroidFlutterLocalNotificationsPlugin>();
      final allowed = await android?.requestNotificationsPermission() ?? true;
      _ready = allowed;
      return allowed;
    } on Object {
      // 알림이 안 되는 것 때문에 채팅이 멈추면 안 된다
      return false;
    }
  }

  @override
  Future<void> show(NotificationText what) async {
    if (!_ready && !await prepare()) return;
    try {
      await _plugin.show(
        id: notificationId,
        title: what.title,
        body: what.body,
        notificationDetails: const NotificationDetails(
          android: AndroidNotificationDetails(
            channelId,
            channelName,
            channelDescription: '들어간 채널에 새 말이 올라오면 알립니다.',
            importance: Importance.high,
            priority: Priority.high,
            // 쌓지 않는다. 같은 번호 + 묶음 없이 띄우면 늘 한 줄만 남는다
            onlyAlertOnce: false,
            autoCancel: true,
          ),
        ),
      );
    } on Object {
      // 못 띄워도 채팅은 계속되어야 한다
    }
  }

  @override
  Future<void> clear() async {
    try {
      await _plugin.cancel(id: notificationId);
    } on Object {
      // 지울 게 없을 수도 있다
    }
  }
}
