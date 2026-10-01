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
import '../core/emoji.dart';
import '../core/relay.dart' as relay;
import 'file_card.dart';
import 'layout.dart';

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

  void _send() {
    final text = _input.text;
    if (text.trim().isEmpty) return;
    widget.state.sendChat(text);
    _input.clear();
  }

  Future<void> _pick({required bool photo}) async {
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

  Future<void> _askChannel() async {
    final controller = TextEditingController();
    final name = await showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('채널 들어가기'),
        content: TextField(
          controller: controller,
          autofocus: true,
          decoration: const InputDecoration(
            hintText: '일반',
            helperText: '# 은 안 붙여도 됩니다',
          ),
          onSubmitted: (v) => Navigator.pop(ctx, v),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('취소')),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, controller.text),
            child: const Text('들어가기'),
          ),
        ],
      ),
    );
    if (name != null && name.trim().isNotEmpty) {
      widget.state.joinChannel(name.trim());
    }
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
              itemBuilder: (_, i) => ListTile(
                leading: const Icon(Icons.person_outline),
                title: Text(people[i]),
              ),
            ),
          ),
        ],
      ),
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
          _Face(nick: line.sender, avatar: state.avatars[line.sender]),
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
                          text: '${line.sender}: ',
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
                  Text('${line.sender}:',
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
  });

  final TextEditingController controller;
  final VoidCallback onSend;
  final VoidCallback onPhoto;
  final VoidCallback onEmoji;
  final bool enabled;

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
            onPressed: enabled ? onPhoto : null,
            icon: const Icon(Icons.image_outlined),
            tooltip: '사진 보내기',
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


/// 사람 얼굴 - 서버에서 받아온 아이콘. 없으면 이름 첫 글자로 대신한다.
class _Face extends StatelessWidget {
  const _Face({required this.nick, this.avatar});

  final String nick;
  final String? avatar;

  @override
  Widget build(BuildContext context) {
    final data = avatar;
    if (data != null && data.isNotEmpty) {
      try {
        return CircleAvatar(
          radius: 13,
          backgroundImage: MemoryImage(base64Decode(data)),
        );
      } on Object {
        // 깨진 아이콘이 와도 줄이 통째로 안 그려지면 안 된다
      }
    }
    return CircleAvatar(
      radius: 13,
      child: Text(nick.isEmpty ? '?' : nick.characters.first,
          style: const TextStyle(fontSize: 12)),
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
