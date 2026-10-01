/// 메시지 안의 이모티콘 - 어떻게 실어 보내고 어떻게 갈라내는가.
///
/// PC 앱의 `chat_core/commands.py`를 옮긴 것이다. **주소만 실어 보낸다** - 보관함
/// 목록을 채널에 뿌리면 512바이트 제한 때문에 수십 줄로 쪼개져 나가고, 서버가 그걸
/// 폭주로 보고 연결을 끊는다.
///
/// 표시 문자는 유니코드 사용자 영역(U+E000, U+E001)이라 사람이 칠 일이 없다. 이걸
/// 모르는 클라이언트에게는 그냥 주소가 보일 뿐이라 대화가 깨지지 않는다.
library;

const String emojiOpen = '';
const String emojiClose = '';

/// 메시지에 넣을 이모티콘 표시.
String formatEmoji(String url) => '$emojiOpen$url$emojiClose';

/// 글 조각 하나 - 글자이거나 이모티콘이거나.
class MessagePart {
  const MessagePart.text(this.value) : isEmoji = false;

  const MessagePart.emoji(this.value) : isEmoji = true;

  final String value;
  final bool isEmoji;

  @override
  bool operator ==(Object other) =>
      other is MessagePart && other.value == value && other.isEmoji == isEmoji;

  @override
  int get hashCode => Object.hash(value, isEmoji);

  @override
  String toString() => isEmoji ? 'emoji($value)' : 'text($value)';
}

/// 메시지를 글자와 이모티콘으로 가른다.
///
/// 짝이 안 맞는 표시(잘렸거나 남의 클라이언트가 흉내낸 경우)는 **그냥 글자로 취급**해서
/// 대화가 사라지지 않게 한다.
List<MessagePart> splitEmojiParts(String text) {
  if (!text.contains(emojiOpen)) return [MessagePart.text(text)];
  final parts = <MessagePart>[];
  var rest = text;
  while (true) {
    final open = rest.indexOf(emojiOpen);
    if (open < 0) {
      if (rest.isNotEmpty) parts.add(MessagePart.text(rest));
      break;
    }
    final before = rest.substring(0, open);
    final after = rest.substring(open + emojiOpen.length);
    final close = after.indexOf(emojiClose);
    if (close < 0) {
      // 닫는 표시가 없다 - 원문 그대로 보여준다
      parts.add(MessagePart.text(before + emojiOpen + after));
      break;
    }
    final url = after.substring(0, close);
    if (before.isNotEmpty) parts.add(MessagePart.text(before));
    parts.add(url.isNotEmpty ? MessagePart.emoji(url) : const MessagePart.text(''));
    rest = after.substring(close + emojiClose.length);
  }
  return parts.where((p) => p.value.isNotEmpty || p.isEmoji).toList();
}
