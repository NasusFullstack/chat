/// 채팅 화면 - 좁으면 한 칸, 넓으면 두 칸.
///
/// 레이아웃만 갈리고 **상태는 하나**다(`AppState`). 그래서 폴드를 접었다 펴도 보던
/// 내용과 쓰던 글이 그대로 남는다 - 레이아웃이 바뀌는 순간이 위험한 자리라, 그때
/// 다시 만들어지는 것을 최대한 줄였다.
library;

import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';

import '../app_state.dart';
import '../core/availability.dart' show uploadBlockedText;
import '../core/client_badge.dart';
import '../core/emoji.dart';
import '../core/relay.dart' as relay;
import 'battle_lobby_page.dart';
import 'file_card.dart';
import 'layout.dart';
import 'room_picker.dart';
import 'settings_page.dart';

class ChatPage extends StatefulWidget {
  const ChatPage({super.key, required this.state});

  final AppState state;

  @override
  State<ChatPage> createState() => _ChatPageState();
}

class _ChatPageState extends State<ChatPage> {
  // 입력 중인 글과 스크롤 위치는 **화면 바깥**에 둔다. 폴드를 펴면서 레이아웃이
  // 1칸 <-> 2칸으로 갈아끼워질 때 쓰던 글이 날아가지 않게
  final _input = TextEditingController();
  final _scroll = ScrollController();

  @override
  void initState() {
    super.initState();
    widget.state.addListener(_onChanged);
  }

  @override
  void dispose() {
    widget.state.removeListener(_onChanged);
    _input.dispose();
    _scroll.dispose();
    super.dispose();
  }

  void _onChanged() {
    if (!mounted) return;
    setState(() {});
    // 새 줄이 오면 맨 아래로. 위를 보고 있을 때는 끌어내리지 않는다
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!_scroll.hasClients) return;
      final pos = _scroll.position;
      if (pos.pixels > pos.maxScrollExtent - 160) {
        _scroll.jumpTo(pos.maxScrollExtent);
      }
    });
  }

  /// 전투를 여는 말과 들어가는 말. PC 의 chat_core/constants.py 와 **같은 문구**여야
  /// 한다 - 다르면 PC 에서 연 방에 폰이 못 들어간다
  static const String openPhrase = '배틀크루저 전투';
  static const String joinPhrase = '배틀크루저 전투 참가';

  void _send() {
    final text = _input.text;
    if (text.trim().isEmpty) return;
    widget.state.sendChat(text);
    _input.clear();
    // 친 말은 채널에도 그대로 간다(PC 와 같다 - 남들도 무슨 일인지 알아야 한다).
    // 그러고 나서 나만 전투로 넘어간다
    _maybeBattle(text.trim());
  }

  void _maybeBattle(String text) {
    final channel = widget.state.current;
    if (channel.isEmpty) return;
    // 참가가 먼저다 - '배틀크루저 전투 참가'는 '배틀크루저 전투'로도 시작한다
    if (text == joinPhrase) {
      final open = widget.state.openRoom(channel);
      if (open == null) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
            content: Text('이 채널에 열린 전투 방이 없습니다.')));
        return;
      }
      _goBattle(open.$1, isHost: false);
    } else if (text == openPhrase) {
      _goBattle(widget.state.openBattleRoom(channel), isHost: true);
    }
  }

  void _goBattle(String room, {required bool isHost}) {
    Navigator.push(
      context,
      MaterialPageRoute<void>(
        builder: (_) => BattleLobbyPage(
          room: room,
          nick: widget.state.myId,
          isHost: isHost,
        ),
      ),
    );
  }

  Future<void> _pick({required bool photo}) async {
    // 버튼이 흐려도 다른 길로 올 수 있다 - 여기서 한 번 더 막고 **왜인지 말한다**
    if (!widget.state.canUploadHere) {
      ScaffoldMessenger.of(context)
          .showSnackBar(const SnackBar(content: Text(uploadBlockedText)));
      return;
    }
    final picker = ImagePicker();
    // 사진은 갤러리에서, 그 밖의 파일은 아직 사진 고르기로만 받는다(파일 고르기는
    // 기기마다 권한이 달라 따로 붙여야 한다)
    final picked = await picker.pickImage(source: ImageSource.gallery);
    if (picked == null) return;
    final result = await widget.state.upload(File(picked.path),
        kind: photo ? 'file' : 'file');
    if (!mounted) return;
    if (!result.ok) {
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(result.note)));
      return;
    }
    // 바로 보내지 않고 입력줄에 넣는다 - 한마디 덧붙이거나 지울 수 있어야 한다
    final now = _input.text;
    _input.text = now.isEmpty ? result.url : '$now ${result.url}';
    _input.selection = TextSelection.collapsed(offset: _input.text.length);
  }

  Future<void> _showEmoji() async {
    final picked = await showModalBottomSheet<String>(
      context: context,
      showDragHandle: true,
      builder: (_) => _EmojiSheet(state: widget.state),
    );
    if (picked == null || picked.isEmpty) return;
    // 입력줄에 넣고 보낼 때 그대로 나간다. 보이는 건 주소지만 받는 쪽은 그림으로 본다
    final now = _input.text;
    final mark = formatEmoji(picked);
    _input.text = now.isEmpty ? mark : '$now $mark';
    _input.selection = TextSelection.collapsed(offset: _input.text.length);
  }

  /// 들어갈 방을 고른다. 서버가 목록을 줄 수 있으면 **보고 고르고**, 아니면 이름을
  /// 받는다 - 어느 쪽인지는 `room_picker.dart` 가 안다.
  Future<void> _askChannel() async {
    final picked = await pickRoom(context, widget.state);
    if (picked == null) return;
    if (!widget.state.loggedIn) {
      // 로그인 전에 보내면 서버가 조용히 무시한다 - 그러면 "눌렀는데 아무 일도
      // 안 일어남"으로만 보이므로 여기서 알려준다
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('아직 서버에 로그인되지 않았습니다.')),
      );
      return;
    }
    widget.state.joinChannel(picked.name, key: picked.key);
  }

  void _showSettings() {
    Navigator.push(
      context,
      MaterialPageRoute<void>(builder: (_) => SettingsPage(state: widget.state)),
    );
  }

  void _showMembers() {
    showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      builder: (_) => _MemberList(state: widget.state),
    );
  }

  @override
  Widget build(BuildContext context) {
    final wide = isWide(context);
    final state = widget.state;
    final body = Column(
      children: [
        Expanded(child: _Messages(state: state, scroll: _scroll)),
        if (state.uploading.isNotEmpty)
          _UploadingBar(name: state.uploading),
        _InputRow(
          controller: _input,
          onSend: _send,
          onPhoto: () => _pick(photo: true),
          onEmoji: _showEmoji,
          enabled: state.current.isNotEmpty,
          photoEnabled: state.canUploadHere,
        ),
      ],
    );

    return Scaffold(
      appBar: AppBar(
        title: Text(state.current.isEmpty ? '춥채팅' : state.current),
        actions: [
          IconButton(
            onPressed: state.current.isEmpty ? null : _showMembers,
            icon: const Icon(Icons.people_outline),
            tooltip: '참여자',
          ),
          IconButton(
            onPressed: _showSettings,
            icon: const Icon(Icons.settings_outlined),
            tooltip: '설정',
          ),
        ],
      ),
      // 좁은 화면에서는 채널 목록을 서랍으로 숨긴다. 넓으면 왼쪽에 펼쳐 둔다
      drawer: wide
          ? null
          : Drawer(child: _ChannelList(state: state, onAdd: _askChannel)),
      body: SafeArea(
        child: wide
            ? Row(
                children: [
                  SizedBox(
                    width: sidePaneWidth,
                    child: _ChannelList(state: state, onAdd: _askChannel),
                  ),
                  const VerticalDivider(width: 1),
                  Expanded(child: body),
                ],
              )
            : body,
      ),
    );
  }
}

class _ChannelList extends StatelessWidget {
  const _ChannelList({required this.state, required this.onAdd});

  final AppState state;
  final VoidCallback onAdd;

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: Column(
        children: [
          ListTile(
            title: const Text('채널'),
            trailing: IconButton(
              onPressed: onAdd,
              icon: const Icon(Icons.add),
              tooltip: '채널 들어가기',
            ),
          ),
          const Divider(height: 1),
          Expanded(
            child: state.channels.isEmpty
                ? const Center(
                    child: Padding(
                      padding: EdgeInsets.all(20),
                      child: Text('아직 들어간 채널이 없습니다.\n+ 를 눌러 들어가세요.',
                          textAlign: TextAlign.center),
                    ),
                  )
                : ListView.builder(
                    itemCount: state.channels.length,
                    itemBuilder: (_, i) {
                      final channel = state.channels[i];
                      final count = state.unread[channel] ?? 0;
                      return ListTile(
                        selected: channel == state.current,
                        title: Text(channel),
                        trailing: count > 0
                            ? Badge(label: Text('$count'))
                            : null,
                        onTap: () {
                          state.showChannel(channel);
                          // 서랍으로 열려 있던 경우에만 닫는다
                          final nav = Navigator.of(context);
                          if (nav.canPop()) nav.pop();
                        },
                        onLongPress: () => state.leaveChannel(channel),
                      );
                    },
                  ),
          ),
        ],
      ),
    );
  }
}

class _MemberList extends StatelessWidget {
  const _MemberList({required this.state});

  final AppState state;

  @override
  Widget build(BuildContext context) {
    final people = state.members[state.current] ?? const <String>[];
    return SafeArea(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          ListTile(title: Text('참여자 ${people.length}명')),
          const Divider(height: 1),
          Flexible(
            child: ListView.builder(
              shrinkWrap: true,
              itemCount: people.length,
              // 보이는 이름은 **상태에 물어본다**(state.displayName). 서버 채팅은
              // 아이디와 보이는 이름이 따로고, 여기서 `nicknames[id] ?? id` 를
              // 직접 쓰면 다른 칸에서 한 군데를 빠뜨리는 날이 온다
              itemBuilder: (_, i) => _Member(
                nick: state.displayName(people[i]),
                avatar: state.avatars[people[i]],
                client: state.clients[people[i]] ?? const ClientInfo(),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// 참여자 한 줄 - 얼굴, 이름, 그리고 **무슨 프로그램으로 들어와 있는지**.
///
/// 프로그램은 IRC 로 묻지 않고 중계 서버에서 받아온다(core/client_badge.dart 에 이유).
/// 모르는 사람은 아무것도 안 적는다 - "알 수 없음"을 적으면 목록이 그 글자로 찬다.
class _Member extends StatelessWidget {
  const _Member({required this.nick, required this.avatar, required this.client});

  final String nick;
  final String? avatar;
  final ClientInfo client;

  @override
  Widget build(BuildContext context) {
    final badge = badgeText(client);
    return ListTile(
      // 아이콘은 서버에서 받아온다(UserlistUpdated -> wantFaces). 예전엔 받아놓고도
      // 사람 모양 기본 아이콘만 그려서 "프로필이 안 불러와진다"로 보였다
      leading: _Face(nick: nick, avatar: avatar, size: faceInList),
      title: Text(nick),
      subtitle: badge.isEmpty ? null : Text(badge),
      trailing: switch (client.platform) {
        'mobile' => const Icon(Icons.smartphone, size: 18),
        'pc' => const Icon(Icons.computer, size: 18),
        _ => null,
      },
    );
  }
}

class _Messages extends StatelessWidget {
  const _Messages({required this.state, required this.scroll});

  final AppState state;
  final ScrollController scroll;

  @override
  Widget build(BuildContext context) {
    final lines = state.lines[state.current] ?? const <ChatLine>[];
    if (lines.isEmpty) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Text(
            state.current.isEmpty
                ? '채널에 들어가면 여기에 이야기가 쌓입니다.'
                : '아직 아무 말도 없습니다.',
            textAlign: TextAlign.center,
            style: Theme.of(context).textTheme.bodyMedium,
          ),
        ),
      );
    }
    return ListView.builder(
      controller: scroll,
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      itemCount: lines.length,
      itemBuilder: (_, i) => _Line(line: lines[i], state: state),
    );
  }
}

class _Line extends StatelessWidget {
  const _Line({required this.line, required this.state});

  final ChatLine line;
  final AppState state;

  /// 글 안에 우리 서버 파일 주소가 있으면 그것(없으면 빈 값).
  String get _fileUrl {
    for (final word in line.text.split(RegExp(r'\s+'))) {
      if (relay.fileIdFrom(word).isNotEmpty) return word;
    }
    return '';
  }

  /// 주소를 뺀 나머지 - 카드가 뜨면 주소 글자는 지저분하므로 뺀다.
  String get _textWithoutFile {
    final url = _fileUrl;
    if (url.isEmpty) return line.text;
    return line.text.replaceAll(url, '').trim();
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    if (line.isSystem) {
      return Padding(
        padding: const EdgeInsets.symmetric(vertical: 4),
        child: Text(
          line.text,
          textAlign: TextAlign.center,
          style: TextStyle(color: scheme.onSurfaceVariant, fontSize: 12),
        ),
      );
    }
    final fileUrl = _fileUrl;
    final body = _textWithoutFile;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 3),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _Face(
              nick: state.displayName(line.sender),
              avatar: state.avatars[line.sender]),
          const SizedBox(width: 8),
          // 긴 글이 화면 밖으로 나가지 않게 남은 폭을 전부 준다
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                if (body.isNotEmpty)
                  RichText(
                    text: TextSpan(
                      style: DefaultTextStyle.of(context).style,
                      children: [
                        TextSpan(
                          text: '${state.displayName(line.sender)}: ',
                          style: TextStyle(
                            fontWeight: FontWeight.bold,
                            color: line.mine ? scheme.primary : scheme.tertiary,
                          ),
                        ),
                        // 이모티콘은 글 사이에 **그림으로** 들어간다. 주소 글자가
                        // 그대로 보이면 한 줄이 주소로 가득 찬다
                        for (final part in splitEmojiParts(body))
                          if (part.isEmoji)
                            WidgetSpan(
                              alignment: PlaceholderAlignment.middle,
                              child: _Emoji(url: part.value),
                            )
                          else
                            TextSpan(
                              text: part.value,
                              style: line.isMention
                                  ? TextStyle(
                                      backgroundColor: scheme.primaryContainer,
                                      color: scheme.onPrimaryContainer,
                                    )
                                  : null,
                            ),
                      ],
                    ),
                  )
                else
                  Text('${state.displayName(line.sender)}:',
                      style: TextStyle(
                        fontWeight: FontWeight.bold,
                        color: line.mine ? scheme.primary : scheme.tertiary,
                      )),
                if (fileUrl.isNotEmpty)
                  _Attachment(url: fileUrl, state: state),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _UploadingBar extends StatelessWidget {
  const _UploadingBar({required this.name});

  final String name;

  @override
  Widget build(BuildContext context) {
    // 올리는 데 한참 걸릴 수 있다. 아무 표시가 없으면 멈춘 줄 안다
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
      child: Row(
        children: [
          const SizedBox(
              width: 14, height: 14, child: CircularProgressIndicator(strokeWidth: 2)),
          const SizedBox(width: 10),
          Expanded(
            child: Text('$name 올리는 중...',
                overflow: TextOverflow.ellipsis,
                style: Theme.of(context).textTheme.bodySmall),
          ),
        ],
      ),
    );
  }
}

class _InputRow extends StatelessWidget {
  const _InputRow({
    required this.controller,
    required this.onSend,
    required this.onPhoto,
    required this.onEmoji,
    required this.enabled,
    this.photoEnabled = true,
  });

  final TextEditingController controller;
  final VoidCallback onSend;
  final VoidCallback onPhoto;
  final VoidCallback onEmoji;
  final bool enabled;

  /// 이 방에서 사진을 올릴 수 있나. 막힌 방에서는 버튼을 흐리게 두고 왜인지 알려준다
  final bool photoEnabled;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(12, 4, 8, 10),
      child: Row(
        children: [
          IconButton(
            onPressed: enabled ? onEmoji : null,
            icon: const Icon(Icons.emoji_emotions_outlined),
            tooltip: '이모티콘',
          ),
          IconButton(
            // 막힌 방에서도 **눌리기는 한다** - 흐리게만 하고 누르면 왜인지 알려준다.
            // 아예 못 누르게 하면 "고장났나" 하고 이유를 알 길이 없다
            onPressed: enabled ? onPhoto : null,
            icon: Icon(Icons.image_outlined,
                color: photoEnabled
                    ? null
                    : Theme.of(context).disabledColor),
            tooltip: photoEnabled ? '사진 보내기' : uploadBlockedText,
          ),
          Expanded(
            child: TextField(
              controller: controller,
              enabled: enabled,
              textInputAction: TextInputAction.send,
              onSubmitted: (_) => onSend(),
              decoration: InputDecoration(
                isDense: true,
                hintText: enabled ? '메시지 입력' : '채널에 먼저 들어가세요',
                border: const OutlineInputBorder(),
              ),
            ),
          ),
          IconButton(
            onPressed: enabled ? onSend : null,
            icon: const Icon(Icons.send),
            tooltip: '보내기',
          ),
        ],
      ),
    );
  }
}


/// 말풍선 옆 얼굴 지름.
///
/// **첫 줄 글 높이와 같게** 맞춘다. 더 크면 위로 맞춰도 얼굴 가운데가 글 가운데보다
/// 내려앉아서 이름과 어긋나 보인다(실측: 지름 26 / 첫 줄 20 일 때 3px). PC 앱도
/// 같은 이유로 작게 쓴다(AVATAR_MSG_PX = 16).
const double faceInLine = 20;

/// 참여자 목록의 얼굴. 여기는 줄에 맞출 글이 없고 손으로 누르는 자리라 크게 둔다
const double faceInList = 36;

/// 사람 얼굴 - 서버에서 받아온 아이콘. 없으면 이름 첫 글자로 대신한다.
class _Face extends StatelessWidget {
  const _Face({required this.nick, this.avatar, this.size = faceInLine});

  final String nick;
  final String? avatar;
  final double size;

  @override
  Widget build(BuildContext context) {
    final data = avatar;
    if (data != null && data.isNotEmpty) {
      try {
        return CircleAvatar(
          radius: size / 2,
          backgroundImage: MemoryImage(base64Decode(data)),
        );
      } on Object {
        // 깨진 아이콘이 와도 줄이 통째로 안 그려지면 안 된다
      }
    }
    return CircleAvatar(
      radius: size / 2,
      child: Text(nick.isEmpty ? '?' : nick.characters.first,
          style: TextStyle(fontSize: size * 0.46)),
    );
  }
}

/// 글에 딸려온 우리 서버 파일 - 그림이면 미리보기, 아니면 카드.
///
/// 그림인지는 **내용으로** 정한다(서버가 올릴 때 보고 알려준다). 이름이 .dat 여도
/// 사진이면 사진으로 보여줘야 한다.
class _Attachment extends StatefulWidget {
  const _Attachment({required this.url, required this.state});

  final String url;
  final AppState state;

  @override
  State<_Attachment> createState() => _AttachmentState();
}

class _AttachmentState extends State<_Attachment> {
  Map<String, dynamic>? _info;
  bool _asked = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    if (_asked) return;
    _asked = true;
    final id = relay.fileIdFrom(widget.url);
    final info = await widget.state.files.meta(id);
    if (!mounted) return;
    setState(() => _info = info);
  }

  @override
  Widget build(BuildContext context) {
    final info = _info;
    // 아직 모르거나 이미 사라진 파일이면 아무것도 안 그린다 - 그러면 주소 글자가
    // 그대로 남는데, 그게 '없는 파일 카드'를 그리는 것보다 낫다
    if (info == null) return const SizedBox.shrink();
    if (info['image'] == true) {
      return Padding(
        padding: const EdgeInsets.only(top: 4),
        child: ClipRRect(
          borderRadius: BorderRadius.circular(8),
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 260, maxHeight: 260),
            child: Image.network(widget.url, fit: BoxFit.contain),
          ),
        ),
      );
    }
    return FileCard(
      url: widget.url,
      info: info,
      mine: widget.state.fileTokens.containsKey(relay.fileIdFrom(widget.url)),
    );
  }
}


/// 글 사이에 들어가는 이모티콘 한 개.
class _Emoji extends StatelessWidget {
  const _Emoji({required this.url});

  final String url;

  /// 채팅에 보이는 크기. PC 앱은 192px인데 폰은 화면이 좁아 그보다 작게 잡는다
  static const double side = 96;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 2),
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: side, maxHeight: side),
        // 못 받아왔을 때 줄이 통째로 안 그려지면 안 된다
        child: Image.network(url, fit: BoxFit.contain,
            errorBuilder: (_, _, _) => const Icon(Icons.broken_image_outlined)),
      ),
    );
  }
}

/// 다 같이 쓰는 이모티콘 고르기.
class _EmojiSheet extends StatefulWidget {
  const _EmojiSheet({required this.state});

  final AppState state;

  @override
  State<_EmojiSheet> createState() => _EmojiSheetState();
}

class _EmojiSheetState extends State<_EmojiSheet> {
  List<Map<String, String>>? _items;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final items = await widget.state.files.sharedEmoji();
    if (!mounted) return;
    setState(() => _items = items);
  }

  @override
  Widget build(BuildContext context) {
    final items = _items;
    return SafeArea(
      child: SizedBox(
        height: 320,
        child: items == null
            ? const Center(child: CircularProgressIndicator())
            : items.isEmpty
                ? const Center(
                    child: Padding(
                      padding: EdgeInsets.all(24),
                      child: Text('아직 저장된 이모티콘이 없습니다.\n'
                          'PC 앱에서 그림을 우클릭해 저장하면 여기에 쌓입니다.',
                          textAlign: TextAlign.center),
                    ),
                  )
                : GridView.builder(
                    padding: const EdgeInsets.all(12),
                    gridDelegate: const SliverGridDelegateWithMaxCrossAxisExtent(
                      maxCrossAxisExtent: 110,
                      mainAxisSpacing: 8,
                      crossAxisSpacing: 8,
                    ),
                    itemCount: items.length,
                    itemBuilder: (_, i) {
                      final item = items[i];
                      return InkWell(
                        onTap: () => Navigator.pop(context, item['url']),
                        child: Column(
                          children: [
                            Expanded(
                              child: Image.network(item['url']!,
                                  fit: BoxFit.contain,
                                  errorBuilder: (_, _, _) =>
                                      const Icon(Icons.broken_image_outlined)),
                            ),
                            Text(item['name'] ?? '',
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: const TextStyle(fontSize: 11)),
                          ],
                        ),
                      );
                    },
                  ),
      ),
    );
  }
}
